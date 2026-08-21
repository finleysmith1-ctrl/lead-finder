# sitesmith

Finds local businesses that have no listed website, using free OpenStreetMap
data (Nominatim for geocoding + Overpass for business listings) — a starting
list for freelance web-design outreach. No API key or sign-up required.

## Setup

```bash
git clone https://github.com/finleysmith1-ctrl/sitesmith.git
cd sitesmith
python3 app.py
```

Python 3 only — no pip install, no dependencies. Searching, the map and your
notes work immediately. Drafting pitches and building sample sites need a free
[OpenRouter](https://openrouter.ai/keys) key, which the app asks for on first
run and validates before saving. You pay OpenRouter directly for what you use:
roughly **4 cents per business** you pitch in full.

## The app

```bash
python3 app.py        # then open http://localhost:8420
```

A local web app: run a search, then work the list over time — mark each business
new / contacted / replied / won / dead, keep notes against each, export CSV.
State lives in `leads.json` (gitignored). Re-running a search merges new finds in
without touching statuses or notes you have already set.

Loopback only and no login: it holds your notes about real businesses, so it is
not meant to be reachable from the network.

## Working the list

- **Build their website** produces a complete, deliverable single-page site for
  the business: responsive, trade-specific design, their real opening hours,
  Call / Get directions / Email buttons, SEO tags and LocalBusiness structured
  data so Google reads it right, and a favicon — all self-contained, no external
  requests, nothing invented.
- **Download site (ready to host)** gives you a ZIP with `index.html`, a favicon,
  the pitch, and plain instructions to put it live free on Netlify in ~5 minutes.
- **Prep top 10** drafts a pitch and builds a sample site for your ten best
  unpitched leads in the background — so you show up ready, for about 40 cents.
- **Call sheet** (opens on your phone) lists the unpitched leads with a phone,
  best first, each with a tap-to-call button, a spoken opener, and one-tap
  outcome logging that saves straight back. Prints cleanly if you'd rather carry
  paper. Calling is the main channel; walking in is the backup.

## Command line

```bash
python3 lead_finder.py "Portland, OR" hair_salon
python3 lead_finder.py "97201" restaurant --radius 5000 --out portland_restaurants.csv
python3 lead_finder.py --help   # full list of business categories and options
```

Output is a CSV: name, phone, address, and a Google Maps link — for every
business found that has a name but no `website` tag on OpenStreetMap.

## Notes

- OSM coverage varies by area — sometimes dense, sometimes sparse. Treat
  results as a starting list, not an exhaustive one.
- Listings with no name are skipped (nothing to pitch to).
- A missing website *tag* isn't proof the business has no site — some just
  haven't been tagged on OSM. `--verify` (or the checkbox in the app) searches
  the web for each lead and either
  **drops** it (the name matches a domain AND the town appears in the same
  result — confident enough to bin) or
  **flags** it (name matches, town absent — kept, with the domain in
  `possible_site` so you can check).
  Then it goes one step further and **actually opens the candidate site**: a
  live page that mentions the business confirms they have a site (dropped); a
  parked/for-sale/dead domain means they have no working site (kept — and it's a
  sharp pitch angle); anything it can't confirm is flagged, never silently
  dropped. There's also a **Re-check for website** button on each lead to run
  this the moment before you pitch.

  Requiring the town is load-bearing: without it "Polaris for Hair" matched
  polaris.com (snowmobiles) and "House of David" matched house.gov. Uncertainty
  always keeps the lead — a wrongly dropped one is invisible, a wrongly kept one
  costs one manual check.
- Directory listings (Yelp, Facebook, Booksy...) don't count as having a website.
  A shop whose only presence is a Yelp page is still a good lead.
