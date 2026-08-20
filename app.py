#!/usr/bin/env python3
"""
app.py — the lead finder as an actual app, in your browser.

    python3 app.py            then open http://localhost:8420

WHY THIS EXISTS: the CLI prints a CSV. A CSV is a file, not a tool — you cannot
see at a glance which leads you have already contacted, which ones need checking,
or which ones went anywhere. Prospecting is a list you work through over weeks,
and that needs somewhere to live.

Stdlib only, per this project's conventions — http.server, no framework. The
search engine itself is untouched: this imports lead_finder and calls the same
functions the command line does, so there is exactly one implementation of the
thing that matters.

State lives in leads.json next to this file. Gitignored: never commit scraped
business data.
"""

import json
import mimetypes
import os
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import lead_finder as LF

HERE = Path(__file__).parent
STORE = HERE / "leads.json"
STATIC = HERE / "static"
# 🔴 Above 1024. Ports below that are privileged — macOS refuses to bind one
# without root, so the original 842 crashed with a bare PermissionError on a
# normal Mac account while working fine on the server, which runs as root.
PORT = int(os.environ.get("PORT", "8420"))

# Where a lead is in the pipeline. Deliberately short — a status list nobody can
# hold in their head is a status list nobody updates.
STATUSES = ["new", "contacted", "replied", "won", "dead"]

_lock = threading.Lock()
_job = {"running": False, "done": 0, "total": 0, "stage": "", "log": [], "error": None}


# ------------------------------------------------------------------ storage

def load():
    try:
        return json.loads(STORE.read_text())
    except Exception:
        return {"leads": [], "searches": []}


def save(data):
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(STORE)          # atomic — a half-written file loses everything


def lead_key(lead):
    """Identity for de-duplication across repeated searches. Name plus address,
    because two salons can share a name and one salon can be re-found every time
    you re-run a search — neither should create a duplicate row."""
    return (lead.get("name", "").strip().lower() + "|"
            + lead.get("address", "").strip().lower())


# ------------------------------------------------------------------- search

def run_search(location, category, radius, verify):
    """Background worker. Writes progress into _job as it goes."""
    def step(stage, done=None, total=None, line=None):
        with _lock:
            _job["stage"] = stage
            if done is not None:
                _job["done"] = done
            if total is not None:
                _job["total"] = total
            if line:
                _job["log"].append(line)
                del _job["log"][:-200]

    try:
        step(f"Looking up {location}")
        coords = LF.geocode(location)
        if not coords:
            raise ValueError(f"Could not find '{location}'. Try a fuller address or a zip code.")
        lat, lon = coords

        step(f"Searching {category.replace('_', ' ')} within {radius}m")
        query = LF.build_overpass_query(lat, lon, radius, LF.CATEGORIES[category])
        data = LF.query_overpass(query)
        found = LF.find_leads(data.get("elements", []))
        step(f"{len(found)} with no website on record", total=len(found))

        if verify and found:
            step("Checking each one against the web", done=0, total=len(found))
            for i, lead in enumerate(found, 1):
                site, certain = LF.find_website(lead["name"], location)
                if site and certain:
                    lead["_drop"] = site
                elif site:
                    lead["possible_site"] = site
                step("Checking each one against the web", done=i,
                     line=f"{lead['name']} — " + (
                         f"has {site}" if site and certain else
                         f"maybe {site}" if site else "no site found"))
                if i < len(found):
                    time.sleep(1.4)     # be decent to a free service

        dropped = [l for l in found if l.get("_drop")]
        kept = [l for l in found if not l.get("_drop")]

        # Merge into the store, never clobbering a status you have already set.
        db = load()
        existing = {lead_key(l): l for l in db["leads"]}
        added = 0
        for l in kept:
            k = lead_key(l)
            if k in existing:
                # refresh the facts, keep the human's decisions
                existing[k].update({x: l.get(x, "") for x in
                                    ("phone", "address", "maps_link", "possible_site")})
            else:
                l.update({"status": "new", "note": "",
                          "found_at": time.strftime("%Y-%m-%d"),
                          "search": f"{category} · {location}"})
                db["leads"].append(l)
                added += 1
        db["searches"].insert(0, {
            "at": time.strftime("%Y-%m-%d %H:%M"), "location": location,
            "category": category, "radius": radius, "verified": bool(verify),
            "found": len(found), "added": added, "dropped": len(dropped),
        })
        del db["searches"][30:]
        save(db)

        with _lock:
            _job["stage"] = (f"Done — {added} new lead{'s' if added != 1 else ''}"
                             + (f", {len(dropped)} already had a website" if dropped else ""))
    except Exception as e:
        with _lock:
            _job["error"] = str(e) or e.__class__.__name__
    finally:
        with _lock:
            _job["running"] = False


