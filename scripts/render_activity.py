#!/usr/bin/env python3
"""Render the verified GitHub activity snapshot as self-contained SVG artwork.

Run from any directory: python scripts/render_activity.py
Uses only the Python standard library. The source schema is defined by
scripts/activity_data.py; missing or inconsistent calendar data is an error.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import xml.etree.ElementTree as ET


NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
ROOT = Path(__file__).resolve().parents[1]
FONT = "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
MONO = "ui-monospace, SFMono-Regular, Consolas, monospace"
BG = "#0b1220"
PANEL = "#121e30"
LINE = "#26364c"
INK = "#eef4f8"
MUTED = "#9caec2"
MINT = "#91f5ce"
LAVENDER = "#c5b8ff"
SAND = "#f5c98b"
EC = timezone(timedelta(hours=-5))
LEVELS = ("#1c2a3d", "#235c54", "#368e78", "#60c6a0", MINT)
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def node(parent: ET.Element, tag: str, **attrs: object) -> ET.Element:
    """ElementTree escapes every text and attribute value from the snapshot."""
    return ET.SubElement(parent, f"{{{NS}}}{tag}", {k.replace("_", "-"): str(v) for k, v in attrs.items()})


def text(parent: ET.Element, x: float, y: float, value: object, size: float = 16,
         color: str = INK, weight: int = 400, mono: bool = False, **attrs: object) -> ET.Element:
    el = node(parent, "text", x=x, y=y, fill=color, font_family=MONO if mono else FONT,
              font_size=size, font_weight=weight, **attrs)
    el.text = str(value)
    return el


def rect(parent: ET.Element, x: float, y: float, w: float, h: float,
         fill: str, rx: float = 0, **attrs: object) -> ET.Element:
    return node(parent, "rect", x=x, y=y, width=w, height=h, rx=rx, fill=fill, **attrs)


def rule(parent: ET.Element, x: float, y: float, length: float, color: str = LINE, **attrs: object) -> None:
    node(parent, "path", d=f"M{x} {y}h{length}", fill="none", stroke=color, **attrs)


def short_date(value: date) -> str:
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}"


def date_range(start: date, end: date) -> str:
    return f"{short_date(start)} — {short_date(end)}"


def number(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def integer(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def load_snapshot(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported activity schema_version")
    if not isinstance(data.get("username"), str) or not data["username"].strip():
        raise ValueError("Missing GitHub username")
    start, end = date.fromisoformat(data["date_from"]), date.fromisoformat(data["date_to"])
    if not 330 <= (end - start).days <= 377:
        raise ValueError("Expected a complete annual GitHub contribution calendar")
    updated = datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))
    if updated.tzinfo is None:
        raise ValueError("generated_at must include its UTC offset")
    daily = {}
    for entry in data["days"]:
        day = date.fromisoformat(entry["date"])
        count = integer(entry["count"], "day.count")
        level = integer(entry["level"], "day.level")
        if level > 4 or (count == 0) != (level == 0):
            raise ValueError(f"Invalid contribution level for {day}")
        if day in daily or not start <= day <= end:
            raise ValueError(f"Duplicate or out-of-period contribution date: {day}")
        daily[day] = {"date": day, "count": count, "level": level}
    if len(daily) != (end - start).days + 1:
        raise ValueError("Calendar contains missing dates; refusing to fabricate zero contributions")
    expected = {
        "total_contributions": sum(day["count"] for day in daily.values()),
        "active_days": sum(day["count"] > 0 for day in daily.values()),
        "last_30_days": sum(day["count"] for day in daily.values() if day["date"] >= end - timedelta(days=29)),
    }
    for key, value in expected.items():
        if integer(data[key], key) != value:
            raise ValueError(f"{key} does not match the source calendar")
    integer(data["public_repos"], "public_repos")
    data.update(_start=start, _end=end, _updated=updated.astimezone(EC), _daily=daily)
    return data


def calendar_weeks(data: dict) -> list[list[dict | None]]:
    day = data["_start"] - timedelta(days=(data["_start"].weekday() + 1) % 7)
    weeks = []
    while day <= data["_end"]:
        weeks.append([data["_daily"].get(day + timedelta(days=offset)) for offset in range(7)])
        day += timedelta(days=7)
    return weeks


def month_markers(weeks: list[list[dict | None]]) -> list[tuple[int, str]]:
    markers = []
    for index, week in enumerate(weeks):
        actual = [day["date"] for day in week if day]
        starts = [day for day in actual if day.day == 1]
        if starts:
            markers.append((index, MONTHS[starts[0].month - 1].capitalize()))
        elif index == 0 and actual:
            markers.append((index, MONTHS[actual[0].month - 1].capitalize()))
    # A partial first month can be only one column wide. Preserve the full
    # next month's label rather than let the two month names overlap.
    if len(markers) > 1 and markers[1][0] - markers[0][0] < 3:
        markers.pop(0)
    return markers


def draw_calendar(parent: ET.Element, weeks: list[list[dict | None]], x: float,
                  y: float, pitch_x: float, pitch_y: float, cell: float,
                  label_size: float) -> None:
    for index, label in month_markers(weeks):
        text(parent, x + index * pitch_x, y - 14, label, label_size, MUTED)
    for row, label in ((1, "Lun"), (3, "Mié"), (5, "Vie")):
        text(parent, x - 12, y + row * pitch_y + cell - 2, label,
             label_size - 1, MUTED, text_anchor="end")
    for column, week in enumerate(weeks):
        for row, day in enumerate(week):
            px, py = round(x + column * pitch_x, 2), round(y + row * pitch_y, 2)
            if day is None:
                # Out-of-period padding is visually distinct from a zero day.
                rect(parent, px, py, cell, cell, "none", 3, stroke=LINE, stroke_opacity=".35")
                continue
            square = rect(parent, px, py, cell, cell, LEVELS[day["level"]], 3)
            title = node(square, "title")
            suffix = "contribución" if day["count"] == 1 else "contribuciones"
            title.text = f"{short_date(day['date'])}: {number(day['count'])} {suffix}"


def legend(parent: ET.Element, right: float, y: float, size: float = 13,
           cell: float = 12, gap: float = 5) -> None:
    width = 5 * cell + 4 * gap
    start = right - 42 - width
    text(parent, start - 10, y + cell - 2, "Menos", size, MUTED, text_anchor="end")
    for index, color in enumerate(LEVELS):
        rect(parent, start + index * (cell + gap), y, cell, cell, color, 3)
    text(parent, right, y + cell - 2, "Más", size, MUTED, text_anchor="end")


def statistic(parent: ET.Element, x: float, y: float, width: float, height: float,
              value: int, label: str, detail: str, accent: str, mobile: bool) -> None:
    rect(parent, x, y, width, height, PANEL, 14, stroke=LINE)
    rule(parent, x + 20, y, 43, accent, stroke_width=2)
    font_size = 45 if mobile else 44
    if len(number(value)) >= 7:
        font_size = 39
    text(parent, x + 20, y + 48, number(value), font_size, INK, 650, letter_spacing="-1.7")
    text(parent, x + 21, y + 76, label, 17 if mobile else 15, INK, 550)
    text(parent, x + 21, y + 96, detail, 15 if mobile else 13, MUTED)
    # A tiny decorative data motif, independent of actual metric values.
    for index, height_ratio in enumerate((0.4, 0.7, 1)):
        bar_height = 15 * height_ratio
        rect(parent, x + width - 37 + index * 7, y + 44 - bar_height,
             3, bar_height, accent, 1.5, fill_opacity=".4")


def make_svg(data: dict, mobile: bool, animated: bool) -> str:
    width, height = (720, 920) if mobile else (1200, 620)
    svg = ET.Element(f"{{{NS}}}svg", {
        "width": str(width), "height": str(height), "viewBox": f"0 0 {width} {height}",
        "role": "img", "aria-labelledby": "activity-title activity-desc",
    })
    title = node(svg, "title", id="activity-title")
    title.text = f"Actividad en GitHub de {data['username']}"
    description = node(svg, "desc", id="activity-desc")
    description.text = (
        f"{number(data['total_contributions'])} contribuciones en el calendario anual de GitHub, "
        f"del {date_range(data['_start'], data['_end'])}; {number(data['active_days'])} días activos; "
        f"{number(data['last_30_days'])} contribuciones en los últimos 30 días; "
        f"{number(data['public_repos'])} repositorios públicos. "
        "Calendario diario real: mayor intensidad verde significa más contribuciones. "
        "Cada color corresponde al nivel de actividad proporcionado por GitHub."
    )
    defs = node(svg, "defs")
    gradient = node(defs, "linearGradient", id="surface", x2="1", y2="1")
    node(gradient, "stop", stop_color=PANEL)
    node(gradient, "stop", offset="1", stop_color=BG)
    if animated:
        style = node(defs, "style")
        style.text = (
            "@keyframes activity-flow{to{stroke-dashoffset:-56}}"
            ".activity-flow{animation:activity-flow 14s linear infinite}"
            "@media(prefers-reduced-motion:reduce){.activity-flow{animation:none}}"
        )
    rect(svg, 0.5, 0.5, width - 1, height - 1, "url(#surface)", 22, stroke=LINE)
    margin = 28 if mobile else 40
    overline_y = 36 if mobile else 40
    text(svg, margin, overline_y, "GITHUB / ACTIVIDAD REAL", 14, MINT, 500, mono=True, letter_spacing="1.5")
    text(svg, margin - 1, 85 if mobile else 92, "Actividad en GitHub",
         43 if mobile else 47, INK, 650, letter_spacing="-1.5")
    text(svg, margin, 113 if mobile else 122,
         f"@{data['username']} · Código y proyectos, día a día.",
         18 if mobile else 17, MUTED)
    if not mobile:
        rect(svg, 1008, 36, 152, 30, MINT, 15, fill_opacity=".08", stroke=MINT, stroke_opacity=".3")
        node(svg, "circle", cx=1026, cy=51, r=3.5, fill=MINT)
        text(svg, 1040, 56, "DATOS REALES", 11.5, MINT, 600, mono=True, letter_spacing=".6")
    metrics = (
        ("total_contributions", "Contribuciones", "último año · GitHub", MINT),
        ("active_days", "Días activos", "en el calendario anual", LAVENDER),
        ("last_30_days", "Contribuciones", "últimos 30 días", SAND),
        ("public_repos", "Repositorios", "públicos en GitHub", MINT),
    )
    for index, (key, label, detail, accent) in enumerate(metrics):
        if mobile:
            x, y, card_w, card_h = 28 + (index % 2) * 340, 137 + (index // 2) * 119, 324, 106
        else:
            x, y, card_w, card_h = 40 + index * 285, 148, 265, 113
        statistic(svg, x, y, card_w, card_h, data[key], label, detail, accent, mobile)
    weeks = calendar_weeks(data)
    if mobile:
        split = math.ceil(len(weeks) / 2)
        groups = (weeks[:split], weeks[split:])
        for index, group in enumerate(groups):
            panel_y = 382 + index * 222
            rect(svg, 28, panel_y, 664, 207, BG, 14, stroke=LINE)
            actual = [day["date"] for week in group for day in week if day]
            text(svg, 49, panel_y + 30, f"Calendario anual · {index + 1} / 2", 18, INK, 550)
            text(svg, 671, panel_y + 30, date_range(min(actual), max(actual)), 13, MUTED, text_anchor="end")
            draw_calendar(svg, group, 82, panel_y + 71, 21.5, 17.5, 14.5, 15)
        legend(svg, 686, 835, 15, 14, 6)
        rule(svg, 28, 861, 664)
        footer_y = 887
        update_label = "Actualizado"
    else:
        rect(svg, 40, 285, 1120, 253, BG, 16, stroke=LINE)
        text(svg, 64, 319, "Un año de contribuciones", 21, INK, 550)
        text(svg, 1136, 319, date_range(data["_start"], data["_end"]), 14, MUTED, text_anchor="end")
        pitch = min(19.5, 1020 / len(weeks))
        draw_calendar(svg, weeks, 99, 366, pitch, 18.5, 15, 14)
        text(svg, 64, 518, "CADA CUADRO REPRESENTA UN DÍA", 11.5, MUTED, 400, mono=True, letter_spacing=".8")
        legend(svg, 1136, 504, 13, 12, 5)
        rule(svg, 40, 562, 1120)
        footer_y = 591
        update_label = "Última actualización"
    # Only this decorative line moves. Calendar colors, bars and counts are static.
    rule(svg, margin, footer_y - 5, 28, LINE, stroke_width=2, stroke_linecap="round")
    rule(svg, margin, footer_y - 5, 28, MINT, stroke_width=2, stroke_linecap="round",
         stroke_dasharray="8 20", **({"class": "activity-flow"} if animated else {}))
    updated = data["_updated"]
    updated_label = f"{short_date(updated.date())} · {updated:%H:%M} EC"
    text(svg, margin + 40, footer_y, f"{update_label}: {updated_label}",
         14 if mobile else 13, MUTED)
    text(svg, width - margin, footer_y, "Fuente: GitHub", 14 if mobile else 13, MUTED, text_anchor="end")
    return ET.tostring(svg, encoding="unicode", xml_declaration=False) + "\n"


def clipped(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit - 1].rstrip() + "…"


def make_recent_svg(data: dict, mobile: bool) -> str:
    events = data.get("recent_public_activity", [])[:4]
    width = 720 if mobile else 1200
    row_height = 112 if mobile else 71
    height = 111 + max(1, len(events)) * row_height
    svg = ET.Element(f"{{{NS}}}svg", {
        "width": str(width), "height": str(height), "viewBox": f"0 0 {width} {height}",
        "role": "img", "aria-labelledby": "recent-title recent-desc",
    })
    title = node(svg, "title", id="recent-title")
    title.text = f"Actividad pública reciente de {data['username']}"
    description = node(svg, "desc", id="recent-desc")
    description.text = "Últimos eventos públicos disponibles en GitHub. " + "; ".join(
        f"{event['repo']}: {event['label']}, {event['created_at']}" for event in events
    )
    rect(svg, 0.5, 0.5, width - 1, height - 1, PANEL, 20, stroke=LINE)
    margin = 28 if mobile else 40
    text(svg, margin, 34, "GITHUB / MOVIMIENTOS RECIENTES", 13, MINT, 500,
         mono=True, letter_spacing="1")
    text(svg, margin, 72, "Lo último en mis repositorios", 29 if mobile else 28,
         INK, 600, letter_spacing="-.6")
    if not events:
        text(svg, margin, 126, "Sin eventos públicos recientes disponibles.", 18, MUTED)
    for index, event in enumerate(events):
        timestamp = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("Recent event timestamp is missing its UTC offset")
        timestamp = timestamp.astimezone(EC)
        top = 105 + index * row_height
        dot_x, content_x = margin + 8, margin + 31
        accent = (MINT, LAVENDER, SAND, MINT)[index]
        if index < len(events) - 1:
            node(svg, "path", d=f"M{dot_x} {top + 8}v{row_height}",
                 fill="none", stroke=LINE, stroke_width="1.5")
        node(svg, "circle", cx=dot_x, cy=top + 8, r=6, fill=PANEL, stroke=accent, stroke_width="1.5")
        node(svg, "circle", cx=dot_x, cy=top + 8, r=2, fill=accent)
        repo = event["repo"]
        own_prefix = data["username"] + "/"
        display_repo = repo[len(own_prefix):] if repo.startswith(own_prefix) else repo
        repo_text = text(svg, content_x, top + 15, clipped(display_repo, 48 if mobile else 69),
                         23 if mobile else 20, INK, 550)
        node(repo_text, "title").text = repo
        label_text = text(svg, content_x, top + 43, clipped(event["label"], 66 if mobile else 112),
                          18 if mobile else 15, MUTED)
        node(label_text, "title").text = event["label"]
        if mobile:
            text(svg, content_x, top + 73, f"{short_date(timestamp.date())} · {timestamp:%H:%M} EC",
                 16, accent)
        else:
            text(svg, width - margin, top + 15, short_date(timestamp.date()), 15, accent, text_anchor="end")
            text(svg, width - margin, top + 41, f"{timestamp:%H:%M} EC", 13, MUTED, text_anchor="end")
    return ET.tostring(svg, encoding="unicode", xml_declaration=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "activity.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "assets")
    args = parser.parse_args()
    snapshot = load_snapshot(args.input)
    rendered = {}
    for mobile in (False, True):
        for animated in (True, False):
            name = "activity" + ("-mobile" if mobile else "") + ("" if animated else "-static") + ".svg"
            output = make_svg(snapshot, mobile, animated)
            ET.fromstring(output)
            rendered[name] = output
        recent = make_recent_svg(snapshot, mobile)
        ET.fromstring(recent)
        rendered["activity-recent" + ("-mobile" if mobile else "") + ".svg"] = recent
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, output in rendered.items():
        (args.output_dir / name).write_text(output, encoding="utf-8")
    print(f"Rendered {len(rendered)} SVG dashboards from verified snapshot {args.input}")


if __name__ == "__main__":
    main()
