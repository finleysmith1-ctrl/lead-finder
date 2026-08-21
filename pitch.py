#!/usr/bin/env python3
"""
pitch.py — writes the approach message, and builds a sample site to attach to it.

WHY THIS IS THE IMPORTANT FILE. A list of businesses is not a business. The work
that actually stops you is writing something specific to thirty different shops,
and the thing that actually wins the job is showing them a page rather than
describing one. Both are machine work; the judgement and the sending are not.

🔴 THIS MODULE NEVER CONTACTS ANYONE. It writes a draft into the app for you to
read, edit and send from your own email or your own phone. A bot that messages
strangers is spam, and spam ends accounts and reputations. The split is the same
one used everywhere else in this system: the machine drafts, the human sends.

Needs an OpenRouter key. Without one the app still works completely — you just do
not get the two generated things. Put the key in either:
    export OPENROUTER_API_KEY=sk-or-...
    or a file called .openrouter-key next to this script (gitignored)
"""

import json
import os
import re
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
API = "https://openrouter.ai/api/v1/chat/completions"

# 🔴 NOT gemini-3.6-flash. It is a reasoning model and spends the whole token
# budget thinking: measured, a four-sentence pitch came back truncated at 64
# characters after burning 396 completion tokens, and OpenRouter's `reasoning`
# controls only hide that output — they still bill for it. 2.5-flash finishes the
# job for $0.00013, eleven times cheaper.
PITCH_MODEL = "google/gemini-2.5-flash"

# The mockup is different: it is the thing a real business owner looks at, and
# it is the whole reason this pitch beats an email. Worth Sonnet money.
SITE_MODEL = "anthropic/claude-sonnet-5"


def api_key():
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    f = HERE / ".openrouter-key"
    if f.exists():
        return f.read_text().strip()
    return ""


def _call(messages, model, max_tokens=2400, temperature=0.7):
    body = json.dumps({"model": model, "messages": messages,
                       "max_tokens": max_tokens, "temperature": temperature}).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read().decode())
    if d.get("error"):
        raise RuntimeError(str(d["error"])[:200])
    return (d["choices"][0]["message"]["content"] or "").strip(), \
           float(d.get("usage", {}).get("cost") or 0)


# ------------------------------------------------------------------- pitch

PITCH_SYSTEM = """You write short cold approach messages for a teenage freelance
web designer contacting small local businesses that have no website.

Voice: a real person, not an agency. Plain words, no jargon, no hype, no
"I hope this email finds you well", no "in today's digital landscape". Never
flatter. Never claim to have visited or eaten there — that is a lie and it is
obvious when it is wrong.

Rules:
- FOUR SENTENCES MAXIMUM. Anything longer does not get read.
- Say something specific and TRUE about this business — its trade, its street,
  the fact that it takes bookings by phone only. Never invent a detail.
- Name the concrete problem their missing website causes for a customer.
- One ask, and make it small: a reply, or two minutes, never "a meeting".
- No prices. No attachments mentioned unless told there is a sample.
- Sign off as Finley.

Output ONLY the message. No subject line, no preamble, no notes."""


def draft_pitch(lead, extra=""):
    """Return (message, cost). Purely a draft — nothing is sent."""
    sig = lead.get("signals") or {}
    facts = [f"Business: {lead.get('name')}",
             f"Type: {(lead.get('search') or '').split('·')[0].strip() or 'local business'}",
             f"Address: {lead.get('address') or 'not on record'}"]
    if lead.get("phone"):
        facts.append(f"Phone listed: {lead['phone']} (so customers must ring to book)")
    if sig.get("social"):
        facts.append("They have social media but no website to send people to.")
    if sig.get("hours"):
        facts.append("Their opening hours are listed publicly, so they keep details current.")
    if sig.get("cuisine"):
        facts.append(f"Cuisine: {sig['cuisine']}")
    if extra:
        facts.append(f"Finley adds: {extra}")

    msg, cost = _call([
        {"role": "system", "content": PITCH_SYSTEM},
        {"role": "user", "content": "\n".join(facts)},
    ], PITCH_MODEL, max_tokens=600, temperature=0.8)
    return msg, cost


# ------------------------------------------------------------------ mockup

