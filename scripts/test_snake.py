"""Integrity, accessibility and continuous-motion checks for the contribution snake."""

from datetime import date, datetime, timedelta, timezone
import math
import re
import unittest
import xml.etree.ElementTree as ET

from render_activity import LEVELS, NS
from render_snake import (HEAD_RADIUS, SEGMENTS, layout, make_snake_svg,
                          rounded_route, snake_points)


def snapshot(length=371, start=date(2025, 9, 28)):
    days = {}
    for i in range(length):
        day = start + timedelta(days=i)
        count = i % 5
        days[day] = {"date": day, "count": count, "level": count}
    return {"username": "cristian-bravo", "_start": start,
            "_end": start + timedelta(days=length - 1), "_daily": days,
            "_updated": datetime(2026, 10, 3, tzinfo=timezone.utc),
            "total_contributions": sum(d["count"] for d in days.values())}


class SnakeTests(unittest.TestCase):
    def test_all_real_dates_counts_and_colors_survive_each_variant(self):
        data = snapshot()
        for mobile in (False, True):
            for animated in (False, True):
                with self.subTest(mobile=mobile, animated=animated):
                    root = ET.fromstring(make_snake_svg(data, mobile, animated))
                    cells = [n for n in root.iter() if n.get("data-date")]
                    self.assertEqual(len(cells), len(data["_daily"]))
                    self.assertEqual(len({n.get("data-date") for n in cells}), len(cells))
                    self.assertEqual(sum(int(n.get("data-count")) for n in cells), data["total_contributions"])
                    for cell in cells:
                        original = data["_daily"][date.fromisoformat(cell.get("data-date"))]
                        self.assertEqual(cell.get("fill"), LEVELS[original["level"]])
                        self.assertEqual(int(cell.get("data-count")), original["count"])
                        self.assertFalse(list(cell.findall(f"{{{NS}}}animate")))

    def test_route_is_closed_and_does_not_clip_snake_or_real_cells(self):
        for mobile in (False, True):
            for length in (365, 371, 373):
                with self.subTest(mobile=mobile, length=length):
                    width, height, grids = layout(snapshot(length), mobile)
                    points = snake_points(grids)
                    # Every segment is orthogonal; the smoothing curve stays
                    # in the convex hull of these points, including the loop.
                    for a, b in zip(points, points[1:] + points[:1]):
                        self.assertGreater(math.dist(a, b), 0)
                        self.assertTrue(a[0] == b[0] or a[1] == b[1])
                    for x, y in points:
                        self.assertGreaterEqual(x - HEAD_RADIUS, 0)
                        self.assertLessEqual(x + HEAD_RADIUS, width)
                        self.assertGreaterEqual(y - HEAD_RADIUS, 0)
                        self.assertLessEqual(y + HEAD_RADIUS, height)
                    self.assertTrue(rounded_route(points).endswith("Z"))
                    for grid in grids:
                        self.assertLess(grid["right"] + grid["cell"] / 2, width)
                        self.assertLess(grid["bottom"] + grid["cell"] / 2, height)

    def test_single_continuous_path_is_shared_by_all_delayed_body_parts(self):
        for mobile in (False, True):
            root = ET.fromstring(make_snake_svg(snapshot(), mobile, True))
            motions = root.findall(f".//{{{NS}}}animateMotion")
            self.assertEqual(len(motions), SEGMENTS + 1)
            begins = []
            for motion in motions:
                self.assertEqual(motion.find(f"{{{NS}}}mpath").get("href"), "#snake-route")
                self.assertEqual(motion.get("calcMode"), "paced")
                self.assertEqual(motion.get("repeatCount"), "indefinite")
                self.assertEqual(motion.get("dur"), "20s" if mobile else "18s")
                begins.append(float(motion.get("begin")[:-1]))
            self.assertEqual(len(set(begins)), SEGMENTS + 1)
            self.assertTrue(all(value < 0 for value in begins))
            self.assertAlmostEqual(max(begins) - min(begins), SEGMENTS * .020)

    def test_static_variants_have_no_animation_and_reduced_motion_has_fallback(self):
        for mobile in (False, True):
            still = make_snake_svg(snapshot(), mobile, False)
            self.assertNotIn("animateMotion", still)
            self.assertNotIn("snake-motion", still)
            moving = make_snake_svg(snapshot(), mobile, True)
            self.assertIn("prefers-reduced-motion:reduce", moving)
            self.assertIn(".snake-motion{display:none}", moving)
            self.assertIn(".snake-rest{display:inline}", moving)

    def test_embedded_image_has_no_scripts_external_assets_or_foreign_objects(self):
        root = ET.fromstring(make_snake_svg(snapshot(), True, True))
        self.assertEqual(root.get("role"), "img")
        for element in root.iter():
            self.assertNotIn(element.tag.split("}")[-1], ("script", "foreignObject", "image"))
            for attr, value in element.attrib.items():
                if attr.endswith("href"):
                    self.assertTrue(value.startswith("#"))
                self.assertFalse(re.match(r"^on[a-z]+$", attr))
        desc = root.find(f"{{{NS}}}desc").text
        self.assertIn("animación decorativa", desc)

    def test_rounded_loop_closes_at_its_initial_tangent_point(self):
        path = rounded_route([(0, 0), (100, 0), (100, 100), (0, 100)])
        start = re.search(r"^M([^ ]+)", path).group(1)
        end = path.split()[-2]
        self.assertEqual(start, end)
        with self.assertRaises(ValueError):
            rounded_route([(0, 0), (0, 0), (1, 1), (2, 2)])


if __name__ == "__main__":
    unittest.main()
