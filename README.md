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

## Using the viewer

- **Tabs** — one per list in `venues.json`, plus **Selected**.
- **Sub-tabs** — give venues an optional `"group"` and that tab gains a second row
  (`All` + one per group). A tab with fewer than two groups shows no sub-tabs.
- **Selected** — tick the box beside any show to drop it in this basket. It spans every
  tab, survives closing the browser, and has two export buttons:
  - *Copy for Google Sheets* — paste straight into a sheet (tab-separated).
  - *Download CSV* — for `File → Import` in Google Sheets, or Excel.

  Both export these columns: Date, Day, Time, Artist, Supporting Artists, Genre, Venue,
  Link, **Exported** — the last one being the day you pulled the list, so batches pasted
  into the same sheet on different days stay tellable apart.
- **Colours** — each venue has a colour (its dot, tag and the stripe down the left of
  each row). Click **Colours** to change them live; to make a change permanent on every
  device, copy the list it shows into `venues.json` as each venue's `"color"`.

The embed needs `allow="clipboard-write"` for the copy button to work inside Squarespace:

```html
<iframe src="https://noahoffangle.github.io/venue-tracker/site/index.html"
        style="width:100%; height:900px; border:0;"
        allow="clipboard-write" title="Show Tracker" loading="lazy"></iframe>
```

## How a show gets labelled EDM or Live Music

Strongest signal wins:

1. **Your own list** — `always_edm` / `always_live` in `scraper/genres.json`. Put a name
   in one of those and it sticks everywhere, overriding everything below. This is how you
   correct any mistake permanently.
2. **The venue told us** — either the venue's site publishes a genre, or the venue is
   single-genre (`"genre": "EDM"` in `venues.json`).
3. **The same artist at another venue** — if an act is known EDM at one venue, it's EDM
   everywhere.
4. **MusicBrainz** — the artist's tags are looked up in the open music database and
   scored electronic-vs-band. Results are cached in `scraper/artist_genres.json` so each
   artist is only looked up once.
5. **Keywords** — the `edm` list in `genres.json` (whole-word matching).
6. **The venue's usual leaning** — `"genre_default"` in `venues.json`, for places that are
   mostly one thing but not exclusively (e.g. a nightclub).
7. Otherwise, Live Music.

To fix a wrong label, add the artist to `always_edm` or `always_live` — that's it.

## Adding or removing a venue

Edit `scraper/venues.json`. To add a venue that uses a website we already support,
copy a block and change the `name`/`url`. Supported `parser` values:

| parser | works for | url to use |
|--------|-----------|------------|
| `aeg_json`  | AEG / AXS venues (K Bridge, Regency Ballroom) | the venue's `aegwebprod…/events/<id>/events.json` feed — find it in the page source as `data-file="…"` |
| `redrocks`  | Red Rocks | the `/events/` page |
| `billgraham`| Another Planet (Bill Graham Civic) | the `/event-listing/` page |
| `jsonld`    | Sites publishing schema.org Events (Emo's, Cow Palace) | the listing page |
| `seetickets`| See Tickets list widget (Concourse Project) | the calendar page |
| `rockhouse` | Etix / Rockhouse venues (Kingdom) | the `/events/` page |
| `festistack`| Festistack WordPress (Silo Houston) | the homepage |
| `silodallas`| Silo Dallas only (needs a headless browser) | the `/events` page |

A venue can also set `"user_agent"` if its host rejects unfamiliar clients, and
`"genre": "EDM"` to tag everything it hosts.

A brand-new website layout needs a new parser added to `scrape.py` first.

## Changing the schedule

Edit the `cron` line in `.github/workflows/scrape.yml`. Times are in **UTC**.
Current setting: `0 0,6,12,18 * * *` (every 6 hours).

## Running it on your own computer (optional)

```
pip install -r scraper/requirements.txt
python scraper/scrape.py
```
