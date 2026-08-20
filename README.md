# lead-finder

Finds local businesses that have no listed website, using free OpenStreetMap
data (Nominatim for geocoding + Overpass for business listings) — a starting
list for freelance web-design outreach. No API key or sign-up required.

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
  Requiring the town is load-bearing: without it "Polaris for Hair" matched
  polaris.com (snowmobiles) and "House of David" matched house.gov. Uncertainty
  always keeps the lead — a wrongly dropped one is invisible, a wrongly kept one
  costs one manual check.
- Directory listings (Yelp, Facebook, Booksy...) don't count as having a website.
  A shop whose only presence is a Yelp page is still a good lead.
