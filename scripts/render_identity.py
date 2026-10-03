#!/usr/bin/env python3
"""Render the compact profile identity with script-free SVG/CSS animation."""

from pathlib import Path
import xml.etree.ElementTree as ET

NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
ROOT = Path(__file__).resolve().parents[1]
MINT, LAVENDER, SAND = "#91f5ce", "#c5b8ff", "#f5c98b"
PHRASES = (("web", "Web & APIs", MINT), ("automation", "Automatización", LAVENDER), ("ai", "IA aplicada", SAND))


def add(parent, tag, **attrs):
    return ET.SubElement(parent, f"{{{NS}}}{tag}", {key.replace("_", "-"): str(value) for key, value in attrs.items()})


def text(parent, x, y, value, size=20, fill="#eef4f8", **attrs):
    element = add(parent, "text", x=x, y=y, font_size=size, fill=fill, **attrs)
    element.text = value
    return element


def phrase_animation(key, index, length, glyph_width):
    start = index * 100 / 3
    typed, held, erased = start + 10, start + 24, start + 31
    end = (index + 1) * 100 / 3
    width = round(length * glyph_width, 2)
    points = [(0, 0)]
    if start:
        points.append((start, 0))
    points += [(typed, width), (held, width), (erased, 0), (100, 0)]
    clip = "".join(f"{p:.4f}%{{width:{w}px}}" for p, w in points)
    # Cursor opacity changes only while the text is completely erased.
    cursor = []
    if start:
        cursor += [(0, 0, 0), (start - .001, 0, 0), (start, 0, 1)]
    else:
        cursor += [(0, 0, 1)]
    cursor += [(typed, width, 1), (held, width, 1), (erased, 0, 1)]
    if index < 2:
        cursor += [(end - .001, 0, 1), (end, 0, 0), (100, 0, 0)]
    else:
        cursor += [(100, 0, 1)]
    cursor_frames = "".join(f"{p:.4f}%{{transform:translateX({x}px);opacity:{opacity}}}" for p, x, opacity in cursor)
    return (
        f"@keyframes type-{key}{{{clip}}}"
        f"@keyframes cursor-{key}{{{cursor_frames}}}"
        f".clip-{key}{{animation:type-{key} 12s steps({length},end) infinite}}"
        f".cursor-{key}{{animation:cursor-{key} 12s steps({length},end) infinite}}"
    )


def diagram(parent, mobile, animated):
    # The entire mobile diagram stays in the available lower-right corner.
    transform = "translate(81.76 191.28) scale(.528)" if mobile else "translate(0 0)"
    diagram_group = add(parent, "g", transform=transform, aria_hidden="true")
    paths = add(diagram_group, "g", fill="none")
    add(paths, "circle", cx=991, cy=137, r=100, stroke="#26364c", stroke_width=1.5)
    add(paths, "circle", cx=991, cy=137, r=73, stroke="#26364c", stroke_dasharray="3 9")
    path = "M877 80h48v57h66v59h118"
    add(paths, "path", d=path, stroke="#406358", stroke_width=1.5)
    add(paths, "path", d=path, stroke=MINT, stroke_width=3, stroke_dasharray="10 20", **{"class": "signal"})
    outer = add(diagram_group, "g", **{"class": "orbit-outer"})
    add(outer, "path", d="M991 37a100 100 0 0 1 86.6 50", fill="none", stroke=LAVENDER, stroke_width=2.5, stroke_linecap="round", stroke_opacity=".6")
    add(outer, "circle", cx=991, cy=37, r=6, fill=LAVENDER)
    add(outer, "circle", cx=991, cy=237, r=5, fill=MINT)
    inner = add(diagram_group, "g", **{"class": "orbit-inner"})
    add(inner, "path", d="M918 137a73 73 0 0 1 36.5-63.22", fill="none", stroke=MINT, stroke_width=2, stroke_opacity=".65", stroke_linecap="round")
    add(inner, "circle", cx=918, cy=137, r=4, fill=MINT)
    add(inner, "circle", cx=1064, cy=137, r=3.5, fill=SAND)
    core = add(diagram_group, "g", **{"class": "core"})
    add(core, "rect", x=945, y=91, width=92, height=92, rx=21, fill="#142334", stroke="#4c7e69", stroke_width=1.5)
    add(core, "rect", x=951, y=97, width=80, height=80, rx=16, fill="none", stroke=MINT, stroke_opacity=".12")
    text(core, 991, 151, "</>", 37, MINT, text_anchor="middle", font_weight=650, **{"class": "mono"})
    if not mobile:
        add(diagram_group, "rect", x=845, y=64, width=64, height=32, rx=9, fill="#1c2035", stroke="#4d4565")
        text(diagram_group, 877, 85, "BUILD", 13, LAVENDER, text_anchor="middle", **{"class": "mono"})
        add(diagram_group, "rect", x=1079, y=180, width=61, height=32, rx=9, fill="#25251f", stroke="#5c543c")
        text(diagram_group, 1109, 201, "SHIP", 13, SAND, text_anchor="middle", **{"class": "mono"})


