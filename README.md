# Chesapeake Fishing HQ — Free Public Fishing Website

A public, mobile-friendly website built from the existing **Baltimore + Mid-Atlantic Fishing Alerts** desktop app. It includes **all 78 app locations**, **31 Maryland public piers/docks**, species activity scores and the **blue crab index**.

**Source of ratings:** `scripts/baltimore_fishing_bot.py` is the original desktop application's scoring module (November 2026), including `score_location()` and `build_species_results()`. The GitHub Actions workflow runs `scripts/update_reports.py` to collect weather, tide and gauge data, converts it into public JSON, and publishes the site. No running Windows PC or Discord account is required.

## Publish it for free using GitHub Pages

1. Sign up at [GitHub](https://github.com/) if needed.
2. Create a **new PUBLIC repository** named `chesapeake-fishing-hq`. Select **Public** and do not initialize it with a README.
3. Extract this ZIP on your PC. **Upload the CONTENTS of its `public_site` folder** to your repository (not the ZIP itself). Easiest method: open the repository, choose **Add file → Upload files**, drag the `public_site` folder contents into the file upload area, commit to `main`. **IMPORTANT:** GitHub's browser uploader may not preserve hidden `.github` folders when drag-and-dropping on some platforms. If you don't see `.github/workflows/publish.yml` in the repository after upload, add the workflow using **Add file → Create new file** and paste the ZIP's `.github/workflows/publish.yml` into that path. A Git client (GitHub Desktop) correctly preserves hidden files.
4. In your repository, go to **Settings → Pages → Build and deployment → Source → GitHub Actions**.
5. Open the **Actions** tab → **Update fishing reports and publish public website** → **Run workflow**. (The workflow may also run immediately after the first push to `main`.)
6. When the deployment succeeds, **Settings → Pages → Visit site** shows your public website. Usually your URL is `https://YOUR-USERNAME.github.io/chesapeake-fishing-hq/`.
7. Reports refresh about every **3 hours** automatically when the scheduled GitHub Action runs. Check the last-updated label on the site. Scheduled runs may be delayed.

### Optional NWS contact email

For better identification when calling the US National Weather Service API, open repository **Settings → Secrets and variables → Actions → Variables** and create a variable named `WEBSITE_CONTACT_EMAIL` with a public contact email that you are comfortable being visible. A public contact value is optional. **Never put a Discord webhook URL here.**

### Preview on your computer

The HTML dashboard runs on a local web server (double-clicking `index.html` via `file://` will not load its JSON because of browser restrictions):

```bash
cd public_site/site
python -m http.server 8000
```

Then open `http://localhost:8000/`. A fresh ZIP starts with **no live ratings** until the first cloud update. Its location directory and map already work.

### Refresh once on your computer (optional)

```bash
cd public_site
python scripts/update_reports.py
cd site
python -m http.server 8000
```

Use Python 3.11 or newer with access to the internet. The refresh uses only Python's standard library, no pip install.

## Site features

- 78 fishing spots and 31 specifically labeled Maryland public piers / docks
- Browse all, Maryland piers, or locations supporting blue crab
- Search by pier, town, waterway or species; sort by fish or crab activity
- Leaflet + OpenStreetMap map, location details, link to directions
- 0–100 fishing score; per-species score, including blue crab where available
- Current/recent weather, wind, rain chance, pressure, USGS streamflow, NOAA regional tides, NWS alerts where providers return data
- Source links, closures/access notes, score reasons, visible update timestamp
- Mobile-ready layout; no login, Discord account, paid hosting, or background PC required

## IMPORTANT: Public/private separation

**DO NOT upload the old desktop ZIP, `config.ini`, any Discord webhook URL, state folder, or log files to the public repository.** This packaged website deliberately excludes all of them. The only original app file included is the public-data scoring Python module. A `.gitignore` is included as extra protection.

## Limits and safety

- The initial `site/data/reports.json` contains **no ratings**. New reports are generated on GitHub Actions. They are **not live before deployment**.
- All ratings are **heuristics**, not fish counts, catch guarantees, harvest permission, pier opening status, or official safety warnings.
- Some piers are partially closed, under repair, have fees, or have seasonal hours; verify with the park before visiting.
- Tide values can come from a **regional NOAA station**, not measurements at the exact fishing deck.
- Blue crab activity ratings do **not** determine legal crabbing seasons, gear restrictions, harvest limits, or licensing. See [Maryland blue crab rules](https://dnr.maryland.gov/fisheries/Pages/regulations/blue-crab.aspx).
- If data sources fail, missing scores are shown as unavailable. Partially sourced reports are labeled as such.
- GitHub scheduled Actions can be late or skipped, and GitHub disables scheduled workflows for public repositories after 60 days of inactivity. You may need to re-enable the workflow periodically; this is a limitation of free, scheduled GitHub hosting.
- GitHub Pages is public and is designed for static sites, not high-volume production commercial web services.
- Open-Meteo's free API is intended for **non-commercial use** and requires attribution; a sponsored or paid service may require upgrading its license or using a suitable alternative API. The website includes attribution.
- Standard OpenStreetMap public tiles have fair-use limits. For heavy traffic, use a dedicated tile provider.
- No custom domain is necessary. If desired, GitHub Pages supports custom domains, which must be purchased or owned separately.

## Files

| Path | Purpose |
| --- | --- |
| `site/index.html` | Public website |
| `site/assets/style.css` | Website styling and mobile layout |
| `site/assets/app.js` | Map, search, filters, location details |
| `site/data/locations.json` | Sanitized location directory (all 78) |
| `site/data/reports.json` | Public generated report data, initially empty |
| `scripts/baltimore_fishing_bot.py` | Original desktop scoring and data-source logic |
| `scripts/export_locations.py` | Rebuild location directory from original app |
| `scripts/update_reports.py` | Public data collector and report exporter |
| `.github/workflows/publish.yml` | Automatic refresh and GitHub Pages publish |
| `.gitignore` | Exclude private app configurations and local logs |

### Official technical references

- GitHub Pages: https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site
- Actions workflow: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- Open-Meteo: https://open-meteo.com/en/docs
- NOAA CO-OPS: https://api.tidesandcurrents.noaa.gov/api/prod/
- NWS API: https://www.weather.gov/documentation/services-web-api