# -------------------------------------------------------------------- server

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass                      # the default logger spams one line per request

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            return self._serve_static("index.html")
        if path.startswith("/static/"):
            return self._serve_static(path[len("/static/"):])
        if path == "/api/state":
            db = load()
            with _lock:
                job = dict(_job)
            return self._send(200, {
                "leads": db["leads"], "searches": db["searches"],
                "categories": sorted(LF.CATEGORIES), "job": job,
                "statuses": STATUSES,
            })
        if path == "/api/export":
            db = load()
            cols = ["name", "phone", "address", "status", "note", "possible_site", "maps_link"]
            rows = [",".join(cols)]
            for l in db["leads"]:
                rows.append(",".join(
                    '"' + str(l.get(c, "")).replace('"', '""') + '"' for c in cols))
            return self._send(200, "\n".join(rows), "text/csv; charset=utf-8")
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            body = self._body()
        except Exception:
            return self._send(400, {"error": "bad JSON"})

        if path == "/api/search":
            with _lock:
                if _job["running"]:
                    return self._send(409, {"error": "a search is already running"})
                _job.update({"running": True, "done": 0, "total": 0,
                             "stage": "starting", "log": [], "error": None})
            cat = body.get("category")
            if cat not in LF.CATEGORIES:
                with _lock:
                    _job["running"] = False
                return self._send(400, {"error": f"unknown category {cat!r}"})
            threading.Thread(target=run_search, daemon=True, args=(
                str(body.get("location", "")).strip(), cat,
                max(200, min(20000, int(body.get("radius") or 3000))),
                bool(body.get("verify")),
            )).start()
            return self._send(200, {"ok": True})

        if path == "/api/lead":
            db = load()
            key = body.get("key")
            for l in db["leads"]:
                if lead_key(l) == key:
                    if "status" in body and body["status"] in STATUSES:
                        l["status"] = body["status"]
                    if "note" in body:
                        l["note"] = str(body["note"])[:500]
                    save(db)
                    return self._send(200, {"ok": True, "lead": l})
            return self._send(404, {"error": "no such lead"})

        if path == "/api/forget":
            db = load()
            before = len(db["leads"])
            db["leads"] = [l for l in db["leads"] if lead_key(l) != body.get("key")]
            save(db)
            return self._send(200, {"ok": True, "removed": before - len(db["leads"])})

        return self._send(404, {"error": "not found"})

    def _serve_static(self, rel):
        # Untrusted path from a URL. Resolve and confirm it is still inside
        # static/ before opening anything.
        target = (STATIC / rel).resolve()
        if not str(target).startswith(str(STATIC.resolve())) or not target.is_file():
            return self._send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def main():
    # Loopback only. This holds a list of local businesses and your notes about
    # them — it has no login, so it must not be reachable from the network.
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except PermissionError:
        raise SystemExit(
            f"\n  Port {PORT} needs admin rights. Pick one above 1024:\n"
            f"      PORT=8420 python3 app.py\n")
    except OSError as e:
        raise SystemExit(
            f"\n  Could not start on port {PORT}: {e}\n"
            f"  Something else is probably using it. Try another:\n"
            f"      PORT=8421 python3 app.py\n")
    print(f"\n  Lead Finder running — open  http://localhost:{PORT}\n")
    print("  Ctrl+C to stop.\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")


if __name__ == "__main__":
    main()
