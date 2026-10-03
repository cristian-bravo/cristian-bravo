"""Run with: python -m unittest discover -s scripts -p 'test_activity_data.py'."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import unittest
from unittest.mock import Mock

from activity_data import (ActivityError, aggregate, collect_activity,
                           fetch_public_repositories, parse_graphql_calendar,
                           parse_public_calendar, select_public_events, validate_days)


def days_from(counts, start=date(2026, 1, 1)):
    return [{"date": (start + timedelta(days=i)).isoformat(), "count": count,
             "level": 1 if count else 0} for i, count in enumerate(counts)]


def html_calendar(days, total=None):
    total = sum(d["count"] for d in days) if total is None else total
    pieces = [f'<h2>{total:,} contributions in the last year</h2>']
    for i, day in enumerate(reversed(days)):
        count = str(day["count"]) if day["count"] else "No"
        pieces.append(f'<td id="d{i}" data-date="{day["date"]}" data-level="{day["level"]}"></td>')
        pieces.append(f'<tool-tip for="d{i}">{count} contributions on January 1st.</tool-tip>')
    return "\n".join(pieces)


def graphql_calendar(days, total=None):
    names = {0: "NONE", 1: "FIRST_QUARTILE", 2: "SECOND_QUARTILE", 3: "THIRD_QUARTILE", 4: "FOURTH_QUARTILE"}
    return {"data": {"user": {"contributionsCollection": {"contributionCalendar": {
        "totalContributions": sum(d["count"] for d in days) if total is None else total,
        "weeks": [{"contributionDays": [{"date": d["date"], "contributionCount": d["count"],
                                          "contributionLevel": names[d["level"]]} for d in days]}]
    }}}}}


def event(number, repo="cristian-bravo/project", **changes):
    value = {"id": str(number), "type": "PushEvent", "public": True,
             "actor": {"login": "cristian-bravo"}, "repo": {"name": repo},
             "created_at": f"2026-10-03T12:{number:02}:00Z", "payload": {"head": "a" * 40}}
    value.update(changes)
    return value


class CalendarTests(unittest.TestCase):
    def test_aggregate_exact_30_day_boundary_and_broken_streak(self):
        days = days_from([100] + [1] * 15 + [0] + [2] * 14)
        result = aggregate(days, 143)
        self.assertEqual(result["last_30_days"], 43)
        self.assertEqual(result["active_days"], 30)
        self.assertEqual(result["longest_streak"], 16)
        self.assertEqual(result["date_to"], "2026-01-31")

    def test_zero_is_valid_only_when_explicitly_observed(self):
        result = aggregate(days_from([0, 0, 0]), 0)
        self.assertEqual(result["active_days"], 0)
        self.assertEqual(result["longest_streak"], 0)
        with self.assertRaises(ActivityError):
            validate_days([], 0)

    def test_public_html_sorts_rows_and_matches_tooltips(self):
        days = days_from([0, 12, 1])
        self.assertEqual(parse_public_calendar(html_calendar(days)), (days, 13))

    def test_public_html_fails_on_missing_tooltip_or_wrong_total(self):
        days = days_from([0, 2])
        for text in (html_calendar(days, total=3), html_calendar(days).replace('for="d1"', 'for="missing"'), "<h2>Sign in</h2>"):
            with self.subTest(text=text), self.assertRaises(ActivityError):
                parse_public_calendar(text)

    def test_graphql_rejects_errors_partial_response_and_unknown_level(self):
        response = graphql_calendar(days_from([1]))
        self.assertEqual(parse_graphql_calendar(response)[1], 1)
        malformed = deepcopy(response)
        malformed["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"][0]["contributionDays"][0]["contributionLevel"] = "NEW_LEVEL"
        for value in ({"errors": [{"message": "Denied"}]}, {"data": {"user": None}}, malformed):
            with self.subTest(value=value), self.assertRaises(ActivityError):
                parse_graphql_calendar(value)

    def test_validation_rejects_gap_duplicate_boolean_and_negative_count(self):
        valid = days_from([1, 2, 0])
        cases = [valid[::2], [valid[0], valid[0]], [{"date": "2026-01-01", "count": True, "level": 1}],
                 [{"date": "2026-01-01", "count": -1, "level": 1}],
                 [{"date": "2026-02-30", "count": 0, "level": 0}]]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ActivityError):
                validate_days(value, 3)

    def test_level_must_match_zero_and_be_in_range(self):
        for count, level in ((0, 1), (1, 0), (1, 5)):
            with self.subTest(level=level), self.assertRaises(ActivityError):
                validate_days([{"date": "2026-01-01", "count": count, "level": level}], count)


class PublicEventTests(unittest.TestCase):
    def test_excludes_profile_bots_private_and_no_longer_public_repos(self):
        values = [event(1), event(2, "cristian-bravo/cristian-bravo"),
                  event(3, actor={"login": "github-actions[bot]"}),
                  event(4, public=False), event(5, "someone/removed"),
                  event(6, "someone/public")]
        verify = Mock(side_effect=lambda name: "https://github.com/" + name if name == "someone/public" else None)
        selected = select_public_events(values, "cristian-bravo", {"cristian-bravo/project": "https://github.com/cristian-bravo/project"}, verify)
        self.assertEqual([v["repo"] for v in selected], ["someone/public", "cristian-bravo/project"])
        self.assertTrue(selected[0]["url"].endswith("/commit/" + "a" * 40))
        self.assertEqual(verify.call_count, 2)

    def test_limits_to_four_newest_and_deduplicates_event_ids(self):
        selected = select_public_events([event(i) for i in range(1, 7)] + [event(6)], "cristian-bravo", {"cristian-bravo/project": "https://github.com/cristian-bravo/project"}, Mock())
        self.assertEqual(len(selected), 4)
        self.assertEqual(selected[0]["created_at"], "2026-10-03T12:06:00Z")

    def test_rejects_missing_privacy_and_foreign_event_links(self):
        unsafe = event(1, type="IssuesEvent", payload={"issue": {"html_url": "https://evil.example/"}})
        missing = event(2)
        del missing["public"]
        for value in (unsafe, missing):
            with self.subTest(value=value), self.assertRaises(ActivityError):
                select_public_events([value], "cristian-bravo", {"cristian-bravo/project": "https://github.com/cristian-bravo/project"}, Mock())

    def test_public_repository_endpoint_must_not_return_private_data(self):
        client = Mock()
        client.request.return_value = [{"private": True, "full_name": "cristian-bravo/secret"}]
        with self.assertRaises(ActivityError):
            fetch_public_repositories(client, "cristian-bravo")


class CollectionTests(unittest.TestCase):
    def client(self, public, official=None):
        client = Mock()
        client.token = "test-placeholder" if official is not None else None
        def request(url, **kwargs):
            if "contributions" in url:
                self.assertFalse(kwargs["authenticate"])
                return html_calendar(public)
            if url.endswith("/graphql"):
                return official
            if "/repos?" in url or "/events/public?" in url:
                return []
            raise AssertionError("Unexpected endpoint")
        client.request.side_effect = request
        return client

    def test_public_calendar_wins_when_authenticated_totals_differ(self):
        days = days_from([0] * 364 + [1], date(2025, 10, 4))
        authenticated = deepcopy(days)
        authenticated[-1]["count"] = 9
        result = collect_activity(client=self.client(days, graphql_calendar(authenticated)), now=datetime(2026, 10, 3, 12, tzinfo=timezone.utc))
        self.assertEqual(result["total_contributions"], 1)
        self.assertEqual(result["calendar_source"], "github-public-profile")
        self.assertEqual(result["generated_at"], "2026-10-03T12:00:00Z")

    def test_matching_official_calendar_is_public_verified(self):
        days = days_from([0] * 365, date(2025, 10, 4))
        result = collect_activity(client=self.client(days, graphql_calendar(days)), now=datetime(2026, 10, 3, tzinfo=timezone.utc))
        self.assertEqual(result["calendar_source"], "github-graphql-public-verified")

    def test_equal_totals_do_not_hide_different_daily_distribution(self):
        days = days_from([0] * 363 + [1, 0], date(2025, 10, 4))
        official = days_from([0] * 364 + [1], date(2025, 10, 4))
        result = collect_activity(client=self.client(days, graphql_calendar(official)), now=datetime(2026, 10, 3, tzinfo=timezone.utc))
        self.assertEqual(result["calendar_source"], "github-public-profile")
        self.assertEqual(result["days"], days)

    def test_stale_or_incomplete_public_calendar_fails(self):
        for days in (days_from([0] * 31), days_from([0] * 365, date(2020, 1, 1))):
            with self.subTest(length=len(days)), self.assertRaises(ActivityError):
                collect_activity(client=self.client(days), now=datetime(2026, 10, 3, tzinfo=timezone.utc))

    def test_graphql_error_is_not_silently_replaced_with_zeroes(self):
        days = days_from([0] * 365, date(2025, 10, 4))
        with self.assertRaises(ActivityError):
            collect_activity(client=self.client(days, {"errors": [{"message": "Forbidden"}]}), now=datetime(2026, 10, 3, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
