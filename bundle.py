#!/usr/bin/env python3
"""
bundle.py — package a finished website into a ready-to-hand-over ZIP.

Everything the client needs in one download: the site as index.html, plain
hosting instructions a beginner can follow, a favicon, and the pitch to send.
Kept in its own file so the multi-line text lives in normal triple-quoted strings
rather than being escaped through app.py's request handler.
"""

import io
import re
import zipfile

README = """{name} — website
{rule}

WHAT'S IN HERE
  index.html   the finished website — open it in any browser to see it
  favicon.svg  the little icon that shows in the browser tab
  pitch.txt    the message to send them (if you drafted one)

HOW TO PUT IT LIVE — free, about 5 minutes
  1. Go to  app.netlify.com/drop
  2. Drag this whole folder onto that page
  3. It goes live instantly at a free netlify.app link — send that to the owner
  4. Later, you can point their own domain (like joesbarbers.com) at it —
     Netlify walks you through it, no code needed

TO CHANGE ANYTHING
  It's all in index.html — text, colours, layout, everything. No build step and
  no dependencies. Edit it, drag the folder to Netlify again, done.

THE PHOTOS
  The grey "your photo here" blocks tell you exactly which images to ask the
  owner for. Drop their photos in and update index.html to point at them.
"""


def favicon_svg(name):
    """A simple coloured tile with the business's initial. Inline SVG, so it needs
    no external file and works the moment the site is opened."""
    init = (name.strip()[:1] or "?").upper().replace("&", "&amp;").replace("<", "")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="12" fill="#0d7a5f"/>'
        '<text x="32" y="45" font-size="38" font-family="sans-serif" '
        'font-weight="700" fill="#ffffff" text-anchor="middle">' + init + '</text></svg>'
    )


def make_zip(name, html, pitch=""):
    """Return (bytes, filename) for the download."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "site"
    readme = README.format(name=name, rule="=" * (len(name) + 10))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("index.html", html)
        z.writestr("README.txt", readme)
        z.writestr("favicon.svg", favicon_svg(name))
        if pitch:
            z.writestr("pitch.txt", pitch)
    return buf.getvalue(), f"{slug}-website.zip"
