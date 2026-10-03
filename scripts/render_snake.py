#!/usr/bin/env python3
"""Render a decorative, looping snake over the verified contribution calendar.

The snake never consumes, recolors or changes contribution cells. Its motion is
an illustration, not an additional statistic. SVG uses SMIL without JavaScript,
external resources or foreignObject. Reduced motion reveals a still snake.
"""

import argparse
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from render_activity import (BG, INK, LAVENDER, LEVELS, LINE, MINT, MUTED,
                             NS, PANEL, ROOT, calendar_weeks, date_range,
                             load_snapshot, node, number, rect, text)


SEGMENTS = 26
SEGMENT_DELAY = 0.020
HEAD_RADIUS = 9


def layout(data, mobile):
    """Separate layout geometry so both the SVG and integrity tests use it."""
    weeks = calendar_weeks(data)
    width, height = (720, 432) if mobile else (1200, 300)
    if mobile:
        split = math.ceil(len(weeks) / 2)
        chunks = (weeks[:split], weeks[split:])
        geometry = [(66, 139, 654, 13), (66, 293, 654, 13)]
        cell = 10
    else:
        chunks = (weeks,)
        geometry = [(86, 139, 1114, 17)]
        cell = 13
    grids = []
    for group, (left, top, right, pitch_y) in zip(chunks, geometry):
        pitch_x = (right - left) / max(1, len(group) - 1)
        grids.append({"weeks": group, "left": left, "right": right, "top": top,
                      "bottom": top + 6 * pitch_y, "pitch_x": pitch_x,
                      "pitch_y": pitch_y, "cell": cell})
    return width, height, grids


def snake_points(grids):
    """A closed serpentine route with no teleport at the loop boundary."""
    points = []
    for index, grid in enumerate(grids):
        left, right, top = grid["left"], grid["right"], grid["top"]
        starts_right = index % 2 == 1
        if index:
            previous = grids[index - 1]
            # The mobile snake crosses the gap on a clear outer rail.
            rail = right + 20 if starts_right else left - 20
            points.extend([(rail, previous["bottom"]), (rail, top)])
        for row in range(7):
            y = top + row * grid["pitch_y"]
            forward = (row % 2 == 0) != starts_right
            start, end = (left, right) if forward else (right, left)
            points.extend([(start, y), (end, y)])
    first, last = grids[0], grids[-1]
    if len(grids) == 1:
        points.extend([(last["right"] + 20, last["bottom"]),
                       (last["right"] + 20, last["bottom"] + 12),
                       (first["left"] - 20, last["bottom"] + 12)])
    else:
        points.append((first["left"] - 20, last["bottom"]))
    points.append((first["left"] - 20, first["top"]))
    # The final connection to point zero has the same tangent as the first row.
    return points


def rounded_route(points, radius=6):
    """Round every corner using quadratic curves with matching line tangents."""
    if len(points) < 4 or len(set(points)) != len(points):
        raise ValueError("Snake route must have distinct points and form a loop")
    corners = []
    for i, point in enumerate(points):
        before, after = points[i - 1], points[(i + 1) % len(points)]
        incoming = math.dist(before, point)
        outgoing = math.dist(point, after)
        if not incoming or not outgoing:
            raise ValueError("Snake route contains a zero-length edge")
        cut = min(radius, incoming / 2, outgoing / 2)
        entry = tuple(point[j] + (before[j] - point[j]) * cut / incoming for j in (0, 1))
        leave = tuple(point[j] + (after[j] - point[j]) * cut / outgoing for j in (0, 1))
        corners.append((entry, point, leave))
    fmt = lambda p: f"{p[0]:.3f},{p[1]:.3f}"
    path = ["M" + fmt(corners[0][2])]
    for entry, control, leave in corners[1:] + corners[:1]:
        path.extend(("L" + fmt(entry), "Q" + fmt(control) + " " + fmt(leave)))
    path.append("Z")
    return " ".join(path)


def draw_cells(svg, grids):
    for index, grid in enumerate(grids):
        cells = node(svg, "g", id=f"calendar-{index + 1}")
        for column, week in enumerate(grid["weeks"]):
            for row, day in enumerate(week):
                x = grid["left"] + column * grid["pitch_x"] - grid["cell"] / 2
                y = grid["top"] + row * grid["pitch_y"] - grid["cell"] / 2
                if day is None:
                    rect(cells, x, y, grid["cell"], grid["cell"], "none", 2,
                         stroke=LINE, stroke_opacity=".35")
                    continue
                square = rect(cells, round(x, 3), round(y, 3), grid["cell"], grid["cell"],
                              LEVELS[day["level"]], 2,
                              data_date=day["date"].isoformat(), data_count=day["count"],
                              data_level=day["level"])
                node(square, "title").text = f"{day['date'].isoformat()}: {number(day['count'])} contribuciones"


def motion(parent, duration, lag):
    # Starting every segment at a different point in the previous iteration
    # keeps the body assembled from the first rendered frame, including t=0.
    begin = -(duration + 4.0 - lag)
    animation = node(parent, "animateMotion", dur=f"{duration}s", begin=f"{begin:.3f}s",
                     repeatCount="indefinite", rotate="auto", calcMode="paced")
    node(animation, "mpath", href="#snake-route")


