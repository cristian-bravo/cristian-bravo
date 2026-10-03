"""An integrated contribution calendar whose decorative snake consumes its cells.

API: animate_calendar(parent, weeks, x, y, pitch_x, pitch_y, cell,
                      *, id_prefix, animated=True) -> Element

Coordinates match render_activity.draw_calendar: x/y are the top-left corner
of the first cell. ``weeks`` contains seven Sunday-to-Saturday entries per
column, each a dict(date, count, level) or None for out-of-period padding.
This helper draws cells and motion only; callers retain month/day labels.
Use distinct id_prefix values for separate desktop/mobile calendar panels.

One 36-second loop: complete map 0-3s, consumption sweep 3-28s, rest until
30s, simultaneous restoration 30-33s, complete map 33-36s. The snake hides
before its motion resets. A separate unanimated copy is shown for reduced
motion, so every original color is restored even while SMIL is running.
No JavaScript, foreignObject, external dependencies or data mutation.
"""

from datetime import date
import math
import re
import xml.etree.ElementTree as ET


NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
LEVELS = ("#1c2a3d", "#235c54", "#368e78", "#60c6a0", "#91f5ce")
MINT, LAVENDER, INK, BG = "#91f5ce", "#c5b8ff", "#eef4f8", "#0b1220"
DURATION = 36.0
SWEEP_START = 3.0
SWEEP_SECONDS = 25.0
RESTORE_START = 30.0
RESTORE_END = 33.0
CONSUME_FADE = 0.10
BODY_SEGMENTS = 15


def element(parent, tag, **attributes):
    return ET.SubElement(parent, f"{{{NS}}}{tag}",
                         {key.replace("_", "-"): str(value) for key, value in attributes.items()})


def normalized_times(*seconds):
    if any(not 0 <= value <= DURATION for value in seconds):
        raise ValueError("Animation time falls outside the loop")
    if any(a > b for a, b in zip(seconds, seconds[1:])):
        raise ValueError("Animation times are not chronological")
    return ";".join(f"{value / DURATION:.8f}" for value in seconds)


def route_geometry(columns, x, y, pitch_x, pitch_y, cell):
    """Open, tangent-continuous row sweep; reset is hidden rather than teleported.

Semicircular turns reach outside the first/last cell centers by pitch_y/2.
All real cell centers lie on a straight portion of the route, so consumption
timings follow exact arc length rather than an approximation by cell index.
"""
    if type(columns) is not int or columns < 1:
        raise ValueError("Calendar must contain at least one week")
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (x, y, pitch_x, pitch_y, cell)):
        raise ValueError("Calendar geometry must be finite")
    if min(pitch_x, pitch_y, cell) <= 0 or cell > min(pitch_x, pitch_y):
        raise ValueError("Calendar cells overlap or have invalid dimensions")
    left, right = x + cell / 2, x + (columns - 1) * pitch_x + cell / 2
    top = y + cell / 2
    span, radius = right - left, pitch_y / 2
    turn_length = math.pi * radius
    path = [f"M {left:.6f} {top:.6f}"]
    for row in range(7):
        endpoint = right if row % 2 == 0 else left
        baseline = top + row * pitch_y
        path.append(f"L {endpoint:.6f} {baseline:.6f}")
        if row < 6:
            sweep = 1 if row % 2 == 0 else 0
            path.append(f"A {radius:.6f} {radius:.6f} 0 0 {sweep} {endpoint:.6f} {baseline + pitch_y:.6f}")
    return {"path": " ".join(path), "length": 7 * span + 6 * turn_length,
            "span": span, "turn_length": turn_length, "left": left,
            "right": right, "top": top, "radius": radius,
            "bounds": (left - radius, top, right + radius, top + 6 * pitch_y)}


def consumption_time(geometry, row, column, pitch_x):
    if not 0 <= row <= 6 or column < 0:
        raise ValueError("Invalid calendar position")
    horizontal = column * pitch_x
    if horizontal > geometry["span"] + 1e-6:
        raise ValueError("Calendar column falls outside the motion route")
    offset = horizontal if row % 2 == 0 else geometry["span"] - horizontal
    distance = row * (geometry["span"] + geometry["turn_length"]) + offset
    return SWEEP_START + SWEEP_SECONDS * distance / geometry["length"]


def checked_days(weeks):
    if not isinstance(weeks, list) or not weeks:
        raise ValueError("Calendar weeks are missing")
    seen = set()
    for week in weeks:
        if not isinstance(week, list) or len(week) != 7:
            raise ValueError("Each calendar week must have seven entries")
        for day in week:
            if day is None:
                continue
            if not isinstance(day, dict):
                raise ValueError("Invalid contribution day")
            raw = day.get("date")
            day_date = raw.isoformat() if isinstance(raw, date) else raw
            try:
                if not isinstance(day_date, str) or date.fromisoformat(day_date).isoformat() != day_date:
                    raise ValueError
            except ValueError:
                raise ValueError("Invalid contribution date") from None
            count, level = day.get("count"), day.get("level")
            if type(count) is not int or count < 0 or type(level) is not int or not 0 <= level <= 4:
                raise ValueError("Invalid contribution count or level")
            if (count == 0) != (level == 0) or day_date in seen:
                raise ValueError("Contribution colors or dates are inconsistent")
            seen.add(day_date)
    if not seen:
        raise ValueError("Contribution calendar is empty")