SITE_SYSTEM = """You are a senior web designer building the ACTUAL website a small
local business will use — not a rough sample. It has to be good enough that the
owner says "yes, put it live." Take it seriously.

Output ONE complete HTML file: <!doctype html> through </html>, all CSS in a
<style> block. NO JavaScript at all — the nav can be a simple in-page anchor menu
that wraps on mobile, which needs none. No external requests of any kind — no
font CDNs, no image URLs, no map embeds, no analytics. It must render perfectly
opened straight off disk.

Make it genuinely EXCELLENT:
- A real single-page site with proper sections: a strong hero with the name and
  what they do, a services (or menu) section, an about paragraph, hours, how to
  find and contact them, and a footer. Use a sticky header with in-page nav.
- Fully responsive. It will mostly be viewed on a phone — design mobile-first and
  make sure it looks right at 375px wide and on a desktop.
- Design it for THIS trade. A barber, a florist, a law office and a taco truck
  must each look distinctly like themselves — commit to a palette, a characterful
  type pairing (system fonts only, but use weight, size and spacing to give it
  personality), and a layout that fits. Avoid a generic template look.
- Since there are no photos, build a beautiful photo-free design: CSS gradients,
  bold shapes, big type, texture. Where a photo genuinely belongs (a hero, a
  gallery), use a tasteful placeholder block clearly labelled "your photo here"
  so the owner knows exactly what to send you — never a fake stock image.
- ACTION BUTTONS that work everywhere: if a phone is given, a "Call now" button
  as <a href="tel:..."> and, on mobile, a sticky call bar is a nice touch. If an
  email is given, a "Get directions" link only if a directions URL is given, and
  an email link. These are the things that turn a visitor into a customer.
- SEO done right, because a great local site is one Google can read:
  * a <title> like "<Name> — <trade> in <town>" and a real <meta name=description>.
  * Open Graph tags (og:title, og:description, og:type=business.business) so a
    shared link looks right.
  * a favicon as an inline data-URI SVG (e.g. the business initial on a coloured
    tile) via <link rel="icon" href="data:image/svg+xml,...">. No external file.
  * a JSON-LD <script type="application/ld+json"> LocalBusiness block using ONLY
    the real name, address, phone, geo and hours you are given — this is the one
    place a <script> tag is allowed, and it must contain data, not code. Omit any
    field you were not given rather than inventing it.
- A favicon and touch-friendly 44px+ tap targets.

🔴 INVENT NOTHING FACTUAL. Use ONLY the details you are given. No made-up reviews,
testimonials, prices, staff names, years-in-business, awards, phone numbers or
email addresses. If you are given hours, show them exactly; if not, omit the
hours section. If you are given services for the trade, keep them generic and
true to the trade (e.g. a barber does "haircuts, beard trims") — never specific
claims you cannot know. This site is handed to the real owner; one invented
detail makes it worthless.

Output only the HTML, nothing else."""


def _human_hours(osm):
    """OSM hours like 'Mo-Fr 09:00-18:00; Sa 10:00-16:00' are unreadable to a
    normal person. Give the model the raw string and let it phrase it, but hand it
    over clearly labelled as the real, exact hours."""
    return osm.strip()


def build_mockup(lead, details=""):
    """Return (html, cost). The real deliverable site, with no invented facts.

    `details` is anything Finley has learned about the business — their real
    colours, services they mentioned, that they want online booking. It is passed
    through as ground truth the model may use.
    """
    sig = lead.get("signals") or {}
    trade = (lead.get("search") or "").split("·")[0].strip() or "local business"
    facts = [f"Business name: {lead.get('name')}",
             f"Trade: {trade}",
             f"Address: {lead.get('address') or '(not known — omit the address, keep a contact section)'}",
             f"Phone: {lead.get('phone') or '(none known — invite contact but invent no number)'}"]
    if sig.get("hours_text"):
        facts.append(f"REAL opening hours (show these exactly, phrased nicely): "
                     f"{_human_hours(sig['hours_text'])}")
    if sig.get("cuisine"):
        facts.append(f"Cuisine / speciality: {sig['cuisine']}")
    if sig.get("email"):
        facts.append(f"Email: {sig['email']}")
    if sig.get("takeaway"):
        facts.append("They do takeaway/delivery — make ordering or calling prominent.")
    if lead.get("maps_link"):
        facts.append(f"Directions link (use for a 'Get directions' button): "
                     f"{lead['maps_link']}")
    town = ""
    for part in (lead.get("address") or "").split():
        pass
    town = (lead.get("search") or "").split("·")[-1].strip()
    if town:
        facts.append(f"Town/area (for the title and SEO): {town}")
    if lead.get("lat") and lead.get("lon"):
        facts.append(f"Geo coordinates for the LocalBusiness schema: "
                     f"{lead['lat']}, {lead['lon']}")
    if details.strip():
        facts.append(f"What Finley knows about them (use as true): {details.strip()}")

    html, cost = _call([
        {"role": "system", "content": SITE_SYSTEM},
        {"role": "user", "content": "\n".join(facts)},
    ], SITE_MODEL, max_tokens=14000, temperature=0.9)

    # Models wrap HTML in a fence about half the time.
    m = re.search(r"```(?:html)?\s*(.+?)```", html, re.S)
    if m:
        html = m.group(1).strip()
    if "<!doctype" not in html[:200].lower() and "<html" not in html[:200].lower():
        raise RuntimeError("the model did not return a web page")

    # 🔴 Belt and braces on the no-external-requests rule. A page that phones home
    # breaks when shown offline and could leak that Finley opened it. Strip
    # anything that reaches out — but KEEP the JSON-LD block, which is structured
    # DATA (application/ld+json), not code, and is exactly what helps a local
    # business show up properly in Google. A ld+json script never executes and
    # never fetches, so it is safe to keep and valuable to have.
    html = re.sub(
        r'<script\b(?![^>]*type=["\']?application/ld\+json)[^>]*>.*?</script>',
        "", html, flags=re.S | re.I)
    html = re.sub(r'<link\b[^>]*rel=["\']?stylesheet[^>]*>', "", html, flags=re.I)
    html = re.sub(r"@import\s+url\([^)]*\);?", "", html, flags=re.I)
    return html, cost
