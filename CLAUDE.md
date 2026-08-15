# lead-finder

Python 3, standard library only (no dependencies). Finds local businesses
with no listed website via OpenStreetMap (Nominatim + Overpass), for
freelance web-dev client outreach.

## Run

    python3 lead_finder.py "<location>" <category> [--radius METERS] [--out FILE.csv]
    python3 lead_finder.py --help    # lists categories

## Test

No test suite yet — single-purpose script. Verify manually: run against a
known location/category and sanity-check the CSV.

## Conventions

- Stdlib only. Don't add a dependency (`requests`, `googlemaps`, etc.)
  without asking first and saying what it's for.
- Category-to-OSM-tag mapping lives in the `CATEGORIES` dict at the top of
  `lead_finder.py` — extend it there, not hardcoded elsewhere.
- Network failures should print a plain-English message, not a raw
  traceback (see the try/except in `main()`).
- Generated output (`*.csv`) is gitignored — never commit scraped data.
