# lead-finder

Finds local businesses that have no listed website, using free OpenStreetMap
data (Nominatim for geocoding + Overpass for business listings) — a starting
list for freelance web-design outreach. No API key or sign-up required.

## Getting started

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
  haven't been tagged on OSM. Always double-check a candidate by hand
  (search their name) before reaching out.