def snake_shape(parent, index=None):
    if index is not None:
        fraction = (SEGMENTS - index) / SEGMENTS
        radius = 1.5 + fraction * 4.7
        color = LAVENDER if index > SEGMENTS * .46 else MINT
        node(parent, "circle", r=round(radius, 3), fill=color,
             stroke=BG, stroke_width="1.2", fill_opacity=round(.48 + .52 * fraction, 3))
        return
    # Wide head, contrasting eyes, and a bright outline remain visible on mint cells.
    node(parent, "ellipse", rx=9, ry=7, fill=MINT, stroke=INK, stroke_width="1.4")
    node(parent, "ellipse", cx=3, cy=0, rx=4, ry=5, fill="#bbffe9", fill_opacity=".6")
    for y in (-2.5, 2.5):
        node(parent, "circle", cx=4, cy=y, r=1.35, fill=BG)


def draw_snake(svg, grids, mobile, animated):
    if animated:
        moving = node(svg, "g", **{"class": "snake-motion", "aria-hidden": "true"})
        duration = 20 if mobile else 18
        for i in range(SEGMENTS, 0, -1):
            part = node(moving, "g", data_segment=i)
            snake_shape(part, i)
            motion(part, duration, i * SEGMENT_DELAY)
        head = node(moving, "g", data_segment="head")
        snake_shape(head)
        motion(head, duration, 0)
    rest = node(svg, "g", **{"class": "snake-rest", "aria-hidden": "true"})
    grid = grids[0]
    head_x = grid["left"] + (grid["right"] - grid["left"]) * .63
    for i in range(SEGMENTS, 0, -1):
        part = node(rest, "g", transform=f"translate({head_x - i * 7:.3f} {grid['top']})")
        snake_shape(part, i)
    head = node(rest, "g", transform=f"translate({head_x:.3f} {grid['top']})")
    snake_shape(head)


def make_snake_svg(data, mobile=False, animated=True):
    width, height, grids = layout(data, mobile)
    svg = ET.Element(f"{{{NS}}}svg", {"width": str(width), "height": str(height),
                     "viewBox": f"0 0 {width} {height}", "role": "img",
                     "aria-labelledby": "snake-title snake-description"})
    node(svg, "title", id="snake-title").text = "Contribution snake — Cristian Bravo"
    node(svg, "desc", id="snake-description").text = (
        "Un recorrido por mis contribuciones. La serpiente es una animación decorativa; "
        "los cuadrados conservan las fechas, cantidades y colores de actividad de GitHub. "
        f"{number(data['total_contributions'])} contribuciones, {date_range(data['_start'], data['_end'])}."
    )
    defs = node(svg, "defs")
    node(defs, "path", id="snake-route", d=rounded_route(snake_points(grids)))
    style = node(defs, "style")
    style.text = (
        ".snake-rest{display:none}"
        "@media(prefers-reduced-motion:reduce){.snake-motion{display:none}.snake-rest{display:inline}}"
        if animated else ".snake-rest{display:inline}"
    )
    rect(svg, .5, .5, width - 1, height - 1, BG, 20, stroke=LINE)
    margin = 28 if mobile else 36
    text(svg, margin, 27 if mobile else 31, "CONTRIBUTION SNAKE", 12, MINT, 550,
         mono=True, letter_spacing="1.8")
    text(svg, margin, 59 if mobile else 69, "Un recorrido por mis contribuciones",
         29 if mobile else 34, INK, 600, letter_spacing="-.6")
    text(svg, margin, 80 if mobile else 93, "Mi calendario de GitHub, en movimiento.",
         14 if mobile else 15, MUTED)
    if mobile:
        for index, grid in enumerate(grids):
            top = 92 + index * 154
            rect(svg, 28, top, 664, 139, PANEL, 12, stroke=LINE)
            actual = [day["date"] for week in grid["weeks"] for day in week if day]
            text(svg, 76, top + 22, f"{index + 1:02} / {date_range(min(actual), max(actual))}", 12, MUTED)
    else:
        rect(svg, 28, 109, 1144, 151, PANEL, 12, stroke=LINE)
        text(svg, 1164, 92, date_range(data["_start"], data["_end"]), 12, MUTED, text_anchor="end")
    draw_cells(svg, grids)
    draw_snake(svg, grids, mobile, animated)
    text(svg, margin, 412 if mobile else 284, f"Contribuciones del último año · @{data['username']}",
         12 if mobile else 13, MUTED)
    if not mobile:
        text(svg, width - margin, 284, "GITHUB / CYSTEMS", 11, MINT, 500, mono=True,
             text_anchor="end", letter_spacing="1")
    return ET.tostring(svg, encoding="unicode") + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "activity.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "assets")
    args = parser.parse_args()
    data = load_snapshot(args.input)
    outputs = {}
    for mobile in (False, True):
        for animated in (True, False):
            filename = "activity-snake" + ("-mobile" if mobile else "") + ("" if animated else "-static") + ".svg"
            content = make_snake_svg(data, mobile, animated)
            ET.fromstring(content)
            outputs[filename] = content
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in outputs.items():
        (args.output_dir / filename).write_text(content, encoding="utf-8")
    print(f"Rendered {len(outputs)} contribution-snake SVGs from verified calendar")


if __name__ == "__main__":
    main()
