#!/usr/bin/env python3
import argparse
import dataclasses
import datetime as dt
import json
import os
from pathlib import Path
from typing import Iterable, List

import requests

DEFAULT_DISTRICT = os.getenv("NUTRISLICE_DISTRICT", "a2schools")
DEFAULT_MENU_TYPE = os.getenv("NUTRISLICE_MENU_TYPE", "lunch")
DEFAULT_DAYS_AHEAD = int(os.getenv("NUTRISLICE_DAYS_AHEAD", "28"))


@dataclasses.dataclass(frozen=True)
class School:
    slug: str
    name: str


@dataclasses.dataclass(frozen=True)
class MenuDay:
    date: dt.date
    entrees: List[str]
    foods: List[str]


def _escape_ics(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _daterange(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def _week_starts(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    current = start - dt.timedelta(days=start.weekday())
    while current <= end:
        yield current
        current += dt.timedelta(days=7)


def fetch_schools(district: str) -> List[School]:
    url = f"https://{district}.api.nutrislice.com/menu/api/schools/"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    schools = []
    for entry in data:
        slug = entry.get("slug")
        name = entry.get("name") or slug
        if slug:
            schools.append(School(slug=slug, name=name))
    return schools


def fetch_week_menu(district: str, school_slug: str, menu_type: str, date: dt.date) -> dict:
    url = (
        f"https://{district}.api.nutrislice.com/menu/api/weeks/school/{school_slug}/"
        f"menu-type/{menu_type}/{date.year}/{date.month:02d}/{date.day:02d}/?format=json"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def parse_menu_day(day: dict) -> MenuDay | None:
    menu_items = day.get("menu_items") or []
    if not menu_items:
        return None

    entrees = []
    foods = []

    for item in menu_items:
        if item.get("is_station_header"):
            continue
        food = item.get("food")
        if not food:
            continue
        name = food.get("name")
        if not name:
            continue
        foods.append(name)
        category = (item.get("category") or "").lower()
        if category in {"entree", "main"}:
            entrees.append(name)

    if not foods:
        return None

    # Deduplicate while preserving order.
    def _dedupe(values: List[str]) -> List[str]:
        seen = set()
        output = []
        for value in values:
            if value not in seen:
                seen.add(value)
                output.append(value)
        return output

    entrees = _dedupe(entrees)
    foods = _dedupe(foods)
    date_value = dt.date.fromisoformat(day["date"])
    return MenuDay(date=date_value, entrees=entrees, foods=foods)


def build_calendar(school: School, menu_days: List[MenuDay], district: str) -> str:
    now = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//a2schools-cal//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for day in menu_days:
        summary = day.entrees[0] if day.entrees else "Lunch Menu"
        description = "Full menu:\n" + "\n".join(day.foods)
        uid = f"{school.slug}-{day.date.isoformat()}@{district}"
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{_escape_ics(uid)}",
                f"DTSTAMP:{now}",
                f"DTSTART;VALUE=DATE:{day.date.strftime('%Y%m%d')}",
                f"SUMMARY:{_escape_ics(summary)}",
                f"DESCRIPTION:{_escape_ics(description)}",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def write_calendar(path: Path, calendar_body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(calendar_body, encoding="utf-8")


def generate_calendars(
    district: str,
    menu_type: str,
    start_date: dt.date,
    end_date: dt.date,
    output_dir: Path,
) -> List[School]:
    schools = fetch_schools(district)
    for school in schools:
        menus: dict[dt.date, MenuDay] = {}
        for week_start in _week_starts(start_date, end_date):
            payload = fetch_week_menu(district, school.slug, menu_type, week_start)
            for day in payload.get("days", []):
                menu_day = parse_menu_day(day)
                if not menu_day:
                    continue
                if start_date <= menu_day.date <= end_date:
                    menus[menu_day.date] = menu_day
        menu_days = [menus[date] for date in sorted(menus)]
        calendar = build_calendar(school, menu_days, district)
        write_calendar(output_dir / f"{school.slug}.ics", calendar)
    return schools


def render_index(output_dir: Path, schools: List[School]) -> None:
    rows = "\n".join(
        """
      <li class="school-card" data-slug="{slug}" data-name="{name}">
        <div class="school-card__header">
          <h2>{name}</h2>
          <a class="ics-link" href="{slug}.ics">Download .ics</a>
        </div>
        <div class="school-card__actions">
          <a class="button" data-action="google" href="#">Google Calendar</a>
          <a class="button" data-action="outlook" href="#">Outlook</a>
          <a class="button" data-action="ical" href="#">iCal</a>
        </div>
      </li>
    """.strip().format(slug=school.slug, name=school.name)
        for school in schools
    )
    html = f"""<!DOCTYPE html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>School Lunch Calendars</title>
    <style>
      :root {{
        color-scheme: light;
        font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
        line-height: 1.6;
        color: #1f2937;
        background: #f3f4f6;
      }}

      * {{
        box-sizing: border-box;
      }}

      body {{
        margin: 0;
      }}

      main {{
        max-width: 960px;
        margin: 0 auto;
        padding: 48px 20px 64px;
      }}

      header {{
        margin-bottom: 32px;
      }}

      h1 {{
        font-size: clamp(2rem, 3vw, 2.75rem);
        margin-bottom: 12px;
        letter-spacing: -0.02em;
      }}

      p {{
        margin: 0;
        color: #4b5563;
        font-size: 1.05rem;
      }}

      .card {{
        background: #ffffff;
        border-radius: 16px;
        padding: 28px;
        box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08);
      }}

      .school-list {{
        list-style: none;
        padding: 0;
        margin: 32px 0 0;
        display: grid;
        gap: 18px;
      }}

      .school-card {{
        border: 1px solid #e5e7eb;
        border-radius: 14px;
        padding: 20px 22px;
        background: #f9fafb;
        display: grid;
        gap: 16px;
      }}

      .school-card__header {{
        display: flex;
        flex-direction: column;
        gap: 6px;
      }}

      .school-card h2 {{
        font-size: 1.25rem;
        margin: 0;
        color: #111827;
      }}

      .ics-link {{
        font-size: 0.95rem;
        color: #2563eb;
        text-decoration: none;
        font-weight: 600;
      }}

      .ics-link:hover {{
        text-decoration: underline;
      }}

      .school-card__actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
      }}

      .button {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 10px 16px;
        border-radius: 999px;
        background: #1d4ed8;
        color: #ffffff;
        text-decoration: none;
        font-weight: 600;
        font-size: 0.95rem;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
      }}

      .button:hover {{
        transform: translateY(-1px);
        box-shadow: 0 8px 18px rgba(37, 99, 235, 0.2);
      }}

      .button[data-action="outlook"] {{
        background: #0f6cbd;
      }}

      .button[data-action="ical"] {{
        background: #6b7280;
      }}

      footer {{
        margin-top: 36px;
        color: #6b7280;
        font-size: 0.9rem;
      }}
    </style>
  </head>
  <body>
    <main>
      <header>
        <h1>School Lunch Calendars</h1>
        <p>
          Subscribe once and your calendar will update automatically with the latest lunch
          menus. Use the buttons below for the most popular calendar apps or download the
          .ics file directly.
        </p>
      </header>
      <section class="card">
        <ul class="school-list">
          {rows}
        </ul>
      </section>
      <footer>
        Tip: Most calendar apps refresh subscriptions every few hours. If you just
        subscribed, give it a little time for new menus to appear.
      </footer>
    </main>
    <script>
      const buttons = document.querySelectorAll(".school-card");
      buttons.forEach((card) => {{
        const slug = card.dataset.slug;
        const name = card.dataset.name;
        const icsUrl = new URL(`${{slug}}.ics`, window.location.href).toString();
        card.querySelector('[data-action="google"]').href =
          `https://calendar.google.com/calendar/r?cid=${{encodeURIComponent(icsUrl)}}`;
        card.querySelector('[data-action="outlook"]').href =
          `https://outlook.live.com/calendar/0/addcal?url=${{encodeURIComponent(icsUrl)}}&name=${{encodeURIComponent(name)}}`;
        card.querySelector('[data-action="ical"]').href = `webcal://${{new URL(icsUrl).host}}${{new URL(icsUrl).pathname}}`;
      }});
    </script>
  </body>
</html>
"""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(html, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate ICS calendars from Nutrislice menus."
    )
    parser.add_argument("--district", default=DEFAULT_DISTRICT)
    parser.add_argument("--menu-type", default=DEFAULT_MENU_TYPE)
    parser.add_argument(
        "--days-ahead",
        type=int,
        default=DEFAULT_DAYS_AHEAD,
        help="Number of days to generate from today forward.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("public"),
        help="Directory to write ICS files and index.html.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    today = dt.date.today()
    end_date = today + dt.timedelta(days=args.days_ahead)
    schools = generate_calendars(
        district=args.district,
        menu_type=args.menu_type,
        start_date=today,
        end_date=end_date,
        output_dir=args.output_dir,
    )
    render_index(args.output_dir, schools)
    manifest = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "district": args.district,
        "menu_type": args.menu_type,
        "days_ahead": args.days_ahead,
        "schools": [dataclasses.asdict(school) for school in schools],
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
