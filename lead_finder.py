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
import sys
import urllib.error
import urllib.parse
import urllib.request

# Every business type we can search for, mapped to its OpenStreetMap tag(s).
# OSM tags them as free-form key=value pairs — e.g. a plumber is tagged
# craft=plumber, a restaurant is amenity=restaurant. Add more here as needed.
CATEGORIES = {
    "plumber": [("craft", "plumber")],
    "electrician": [("craft", "electrician")],
    "hair_salon": [("shop", "hairdresser")],
    "nail_salon": [("shop", "beauty")],
    "restaurant": [("amenity", "restaurant")],
    "cafe": [("amenity", "cafe")],
    "gym": [("leisure", "fitness_centre")],
    "dentist": [("amenity", "dentist")],
    "lawyer": [("office", "lawyer")],
    "accountant": [("office", "accountant")],
    "auto_repair": [("shop", "car_repair")],
}

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Nominatim's usage policy requires a real identifying User-Agent (not a
# browser string) so they can contact someone if a script misbehaves.
USER_AGENT = "lead-finder/0.1 (personal project; finley.smith.1@alpha.school)"


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
                "maps_link": (
                    f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
                    if lat is not None
                    else ""
                ),
            }
        )
    return leads


def write_csv(path, leads):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "phone", "address", "maps_link"])
        writer.writeheader()
        writer.writerows(leads)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("location", help="place name or address, e.g. 'Portland, OR' or a zip code")
    parser.add_argument("category", choices=sorted(CATEGORIES), help="business type to search for")
    parser.add_argument("--radius", type=int, default=3000, help="search radius in meters (default 3000, ~1.9 miles)")
    parser.add_argument("--out", default="leads.csv", help="CSV file to write results to (default leads.csv)")
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

    write_csv(args.out, leads)
    print(f"Wrote {len(leads)} lead(s) -> {args.out}")


if __name__ == "__main__":
    main()
