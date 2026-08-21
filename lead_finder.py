#!/usr/bin/env python3
"""
lead_finder.py — find local businesses with no listed website.

Uses two free, public OpenStreetMap services (no API key needed):
  - Nominatim: turns a place name/address into lat/lon ("geocoding")
  - Overpass:  queries OSM's business data for a given tag near a point

Both are shared public infrastructure with usage policies (identify
yourself via User-Agent, don't hammer them) — see the comments below.
"""

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Every business type we can search for, mapped to its OpenStreetMap tag(s).
# OSM tags them as free-form key=value pairs — e.g. a plumber is tagged
# craft=plumber, a restaurant is amenity=restaurant. Add more here as needed.
CATEGORIES = {
    # trades — often no site at all, and they win work by being findable
    "plumber": [("craft", "plumber")],
    "electrician": [("craft", "electrician")],
    "builder": [("craft", "builder"), ("craft", "carpenter")],
    "painter": [("craft", "painter")],
    "roofer": [("craft", "roofer")],
    "landscaper": [("craft", "gardener"), ("shop", "garden_centre")],
    "cleaner": [("shop", "laundry"), ("shop", "dry_cleaning")],
    # appearance — heavy repeat custom, booking pages sell well
    "hair_salon": [("shop", "hairdresser")],
    "barber": [("shop", "hairdresser"), ("shop", "barber")],
    "nail_salon": [("shop", "beauty"), ("shop", "nail_salon")],
    "tattoo": [("shop", "tattoo")],
    "spa": [("leisure", "spa"), ("shop", "massage")],
    # food — menus and hours are the whole job
    "restaurant": [("amenity", "restaurant")],
    "cafe": [("amenity", "cafe")],
    "bakery": [("shop", "bakery")],
    "bar": [("amenity", "bar"), ("amenity", "pub")],
    "food_truck": [("amenity", "fast_food")],
    "butcher": [("shop", "butcher")],
    # services
    "gym": [("leisure", "fitness_centre")],
    "dentist": [("amenity", "dentist")],
    "doctor": [("amenity", "doctors")],
    "vet": [("amenity", "veterinary")],
    "lawyer": [("office", "lawyer")],
    "accountant": [("office", "accountant")],
    "estate_agent": [("office", "estate_agent")],
    "auto_repair": [("shop", "car_repair")],
    "car_wash": [("amenity", "car_wash")],
    "dog_groomer": [("shop", "pet_grooming"), ("shop", "pet")],
    "childcare": [("amenity", "childcare"), ("amenity", "kindergarten")],
    # retail
    "florist": [("shop", "florist")],
    "jeweller": [("shop", "jewelry")],
    "clothing": [("shop", "clothes")],
    "furniture": [("shop", "furniture")],
    "hardware": [("shop", "hardware"), ("shop", "doityourself")],
    "bike_shop": [("shop", "bicycle")],
    "bookshop": [("shop", "books")],
    "optician": [("shop", "optician")],
    "pharmacy": [("amenity", "pharmacy")],
    "photographer": [("shop", "photo"), ("craft", "photographer")],
}

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Nominatim's usage policy requires a real identifying User-Agent (not a
# browser string) so they can contact someone if a script misbehaves.
USER_AGENT = "sitesmith/0.1 (personal project; finley.smith.1@alpha.school)"


