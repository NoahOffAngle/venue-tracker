# 🎸 Show Tracker

A tiny self-updating tool that scrapes upcoming shows from music venue websites,
stores them in one file, and shows them in a filterable web page. It runs itself
4× a day using GitHub Actions — no server, no computer left on.

## How it fits together

```
GitHub Actions (free cloud timer, 4x/day)
        │  runs
        ▼
scraper/scrape.py  ──reads──►  scraper/venues.json   (which venues to track)
        │  writes
        ▼
data/events.json   (the "database")
        │  read by
        ▼
site/index.html    (the filterable viewer, embedded in Squarespace)
```

## One-time setup

1. **Put this folder in a GitHub repository** (GitHub Desktop is the easy way).
2. **Turn on Actions:** repo → *Actions* tab → enable workflows.
3. **Turn on the web page:** repo → *Settings → Pages* → Source = *Deploy from a
   branch* → branch `main`, folder `/ (root)` → Save. After a minute your page is at
   `https://<username>.github.io/<repo>/site/index.html`.
4. **Run it once now:** *Actions* tab → *Scrape venues* → *Run workflow*.
5. **(Optional) Email alerts:** add these repo *Secrets* (*Settings → Secrets and
   variables → Actions*):
   - `MAIL_USERNAME` – your Gmail address
   - `MAIL_PASSWORD` – a Gmail **App Password** (not your normal password)
   - `MAIL_TO` – where alerts should go
   If these aren't set, the tracker still works — it just skips the email.

## Adding or removing a venue

Edit `scraper/venues.json`. To add a venue that uses a website we already support,
copy a block and change the `name`/`url`. Supported `parser` values:

| parser | works for | url to use |
|--------|-----------|------------|
| `aeg_json`  | AEG / Bowery Presents venues | the venue's `aegwebprod…/events/<id>/events.json` feed |
| `redrocks`  | Red Rocks | the `/events/` page |
| `billgraham`| Another Planet (Bill Graham Civic) | the `/event-listing/` page |

A brand-new website layout needs a new parser added to `scrape.py` first.

## Changing the schedule

Edit the `cron` line in `.github/workflows/scrape.yml`. Times are in **UTC**.
Current setting: `0 0,6,12,18 * * *` (every 6 hours).

## Running it on your own computer (optional)

```
pip install -r scraper/requirements.txt
python scraper/scrape.py
```