def draw_days(parent, weeks, x, y, pitch_x, pitch_y, cell, geometry,
              *, animate, include_data):
    for column, week in enumerate(weeks):
        for row, day in enumerate(week):
            attributes = {"x": round(x + column * pitch_x, 6),
                          "y": round(y + row * pitch_y, 6),
                          "width": cell, "height": cell, "rx": 3}
            if day is None:
                element(parent, "rect", **attributes, fill="none", stroke="#26364c", stroke_opacity=".35")
                continue
            day_date = day["date"].isoformat() if isinstance(day["date"], date) else day["date"]
            if include_data:
                attributes.update(data_date=day_date, data_count=day["count"], data_level=day["level"])
            square = element(parent, "rect", **attributes, fill=LEVELS[day["level"]])
            element(square, "title").text = f"{day_date}: {day['count']} contribuciones"
            if animate:
                when = consumption_time(geometry, row, column, pitch_x)
                square.set("data-consume-at", f"{when:.8f}")
                element(square, "animate", attributeName="opacity", dur=f"{DURATION:g}s",
                        values="1;1;0;0;1;1",
                        keyTimes=normalized_times(0, when, when + CONSUME_FADE, RESTORE_START, RESTORE_END, DURATION),
                        calcMode="linear", repeatCount="indefinite")


def animate_part(part, route_id, delay):
    start, end = SWEEP_START + delay, SWEEP_START + SWEEP_SECONDS + delay
    part.set("opacity", "0")
    element(part, "animate", attributeName="opacity", dur=f"{DURATION:g}s",
            values="0;0;1;1;0;0", calcMode="linear", repeatCount="indefinite",
            keyTimes=normalized_times(0, start - .15, start, end, end + .20, DURATION))
    motion = element(part, "animateMotion", dur=f"{DURATION:g}s", repeatCount="indefinite",
                     rotate="auto", calcMode="linear", keyPoints="0;0;1;1",
                     keyTimes=normalized_times(0, start, end, DURATION))
    element(motion, "mpath", href=f"#{route_id}")


def draw_snake(parent, route_id, geometry, cell):
    # Limit delay on very narrow calendars so the complete snake disappears
    # before the simultaneous restoration phase, including short test fixtures.
    delay_step = min(cell * .78 * SWEEP_SECONDS / geometry["length"], 1.2 / BODY_SEGMENTS)
    for index in range(BODY_SEGMENTS, 0, -1):
        fraction = (BODY_SEGMENTS + 1 - index) / (BODY_SEGMENTS + 1)
        size = cell * (.37 + .53 * fraction)
        part = element(parent, "g", data_segment=index)
        element(part, "rect", x=-size / 2, y=-size / 2, width=size, height=size,
                rx=min(size * .25, 3), fill=LAVENDER if index > 8 else MINT,
                stroke=BG, stroke_width="1", fill_opacity=.60 + .40 * fraction)
        animate_part(part, route_id, index * delay_step)
    head = element(parent, "g", data_segment="head")
    size = cell * 1.08
    element(head, "rect", x=-size / 2, y=-size / 2, width=size, height=size,
            rx=size * .27, fill=MINT, stroke=INK, stroke_width="1.2")
    for side in (-1, 1):
        element(head, "circle", cx=size * .22, cy=side * size * .23,
                r=max(.8, size * .08), fill=BG)
    animate_part(head, route_id, 0)


def animate_calendar(parent, weeks, x, y, pitch_x, pitch_y, cell, *, id_prefix, animated=True):
    """Draw the real calendar plus synchronized consumption motion into parent.

The path's maximum extra horizontal reach is pitch_y/2 beyond cell centers;
reserve that plus half the snake head (cell*.54 + .6px) at both sides.
Animated live cells carry data-date/count/level; the reduced-motion visual copy
has no duplicate data attributes, keeping the source calendar unambiguous.
"""
    if not isinstance(id_prefix, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", id_prefix):
        raise ValueError("id_prefix must be a unique safe SVG identifier")
    checked_days(weeks)
    geometry = route_geometry(len(weeks), x, y, pitch_x, pitch_y, cell)
    container = element(parent, "g", id=f"{id_prefix}-calendar")
    if not animated:
        draw_days(container, weeks, x, y, pitch_x, pitch_y, cell, geometry,
                  animate=False, include_data=True)
        return container
    live_class, still_class = f"{id_prefix}-live", f"{id_prefix}-still"
    route_id = f"{id_prefix}-route"
    defs = element(container, "defs")
    element(defs, "path", id=route_id, d=geometry["path"])
    element(defs, "style").text = (
        f".{still_class}{{display:none}}"
        f"@media(prefers-reduced-motion:reduce){{.{live_class}{{display:none}}.{still_class}{{display:inline}}}}"
    )
    live = element(container, "g", **{"class": live_class})
    draw_days(live, weeks, x, y, pitch_x, pitch_y, cell, geometry,
              animate=True, include_data=True)
    snake = element(live, "g", aria_hidden="true")
    draw_snake(snake, route_id, geometry, cell)
    still = element(container, "g", **{"class": still_class, "aria-hidden": "true"})
    draw_days(still, weeks, x, y, pitch_x, pitch_y, cell, geometry,
              animate=False, include_data=False)
    return container