def render(mobile=False, animated=True):
    width, height = (720, 355) if mobile else (1200, 276)
    svg = ET.Element(f"{{{NS}}}svg", {
        "width": str(width), "height": str(height), "viewBox": f"0 0 {width} {height}",
        "role": "img", "aria-labelledby": "title desc",
    })
    add(svg, "title", id="title").text = "Cristian Bravo · Full Stack Developer · Ecuador"
    add(svg, "desc", id="desc").text = (
        "Cristian Bravo, creador de CYSTEMS en Ecuador. Full Stack Developer. "
        "Web y APIs, automatización e IA aplicada. "
        "El nombre permanece fijo; las especialidades aparecen con un efecto de escritura "
        "y un diagrama tecnológico muestra órbitas y flujo de datos."
        if animated else
        "Cristian Bravo, creador de CYSTEMS en Ecuador. Full Stack Developer. "
        "Web y APIs, automatización e IA aplicada. Versión estática sin animaciones."
    )
    defs = add(svg, "defs")
    style = add(defs, "style")
    css = "text{font-family:Segoe UI,Arial,sans-serif}.mono{font-family:Consolas,'Courier New',monospace}"
    type_size = 27 if mobile else 25
    glyph_width = type_size * .6
    if animated:
        css += (
            ".typed-static{display:none}"
            ".signal{animation:signal-flow 2.6s linear infinite}"
            ".orbit-outer{transform-origin:991px 137px;animation:orbit 12s linear infinite}"
            ".orbit-inner{transform-origin:991px 137px;animation:orbit 8s linear infinite reverse}"
            ".core{animation:float-core 3.6s ease-in-out infinite}"
            "@keyframes signal-flow{to{stroke-dashoffset:-60}}"
            "@keyframes orbit{to{transform:rotate(360deg)}}"
            "@keyframes float-core{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}"
        )
        for index, (key, phrase, _) in enumerate(PHRASES):
            clip = add(defs, "clipPath", id=f"type-{key}", clipPathUnits="userSpaceOnUse")
            add(clip, "rect", x=0, y=-35, width=len(phrase) * glyph_width if index == 0 else 0,
                height=48, **{"class": f"clip-{key}"})
            css += phrase_animation(key, index, len(phrase), glyph_width)
        css += (
            "@media(prefers-reduced-motion:reduce){"
            ".typed-line{display:none}.typed-static{display:block}"
            ".signal,.orbit-outer,.orbit-inner,.core{animation:none}"
            "[class^='clip-'],[class^='cursor-']{animation:none}}"
        )
    style.text = css
    add(svg, "rect", x=1, y=1, width=width - 2, height=height - 2, rx=24,
        fill="#0b1220", stroke="#26364c", stroke_width=2)
    if mobile:
        add(svg, "rect", x=36, y=34, width=43, height=33, rx=8, fill=MINT)
        text(svg, 58, 57, "cb.", 21, "#0b1220", text_anchor="middle", font_weight=800)
        text(svg, 96, 57, "CYSTEMS / ECUADOR", 20, "#9caec2", letter_spacing=2, **{"class": "mono"})
        name = text(svg, 34, 150, "Cristian ", 74, font_weight=750, letter_spacing=-3)
        role_x, role_y, role_size, spacing = 38, 205, 26, 1.6
        type_x, type_y = 68, 269
        add(svg, "path", d="M38 307h454", fill="none", stroke="#26364c")
        add(svg, "path", d="M38 307h454", fill="none", stroke=MINT, stroke_width=2,
            stroke_dasharray="10 20", **{"class": "signal"})
    else:
        add(svg, "path", d="M784 1v274", fill="none", stroke="#26364c")
        add(svg, "rect", x=40, y=34, width=39, height=30, rx=8, fill=MINT)
        text(svg, 59, 55, "cb.", 17, "#0b1220", text_anchor="middle", font_weight=800)
        text(svg, 94, 56, "CYSTEMS / ECUADOR", 15, "#9caec2", letter_spacing=2.4, **{"class": "mono"})
        name = text(svg, 38, 148, "Cristian ", 76, font_weight=750, letter_spacing=-3)
        role_x, role_y, role_size, spacing = 42, 196, 23, 2
        type_x, type_y = 72, 240
    add(name, "tspan", fill=MINT).text = "Bravo"
    add(name, "tspan", fill=LAVENDER).text = "."
    text(svg, role_x, role_y, "FULL STACK DEVELOPER", role_size, "#d4dfec",
         letter_spacing=spacing, **{"class": "mono"})
    text(svg, role_x, type_y, "›", type_size + 2, MINT, font_weight=600, **{"class": "mono"})
    if animated:
        typed = add(svg, "g", transform=f"translate({type_x} {type_y})", **{"class": "typed-line", "aria-hidden": "true"})
        for index, (key, phrase, color) in enumerate(PHRASES):
            group = add(typed, "g", clip_path=f"url(#type-{key})")
            text(group, 0, 0, phrase, type_size, color,
                 textLength=round(len(phrase) * glyph_width, 2), lengthAdjust="spacingAndGlyphs", **{"class": "mono"})
            add(typed, "rect", x=2, y=-type_size + 4, width=2.5, height=type_size,
                fill=color, opacity=1 if index == 0 else 0, **{"class": f"cursor-{key}"})
    static_phrase = "Web & APIs · Automatización" if mobile else "Web & APIs · Automatización · IA aplicada"
    text(svg, type_x, type_y, static_phrase, 23 if mobile else 21, "#9caec2",
         **{"class": "typed-static mono"})
    diagram(svg, mobile, animated)
    return ET.tostring(svg, encoding="unicode") + "\n"


def main():
    for mobile in (False, True):
        for animated in (True, False):
            name = "hero-compact" + ("-mobile" if mobile else "") + ("" if animated else "-static") + ".svg"
            output = render(mobile, animated)
            ET.fromstring(output)
            (ROOT / "assets" / name).write_text(output, encoding="utf-8")
            print(name)


if __name__ == "__main__":
    main()