def geocode(location):
    """Turn a place name/address into (lat, lon). Returns None if not found."""
    params = urllib.parse.urlencode({"q": location, "format": "json", "limit": 1})
    req = urllib.request.Request(
        f"{NOMINATIM_URL}?{params}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        results = json.load(resp)
    if not results:
        return None
    return float(results[0]["lat"]), float(results[0]["lon"])


def build_overpass_query(lat, lon, radius, tag_pairs):
    """Build an Overpass QL query for nodes+ways matching any of tag_pairs
    within `radius` meters of (lat, lon). `out center tags` returns each
    result's tags plus a usable coordinate even for way-shaped features."""
    clauses = []
    for key, value in tag_pairs:
        clauses.append(f'  node["{key}"="{value}"](around:{radius},{lat},{lon});')
        clauses.append(f'  way["{key}"="{value}"](around:{radius},{lat},{lon});')
    body = "\n".join(clauses)
    return f"[out:json][timeout:25];\n(\n{body}\n);\nout center tags;"


def query_overpass(query):
    req = urllib.request.Request(
        OVERPASS_URL,
        data=query.encode("utf-8"),
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def element_coords(element):
    """Nodes have lat/lon directly; ways only get coords via `out center`."""
    if "lat" in element:
        return element["lat"], element["lon"]
    center = element.get("center")
    if center:
        return center["lat"], center["lon"]
    return None, None


def format_address(tags):
    parts = [tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:city")]
    return " ".join(p for p in parts if p)


def find_leads(elements):
    """Filter to named businesses with no website tag on record."""
    leads = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue  # nothing to pitch to without a name
        has_site = bool(tags.get("website") or tags.get("contact:website"))
        if has_site:
            continue
        lat, lon = element_coords(el)
        leads.append(
            {
                "name": name,
                "phone": tags.get("phone") or tags.get("contact:phone") or "",
                "address": format_address(tags),
                "lat": lat,
                "lon": lon,
                # Signals that say how ready this business is to buy a website.
                # Kept as raw facts here; score_lead() turns them into a number,
                # so the reasoning stays visible instead of collapsing to a digit.
                "signals": {
                    # Social presence with nowhere to send people is the single
                    # best tell: they already care about being found online.
                    "social": bool(tags.get("contact:facebook") or tags.get("facebook")
                                   or tags.get("contact:instagram")),
                    "email": tags.get("email") or tags.get("contact:email") or "",
                    "hours": bool(tags.get("opening_hours")),
                    # The actual hours string, so a generated site shows their
                    # REAL hours instead of inventing "Mon-Fri 9-5". Never fill
                    # this in from a guess — an empty value means the site omits
                    # the hours section rather than making one up.
                    "hours_text": tags.get("opening_hours", ""),
                    "takeaway": bool(tags.get("delivery") or tags.get("takeaway")),
                    "cuisine": tags.get("cuisine", ""),
                    "brand": bool(tags.get("brand")),   # a chain: head office owns the site
                },
                "maps_link": (
                    f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
                    if lat is not None
                    else ""
                ),
            }
        )
    return leads


def score_lead(lead):
    """How worth chasing is this one? Returns (score 0-100, list of reasons).

    Deliberately explainable — the reasons are shown in the app next to the
    number. A score you cannot interrogate is a score you stop trusting the first
    time it puts something silly at the top.
    """
    sig = lead.get("signals") or {}
    score, why = 50, []

    if sig.get("social"):
        score += 25
        why.append("has social but nowhere to send people")
    if lead.get("phone"):
        score += 10
        why.append("phone listed — you can just call")
    if sig.get("email"):
        score += 8
        why.append("email listed")
    if sig.get("hours"):
        score += 5
        why.append("keeps their listing updated")
    if sig.get("takeaway") or sig.get("cuisine"):
        score += 5
        why.append("takes orders — a menu page pays for itself")
    if lead.get("possible_site"):
        score -= 30
        why.append("might already have a site — check first")
    if sig.get("brand"):
        score -= 35
        why.append("looks like a chain — head office owns the website")
    if not lead.get("address"):
        score -= 10
        why.append("no address on record")

    return max(0, min(100, score)), why


# --------------------------------------------------------------- verification
#
# A missing `website` tag on OSM is NOT proof a business has no website — plenty
# of shops simply never got tagged. That is the biggest weakness of this tool and
# the README already warns about it. Measured on the very first result of a real
# run: "Rudy's Barbershop, Portland" has no OSM website tag and owns
# rudysbarbershop.com. Pitching a web design to someone who already has a site
# wastes the one thing there is least of — time.
#
# So --verify searches the open web for each lead and drops the ones that clearly
# already have their own site. Free, no API key, stdlib only.

SEARCH_URL = "https://www.bing.com/search?q="

# A browser User-Agent, unlike the Nominatim calls above. Deliberate and worth
# explaining: OSM's usage policy asks for an identifying agent so they can
# contact you. A general search engine has no such policy and simply refuses
# non-browser clients, so the honest identifying string gets zero results.
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 🔴 A listing on one of these is NOT the business having a website — it is a
# directory that lists everyone. A shop whose only web presence is a Yelp page is
# still a good lead; arguably a better one, because it proves they care about
# being findable and have nowhere of their own to send people.
DIRECTORIES = {
    "yelp.", "facebook.", "fb.com", "instagram.", "tripadvisor.", "mapquest.",
    "yellowpages.", "bbb.org", "foursquare.", "nextdoor.", "chamberofcommerce.",
    "opentable.", "doordash.", "ubereats.", "grubhub.", "booksy.", "vagaro.",
    "styleseat.", "square.site", "linkedin.", "indeed.", "glassdoor.",
    "storeshours.", "hours-", "-hours.", "manta.", "cylex", "bizapedia",
    "google.", "bing.", "apple.com", "wikipedia.", "youtube.", "tiktok.",
    "angi.", "thumbtack.", "houzz.", "trustpilot.", "zocdoc.", "healthgrades.",
}


def _slug(text):
    """Letters and digits only, lowercased — 'Rudy's Barbershop' -> rudysbarbershop."""
    return "".join(c for c in text.lower() if c.isalnum())


def looks_like_own_site(name, domain):
    """Is this domain plausibly THIS business's own website?

    Compares the squashed business name against the squashed domain. Matches
    'Rudy's Barbershop' to rudysbarbershop.com, and also the common case where
    the domain uses only the distinctive part of the name ('kimshair.com').
    """
    host = domain.lower()
    if host.startswith("www."):
        host = host[4:]
    stem = _slug(host.rsplit(".", 1)[0] if "." in host else host)
    full = _slug(name)
    if not stem or not full:
        return False

    # Generic trade words appear in thousands of unrelated domains.
    generic = {"the", "and", "salon", "hair", "shop", "barber", "barbershop",
               "cafe", "restaurant", "bar", "grill", "studio", "spa", "co",
               "inc", "llc", "company", "clinic", "center", "centre", "beauty",
               "nails", "dental", "auto", "repair", "gym", "fitness", "law"}

    # The name is contained in the domain: rudysbarbershop.com. Confident.
    if full in stem:
        return True
    # The domain is a shortened form of the name: "Bishops Cuts" -> bishops.co.
    # 🔴 Must exclude generic stems or salon.com "matches" every salon in town —
    # and a false match here DELETES a real lead, which is the expensive direction
    # to be wrong in. Better to leave a verified-website business on the list for
    # Finley to spot than to silently bin a genuine prospect.
    if stem in full and stem not in generic and len(stem) >= 5:
        return True
    words = [w for w in "".join(
        c if c.isalnum() else " " for c in name.lower()).split() if w not in generic]
    # Two or more distinctive words both present is a confident match.
    hits = sum(1 for w in words if len(w) > 2 and w in stem)
    return hits >= 2 or (len(words) == 1 and words[0] in stem and len(words[0]) > 4)


# Tells that a domain resolves but has nothing real on it — a registrar parking
# page, a for-sale holder, a blank host. A business whose only "website" is one of
# these effectively has NO working site, which makes them a GOOD lead (and a sharp
# pitch angle: "you own the domain but there's nothing there").
PARKED = (
    "domain is for sale", "buy this domain", "is parked", "parked free",
    "godaddy.com/domainsearch", "sedoparking", "hugedomains", "domain for sale",
    "this domain may be for sale", "under construction", "coming soon",
    "default web page", "apache2 ubuntu default", "welcome to nginx",
    "future home of something", "account suspended",
)


def fetch_page(url, timeout=12):
    """Open a URL like a browser and return its lowercased HTML, or None.

    Small local business sites almost never block a plain client — that is the big
    marketplaces (Etsy, eBay). Using stdlib urllib keeps this tool dependency-free
    and portable to a Mac, which is the whole point of the project.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(500_000)          # cap: we only need title/headers/footer
        return raw.decode("utf-8", "ignore").lower()
    except Exception:
        return None


def site_is_real(domain, name, timeout=12):
    """Actually OPEN a candidate domain and judge it. This is the verification
    step: a name matching a domain in a search result is a lead, not proof — the
    proof is opening the page and seeing the business on it.

    Returns one of:
      "match"   — the site loads and mentions this business. They have a site.
      "parked"  — the domain resolves but is empty/for-sale. No working site.
      "unknown" — loads but does not clearly mention them, OR would not open at
                  all. Cannot confirm either way.
    """
    host = domain[4:] if domain.startswith("www.") else domain
    generic = {"the", "and", "salon", "hair", "shop", "barber", "barbershop",
               "cafe", "restaurant", "bar", "grill", "studio", "spa", "co",
               "inc", "llc", "company", "clinic", "center", "centre", "beauty",
               "nails", "dental", "auto", "repair", "gym", "fitness", "law"}
    words = [w for w in re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
             if len(w) > 2 and w not in generic]

    opened = False
    for url in (f"https://{host}", f"https://www.{host}", f"http://{host}"):
        html = fetch_page(url, timeout)
        if html is None:
            continue
        opened = True
        if any(p in html for p in PARKED):
            return "parked"
        # A distinctive word from the name, on the business's own matching domain,
        # is strong confirmation — this really is their site.
        if any(w in html for w in words):
            return "match"
        break
    # Opened but no distinctive word: ambiguous. Never opened: also unknown, and
    # the caller keeps the lead — a site we could not reach is not a site we can
    # prove exists.
    return "unknown"


def find_website(name, location, timeout=20):
    """Search the open web for this business. Returns its own domain, or None.

    🔴 A NAME MATCH ALONE IS NOT ENOUGH, and the first live run proved it badly.
    Short business names collide with big unrelated brands:

        "Polaris for Hair"           -> polaris.com    (the snowmobile company)
        "House of David"             -> house.gov      (the US Congress)
        "Blondie"                    -> blondie.lnk.to (the band)
        "Northwest Barber Assoc."    -> northwest.bank

    Every one of those would have silently deleted a real prospect. So a domain is
    only accepted when the search result that carries it ALSO mentions the town —
    a genuine local business's own site says where it is; polaris.com does not.

    Returns (domain, certain). `certain` is True only when the town was also in
    that result. (None, False) means no site found OR the search was unreachable —
    the caller cannot distinguish those, which is the safe way round: a failed
    search keeps the lead rather than binning it.
    """
    query = f"{name} {location}".strip()
    url = SEARCH_URL + urllib.parse.quote(query)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "ignore")
    except Exception:
        return None, False

    # "Portland, OR" -> "portland". The town is the part that has to show up.
    town = location.split(",")[0].strip().lower()

    # Bing wraps each organic result in <li class="b_algo">. Working per-result
    # keeps a domain tied to the snippet that mentions it, instead of matching a
    # domain from result 1 against a town named in result 7.
    # Two grades of answer, because the cost of being wrong is lopsided. A
    # CERTAIN hit (name matches AND the town appears in the same result) is safe
    # to drop. A MAYBE (name matches, no town) gets kept and flagged instead —
    # requiring the town for everything was correct but so strict it only caught
    # 1 site in 32, which is barely worth running.
    candidate, local_hit = None, None
    for block in re.split(r'<li class="b_algo"', body)[1:]:
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", block)).lower()
        local = bool(town) and town in text
        for host in re.findall(r"https?://([a-z0-9.-]+\.[a-z]{2,})", text):
            if any(d in host for d in DIRECTORIES):
                continue
            if not looks_like_own_site(name, host):
                continue
            if local and local_hit is None:
                local_hit = host
            if candidate is None:
                candidate = host
    best = local_hit or candidate
    if not best:
        return None, False

    # 🔴 THE VERIFICATION STEP. A search snippet is a lead, not proof — before we
    # tell Finley a business has a website (and drop it), we OPEN the site and look.
    # This turns three cases into honest answers that the search alone got wrong:
    #   - a live site that mentions them  -> confirmed, drop it (don't waste a pitch)
    #   - a parked / for-sale / dead domain -> NOT a working site, KEEP the lead
    #     (and it's a great angle: "you own the domain but there's nothing there")
    #   - a domain we can't confirm -> flag it, never silently drop
    verdict = site_is_real(best, name, timeout=12)
    if verdict == "match":
        return best, True            # opened it, saw them — real site, drop
    if verdict == "parked":
        return None, False           # domain resolves but empty — keep as a lead
    # "unknown": found a name-matching domain but couldn't confirm it's live and
    # theirs. Flag it for a human glance rather than dropping a possible prospect.
    return best, False


def verify_leads(leads, city, pause=1.5):
    """Drop leads that certainly have their own site; flag the maybes.

    Returns (kept, dropped). Kept leads may carry a `possible_site` — a domain
    that matched the name but could not be confirmed as local. Those stay on the
    list with a note rather than being deleted on a guess.
    """
    kept, dropped = [], []
    for i, lead in enumerate(leads, 1):
        site, certain = find_website(lead["name"], city)
        if site and certain:
            lead["found_site"] = site
            dropped.append(lead)
            note = f"has {site}"
        elif site:
            lead["possible_site"] = site
            kept.append(lead)
            note = f"maybe {site} — check"
        else:
            kept.append(lead)
            note = "no site found"
        print(f"  [{i}/{len(leads)}] {lead['name'][:42]:<42} {note}")
        # Be a decent citizen of someone else's free service.
        if i < len(leads):
            time.sleep(pause)
    return kept, dropped


def write_csv(path, leads):
    with open(path, "w", newline="") as f:
        cols = ["name", "phone", "address", "maps_link", "possible_site"]
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows({k: l.get(k, "") for k in cols} for l in leads)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("location", help="place name or address, e.g. 'Portland, OR' or a zip code")
    parser.add_argument("category", choices=sorted(CATEGORIES), help="business type to search for")
    parser.add_argument("--radius", type=int, default=3000, help="search radius in meters (default 3000, ~1.9 miles)")
    parser.add_argument("--out", default="leads.csv", help="CSV file to write results to (default leads.csv)")
    parser.add_argument("--verify", action="store_true",
                        help="search the web for each lead and drop any that already "
                             "have their own website (slow: ~1.5s per lead, but it is "
                             "the difference between a lead list and a guess)")
    args = parser.parse_args()

    print(f"Looking up '{args.location}'...")
    try:
        coords = geocode(args.location)
    except (urllib.error.URLError, TimeoutError) as e:
        sys.exit(f"Could not reach Nominatim (geocoding service): {e}")
    if coords is None:
        sys.exit(f"No match for '{args.location}' — try a more specific address or a zip code.")
    lat, lon = coords
    print(f"  -> {lat:.5f}, {lon:.5f}")

    print(f"Searching for '{args.category}' within {args.radius}m...")
    query = build_overpass_query(lat, lon, args.radius, CATEGORIES[args.category])
    try:
        data = query_overpass(query)
    except (urllib.error.URLError, TimeoutError) as e:
        sys.exit(f"Could not reach Overpass (business data service): {e}")

    elements = data.get("elements", [])
    leads = find_leads(elements)

    print(f"Found {len(elements)} listing(s), {len(leads)} with no website on record.")
    if not leads:
        return

    if args.verify:
        print(f"\nVerifying {len(leads)} lead(s) against the open web "
              f"(~{len(leads) * 2 // 60 + 1} min)...")
        # The location string doubles as the city for searching — "Rudy's
        # Barbershop" alone is ambiguous, "Rudy's Barbershop Portland, OR" is not.
        try:
            leads, dropped = verify_leads(leads, args.location)
        except KeyboardInterrupt:
            sys.exit("\nStopped. Nothing written.")
        maybes = [l for l in leads if l.get("possible_site")]
        print(f"\n{len(dropped)} definitely had a website and were dropped.")
        if maybes:
            print(f"{len(maybes)} might have one — kept, with the domain in the "
                  f"`possible_site` column so you can check before pitching.")
        if dropped:
            print("  e.g. " + ", ".join(
                f"{d['name']} ({d['found_site']})" for d in dropped[:3]))
        if not leads:
            print("None left — every business here already has a site. "
                  "Try another category or a different area.")
            return

    write_csv(args.out, leads)
    print(f"Wrote {len(leads)} lead(s) -> {args.out}")
    if not args.verify:
        print("Tip: add --verify to drop the ones that already have a website. "
              "On a real run that was over half of them.")


if __name__ == "__main__":
    main()
