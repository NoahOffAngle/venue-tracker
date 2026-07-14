#!/usr/bin/env python3
"""
Show Tracker scraper
====================
Reads scraper/venues.json, scrapes each venue, and writes data/events.json
(the file the web viewer reads). It also compares against the previous run and
reports what was ADDED, CHANGED, or REMOVED — that summary is what powers the
email alert.

Everything here is plain HTTP (no browser needed), so it runs fast and cheap on
GitHub Actions 4x/day.
"""

import os
import re
import sys
import json
import html
import pathlib
import datetime
import unicodedata

import requests
from bs4 import BeautifulSoup

# ---- Where things live -------------------------------------------------------
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "events.json"
CONFIG_FILE = ROOT / "scraper" / "venues.json"
SUMMARY_FILE = ROOT / "scraper" / "last_changes.txt"
GENRES_FILE = ROOT / "scraper" / "genres.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ShowTracker/1.0; personal use)"}
TIMEOUT = 30

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


# ---- Small helpers -----------------------------------------------------------
def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def make_id(venue, date, artist):
    """A stable fingerprint so the same show keeps the same id across runs."""
    return f"{slugify(venue)}-{date}-{slugify(artist)}"[:120]


# EDM keyword list, loaded from scraper/genres.json (edit that file to fix labels).
try:
    EDM_KEYWORDS = [k.lower() for k in json.loads(GENRES_FILE.read_text(encoding="utf-8"))["edm"]]
except Exception:
    EDM_KEYWORDS = []


# Phrases that mean the "supporting" text is really a description, not opening acts.
_DESCRIPTION_MARKERS = (
    "in partnership", "pre-show", "presented by", "performances by",
    "a benefit", "benefiting", "in celebration", "an evening with",
    "screening", "film ", "presented in",
)
# Connector words to strip from the front of a supporting-acts string.
_SUPPORT_PREFIX = re.compile(
    r"^(with(\s+very)?\s+special\s+guests?|with|w/|plus\s+special\s+guests?|plus|"
    r"featuring|feat\.?|special\s+guests?)\s+", re.I)


def tidy_support(support):
    """Clean up the supporting-acts text: drop descriptions, strip connectors."""
    s = (support or "").strip()
    if not s:
        return ""
    # If it was truncated with an ellipsis, it's almost always a description blurb.
    if s.endswith("…") or s.endswith("..."):
        return ""
    low = s.lower()
    if any(marker in low for marker in _DESCRIPTION_MARKERS):
        return ""
    # Strip leading "with / plus / special guest(s) / featuring" fluff.
    s = _SUPPORT_PREFIX.sub("", s).strip()
    return s


def detect_genre(artist, support):
    """Two buckets: 'EDM' if any known EDM name/keyword matches, else 'Live Music'."""
    text = f" {artist} {support} ".lower()
    for kw in EDM_KEYWORDS:
        if kw in text:
            return "EDM"
    return "Live Music"


def make_event(venue, date, time, artist, support, url):
    support = tidy_support(support)
    return {
        "id": make_id(venue, date, artist),
        "venue": venue,
        "list": "",            # which tab/group this venue belongs to (set in main)
        "date": date,          # "YYYY-MM-DD"
        "time": time,          # "7:30 PM"
        "artist": artist,
        "support": support,
        "genre": detect_genre(artist, support),
        "url": url,
    }


def clean(text):
    return html.unescape((text or "").strip())


def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def parse_time(raw):
    """'7:30 pm' / '7:00PM' -> '7:30 PM' (or '' if none found)."""
    m = re.search(r"(\d{1,2}):(\d{2})\s*([ap])\.?m\.?", raw, re.I)
    if not m:
        return ""
    return f"{int(m.group(1))}:{m.group(2)} {m.group(3).upper()}M"


# ---- Parser 1: AEG / Bowery Presents JSON feed (Under the K Bridge) -----------
def parse_aeg_json(venue, cfg):
    data = requests.get(cfg["url"], headers=HEADERS, timeout=TIMEOUT).json()
    site = cfg.get("site_url", "").rstrip("/")
    out = []
    for e in data.get("events", []):
        title = e.get("title", {}) or {}
        artist = clean(title.get("headlinersText"))
        support = clean(title.get("supportingText"))
        iso = e.get("eventDateTime")  # "2026-07-17T18:00:00" (local venue time)
        if not (artist and iso):
            continue
        try:
            dt = datetime.datetime.fromisoformat(iso)
        except ValueError:
            continue
        date = dt.strftime("%Y-%m-%d")
        time = dt.strftime("%-I:%M %p")
        url = f"{site}/events/detail?event_id={e.get('eventId')}" if site else cfg["url"]
        out.append(make_event(venue, date, time, artist, support, url))
    return out


# ---- Parser 2: Red Rocks (static HTML cards) ---------------------------------
def parse_redrocks(venue, cfg):
    soup = BeautifulSoup(fetch_html(cfg["url"]), "html.parser")
    out, seen = [], set()
    for card in soup.select("div.card.card-event"):
        title_el = card.select_one(".card-title")
        date_el = card.select_one(".date")
        if not (title_el and date_el):
            continue
        artist = clean(title_el.get_text(" ", strip=True))
        raw_date = date_el.get_text(" ", strip=True)   # "Tue, Jul 14, 7:30 pm"

        # Year isn't in the .date text, but the card carries data-month="July 2026"
        year_match = re.search(r"(20\d\d)", card.get("data-month", ""))
        md = re.search(r"([A-Za-z]{3,9})\s+(\d{1,2})", raw_date)
        if not md:
            continue
        month = MONTHS.get(md.group(1)[:3].lower())
        if not month:
            continue
        year = year_match.group(1) if year_match else str(datetime.date.today().year)
        date = f"{year}-{month:02d}-{int(md.group(2)):02d}"
        time = parse_time(raw_date)

        support_el = card.select_one("p.hide-mobile")
        support = clean(support_el.get_text(" ", strip=True)) if support_el else ""

        url = card.get("data-permalink") or cfg["url"]
        ev = make_event(venue, date, time, artist, support, url)
        if ev["id"] in seen:
            continue
        seen.add(ev["id"])
        out.append(ev)
    return out


