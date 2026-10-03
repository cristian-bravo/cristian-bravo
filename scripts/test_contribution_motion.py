"""Verify calendar integrity and synchronization between snake and consumed cells."""

from copy import deepcopy
from datetime import date, timedelta
import unittest
import xml.etree.ElementTree as ET

from contribution_motion import (BODY_SEGMENTS, CONSUME_FADE, DURATION, LEVELS,
                                 NS, RESTORE_END, RESTORE_START, SWEEP_SECONDS,
                                 SWEEP_START, animate_calendar, consumption_time,
                                 route_geometry)


def weeks(columns=26):
    start = date(2026, 1, 4)
    result = []
    for column in range(columns):
        result.append([{"date": start + timedelta(days=column * 7 + row),
                        "count": (column + row) % 5, "level": (column + row) % 5}
                       for row in range(7)])
    return result


def svg():
    return ET.Element(f"{{{NS}}}svg")


def times(animation):
    return [float(part) * DURATION for part in animation.get("keyTimes").split(";")]


class ContributionMotionTests(unittest.TestCase):
    def test_consumption_matches_head_distance_in_both_row_directions(self):
        columns, px, py, cell = 26, 21.5, 17.5, 14.5
        geometry = route_geometry(columns, 82, 453, px, py, cell)
        self.assertAlmostEqual(consumption_time(geometry, 0, 0, px), SWEEP_START)
        self.assertAlmostEqual(consumption_time(geometry, 6, columns - 1, px), SWEEP_START + SWEEP_SECONDS)
        previous = -1
        for row in range(7):
            order = range(columns) if row % 2 == 0 else range(columns - 1, -1, -1)
            for column in order:
                when = consumption_time(geometry, row, column, px)
                self.assertGreater(when, previous)
                previous = when
        # Two adjacent centers are separated by exactly one horizontal pitch.
        travel = SWEEP_SECONDS * px / geometry["length"]
        self.assertAlmostEqual(consumption_time(geometry, 0, 1, px) - SWEEP_START, travel)
        self.assertAlmostEqual(consumption_time(geometry, 1, 0, px) - consumption_time(geometry, 1, 1, px), travel)

    def test_consumption_empties_each_cell_then_restores_every_color_together(self):
        root = svg()
        animate_calendar(root, weeks(), 82, 453, 21.5, 17.5, 14.5, id_prefix="mobile-a")
        cells = [node for node in root.iter() if node.get("data-date")]
        self.assertEqual(len(cells), 26 * 7)
        for square in cells:
            animation = square.find(f"{{{NS}}}animate")
            self.assertEqual(animation.get("attributeName"), "opacity")
            self.assertEqual(animation.get("values"), "1;1;0;0;1;1")
            schedule = times(animation)
            self.assertAlmostEqual(schedule[1], float(square.get("data-consume-at")), places=5)
            self.assertAlmostEqual(schedule[2] - schedule[1], CONSUME_FADE, places=5)
            self.assertAlmostEqual(schedule[3], RESTORE_START, places=5)
            self.assertAlmostEqual(schedule[4], RESTORE_END, places=5)
            self.assertEqual(square.get("fill"), LEVELS[int(square.get("data-level"))])

    def test_source_dates_counts_levels_unchanged_and_no_input_mutation(self):
        data = weeks()
        data[-1][-1] = None
        original = deepcopy(data)
        root = svg()
        animate_calendar(root, data, 99, 366, 19.5, 18.5, 15, id_prefix="desktop")
        self.assertEqual(data, original)
        source = {d["date"].isoformat(): d for week in data for d in week if d}
        cells = [n for n in root.iter() if n.get("data-date")]
        self.assertEqual(len(cells), len(source))
        self.assertEqual(len({n.get("data-date") for n in cells}), len(source))
        for square in cells:
            day = source[square.get("data-date")]
            self.assertEqual(int(square.get("data-count")), day["count"])
            self.assertEqual(int(square.get("data-level")), day["level"])

    def test_head_and_body_hide_before_restore_and_before_motion_reset(self):
        for columns in (1, 26, 53):
            with self.subTest(columns=columns):
                root = svg()
                animate_calendar(root, weeks(columns), 99, 366, 19.5, 18.5, 15, id_prefix="desktop")
                parts = [n for n in root.iter() if n.get("data-segment")]
                self.assertEqual(len(parts), BODY_SEGMENTS + 1)
                for part in parts:
                    fade = part.find(f"{{{NS}}}animate")
                    motion = part.find(f"{{{NS}}}animateMotion")
                    self.assertEqual(part.get("opacity"), "0")
                    self.assertLess(times(fade)[4], RESTORE_START)
                    self.assertEqual(fade.get("values").split(";")[-1], "0")
                    self.assertEqual(motion.get("keyPoints"), "0;0;1;1")
                    self.assertAlmostEqual(times(motion)[2] - times(motion)[1], SWEEP_SECONDS, places=5)

    def test_route_has_six_smooth_turns_and_fits_existing_calendar_margins(self):
        for columns, x, y, px, py, cell, width, height in (
            (53, 89, 236, min(20, 1056 / 53), 20, 16, 1200, 450),
            (27, 79, 320, 21.5, 19, 16, 720, 744),
            (26, 79, 510, 21.5, 19, 16, 720, 744),
        ):
            geometry = route_geometry(columns, x, y, px, py, cell)
            self.assertEqual(geometry["path"].count(" A "), 6)
            self.assertEqual(geometry["path"].count("M "), 1)
            self.assertNotIn("Z", geometry["path"])
            left, top, right, bottom = geometry["bounds"]
            radius = cell * .54 + .6
            self.assertGreater(left - radius, 0)
            self.assertGreater(top - radius, 0)
            self.assertLess(right + radius, width)
            self.assertLess(bottom + radius, height)

    def test_static_and_reduced_motion_show_complete_unanimated_calendar(self):
        static = svg()
        animate_calendar(static, weeks(), 82, 453, 21.5, 17.5, 14.5, id_prefix="static", animated=False)
        self.assertFalse(static.findall(f".//{{{NS}}}animate"))
        self.assertFalse(static.findall(f".//{{{NS}}}animateMotion"))
        self.assertEqual(len([n for n in static.iter() if n.get("data-date")]), 182)
        root = svg()
        animate_calendar(root, weeks(), 82, 453, 21.5, 17.5, 14.5, id_prefix="first")
        still = next(n for n in root.iter() if n.get("class") == "first-still")
        self.assertFalse(still.findall(f".//{{{NS}}}animate"))
        self.assertEqual(len(still.findall(f"{{{NS}}}rect")), 182)
        css = root.find(f".//{{{NS}}}style").text
        self.assertIn("prefers-reduced-motion:reduce", css)
        self.assertIn(".first-live{display:none}", css)
        self.assertIn(".first-still{display:inline}", css)

    def test_two_panels_have_disjoint_ids_and_local_motion_references(self):
        root = svg()
        for prefix in ("first", "second"):
            animate_calendar(root, weeks(), 82, 453, 21.5, 17.5, 14.5, id_prefix=prefix)
        ids = [n.get("id") for n in root.iter() if n.get("id")]
        self.assertEqual(len(ids), len(set(ids)))
        for node in root.findall(f".//{{{NS}}}mpath"):
            self.assertIn(node.get("href")[1:], ids)
        serialized = ET.tostring(root, encoding="unicode")
        ET.fromstring(serialized)
        self.assertNotIn("foreignObject", serialized)
        self.assertNotIn("<script", serialized)

    def test_invalid_dates_colors_and_overlapping_geometry_are_rejected(self):
        bad = weeks()
        bad[0][0]["count"] = 1
        with self.assertRaises(ValueError):
            animate_calendar(svg(), bad, 0, 0, 10, 10, 8, id_prefix="bad")
        with self.assertRaises(ValueError):
            route_geometry(26, 0, 0, 10, 10, 11)
        with self.assertRaises(ValueError):
            animate_calendar(svg(), weeks(), 0, 0, 10, 10, 8, id_prefix="bad id")


if __name__ == "__main__":
    unittest.main()
