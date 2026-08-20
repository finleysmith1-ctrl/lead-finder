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

SITE_SYSTEM = """You build a single-page website for a small local business, to
be shown to the owner as a free sample.

Output ONE complete HTML file: <!doctype html> through </html>, with all CSS in a
<style> block. No JavaScript. No external requests of any kind — no font CDNs, no
image URLs, no analytics. It must render correctly opened straight off disk.

Design it for THIS business, not from a template. A barber and a florist should
not look alike: pick a palette, a type pairing and a layout that suit the trade.
Use CSS gradients, shapes and generous type instead of photographs, since there
are no images available.

Must include: the business name, what they do, where they are, the phone number
as a tel: link if given, opening hours if given, and one clear call to action.

🔴 INVENT NOTHING FACTUAL. No made-up reviews, no fake testimonials, no prices,
no staff names, no "established 1987", no awards. Where a real site would show
photographs, leave a tastefully styled placeholder block that says what belongs
there. This is shown to the actual owner — anything invented reads as sloppy and
kills the pitch.

Output only the HTML."""


def build_mockup(lead):
    """Return (html, cost). A real page, for a real business, with no invented facts."""
    sig = lead.get("signals") or {}
    facts = [f"Name: {lead.get('name')}",
             f"Trade: {(lead.get('search') or '').split('·')[0].strip() or 'local business'}",
             f"Address: {lead.get('address') or '(not known — omit the address section)'}",
             f"Phone: {lead.get('phone') or '(none known — use a contact form styled as a placeholder)'}"]
    if sig.get("cuisine"):
        facts.append(f"Cuisine: {sig['cuisine']}")
    if sig.get("takeaway"):
        facts.append("They do takeaway/delivery, so ordering should be prominent.")

    html, cost = _call([
        {"role": "system", "content": SITE_SYSTEM},
        {"role": "user", "content": "\n".join(facts)},
    ], SITE_MODEL, max_tokens=8000, temperature=0.9)

    # Models wrap HTML in a fence about half the time.
    m = re.search(r"```(?:html)?\s*(.+?)```", html, re.S)
    if m:
        html = m.group(1).strip()
    if "<!doctype" not in html[:200].lower() and "<html" not in html[:200].lower():
        raise RuntimeError("the model did not return a web page")

    # 🔴 Belt and braces on the no-external-requests rule. A page that phones home
    # is one that breaks when shown offline, and worse, one that could leak that
    # Finley opened it. Strip anything that reaches out.
    html = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r'<link\b[^>]*rel=["\']?stylesheet[^>]*>', "", html, flags=re.I)
    html = re.sub(r"@import\s+url\([^)]*\);?", "", html, flags=re.I)
    return html, cost