# ---- Parser 3: Bill Graham Civic / Another Planet (static HTML) --------------
def parse_billgraham(venue, cfg):
    soup = BeautifulSoup(fetch_html(cfg["url"]), "html.parser")
    out, seen = [], set()
    for show in soup.select("h2.show-title"):
        artist = clean(show.get_text(" ", strip=True))
        container = show.find_parent("div", class_="detail-information") or show.parent
        if not container:
            continue

        date_el = container.select_one(".date-show")
        content = date_el.get("content", "") if date_el else ""  # "August 13, 2026 7:00pm"
        m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s*(20\d\d)", content)
        if not m:
            continue
        month = MONTHS.get(m.group(1)[:3].lower())
        if not month:
            continue
        date = f"{m.group(3)}-{month:02d}-{int(m.group(2)):02d}"
        time = parse_time(content)

        support_el = container.select_one(".support")
        support = clean(", ".join(support_el.stripped_strings)) if support_el else ""

        more = container.select_one("a.more-info")
        url = more.get("href") if more and more.get("href") else cfg["url"]
        ev = make_event(venue, date, time, artist, support, url)
        if ev["id"] in seen:
            continue
        seen.add(ev["id"])
        out.append(ev)
    return out


PARSERS = {
    "aeg_json": parse_aeg_json,
    "redrocks": parse_redrocks,
    "billgraham": parse_billgraham,
}


# ---- Load previous run so we can diff ----------------------------------------
def load_previous():
    if not DATA_FILE.exists():
        return {}
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return {e["id"]: e for e in data.get("events", [])}
    except Exception:
        return {}


def compare(previous, current):
    added = [e for i, e in current.items() if i not in previous]
    removed = [e for i, e in previous.items() if i not in current]
    changed = []
    for i, e in current.items():
        if i in previous:
            old = previous[i]
            fields = [k for k in ("date", "time", "artist", "support")
                      if (old.get(k) or "") != (e.get(k) or "")]
            if fields:
                changed.append((old, e, fields))
    return added, removed, changed


def build_summary(added, removed, changed, errors, first_run):
    lines = []
    if first_run:
        lines.append(f"Initial import: {len(added)} shows loaded.")
    else:
        def label(e):
            return f"{e['date']} — {e['artist']} @ {e['venue']} ({e['time'] or 'time TBA'})"
        if added:
            lines.append(f"ADDED ({len(added)}):")
            lines += [f"  + {label(e)}" for e in sorted(added, key=lambda x: x['date'])]
        if changed:
            lines.append(f"\nCHANGED ({len(changed)}):")
            for old, new, fields in sorted(changed, key=lambda x: x[1]['date']):
                bits = ", ".join(f"{f}: '{old.get(f) or '—'}' -> '{new.get(f) or '—'}'" for f in fields)
                lines.append(f"  ~ {label(new)}\n      {bits}")
        if removed:
            lines.append(f"\nREMOVED ({len(removed)}):")
            lines += [f"  - {label(e)}" for e in sorted(removed, key=lambda x: x['date'])]
        if not (added or changed or removed):
            lines.append("No changes since last run.")
    if errors:
        lines.append("\nWARNINGS:")
        lines += [f"  ! {msg}" for msg in errors]
    return "\n".join(lines)


def set_github_output(**kwargs):
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        for k, v in kwargs.items():
            f.write(f"{k}={v}\n")


def main():
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    venues = sorted(config["venues"], key=lambda v: v.get("rank", 999))

    previous = load_previous()
    first_run = len(previous) == 0

    scraped, errors, ok_venues = [], [], set()
    for v in venues:
        parser = PARSERS.get(v.get("parser"))
        if not parser:
            errors.append(f"{v['name']}: no parser named '{v.get('parser')}'")
            continue
        try:
            events = parser(v["name"], v)
            if not events:
                raise ValueError("0 events found (site layout may have changed)")
            for e in events:
                e["list"] = v.get("list", "")
            print(f"  {v['name']}: {len(events)} events")
            scraped.extend(events)
            ok_venues.add(v["name"])
        except Exception as ex:
            errors.append(f"{v['name']}: {ex}")
            print(f"  ERROR {v['name']}: {ex}", file=sys.stderr)

    # Safety net: if a venue failed this run, keep its PREVIOUS events instead of
    # letting the whole venue vanish from the tracker (and spam a "removed" alert).
    configured = {v["name"] for v in venues}
    for e in previous.values():
        if e["venue"] in configured and e["venue"] not in ok_venues:
            scraped.append(e)

    current = {e["id"]: e for e in scraped}
    added, removed, changed = compare(previous, current)

    out = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lists": config.get("lists", []),
        "events": sorted(current.values(), key=lambda e: (e["date"], e["time"], e["venue"])),
    }
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = build_summary(added, removed, changed, errors, first_run)
    SUMMARY_FILE.write_text(summary + "\n", encoding="utf-8")

    print("\n===== SUMMARY =====")
    print(summary)
    print(f"\nTotal shows now tracked: {len(current)}")

    has_changes = bool(added or removed or changed) and not first_run
    set_github_output(
        has_changes=str(has_changes).lower(),
        first_run=str(first_run).lower(),
        total=len(current),
    )


if __name__ == "__main__":
    main()
