# School Lunch Calendars

This project generates per-school iCalendar (ICS) files for Nutrislice lunch menus and publishes them to GitHub Pages on a daily schedule.

## How it works

* Fetches the list of schools from the Nutrislice API.
* For each school, pulls weekly lunch menus and builds one all-day calendar event per day.
* The event title is the entree list; the description includes every food item.
* Writes `public/<school>.ics`, an `index.html` listing, and a `manifest.json` summary.

## Configuration

The Nutrislice district is configured via environment variable so forks can point at their own district.

| Variable | Default | Description |
| --- | --- | --- |
| `NUTRISLICE_DISTRICT` | `a2schools` | District subdomain used by Nutrislice. |
| `NUTRISLICE_MENU_TYPE` | `lunch` | Menu type slug for Nutrislice. |
| `NUTRISLICE_DAYS_AHEAD` | `28` | Days ahead to generate. |

## Local usage

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python generate_ics.py --district a2schools --menu-type lunch --days-ahead 28
```

The generated calendars will be in `public/`.

## GitHub Pages

The workflow in `.github/workflows/publish.yml` runs daily and publishes the `public/` directory to the `gh-pages` branch. Configure GitHub Pages to use the `gh-pages` branch as the source.

## Forking for another district

1. Fork this repository.
2. In your fork, open **Settings → Pages** and set the source to the `gh-pages` branch.
3. Configure the district details as repository variables in **Settings → Secrets and variables → Actions → Variables**:
   * `NUTRISLICE_DISTRICT`: the Nutrislice subdomain for your district (for example `a2schools`).
   * `NUTRISLICE_MENU_TYPE`: the menu type slug to pull (`lunch` by default).
   * `NUTRISLICE_DAYS_AHEAD`: how many days ahead to publish (defaults to `28` in the workflow).
4. Run the “Publish lunch calendars” workflow manually once (Actions tab) or wait for the daily schedule.

The GitHub Actions workflow will use those variables on each run to generate and publish calendars for your district.

## Credit
Credit to original author [George Hotelling](https://github.com/georgeh)
