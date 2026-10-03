#!/usr/bin/env python3
"""Collect a public, reproducible GitHub profile snapshot using only stdlib.

Usage: python scripts/activity_data.py --output data/activity.json
Optional GITHUB_TOKEN (or GH_TOKEN) enables the official GraphQL calendar.
That calendar is published only when it matches the anonymous profile exactly;
otherwise the anonymous calendar wins. No private repository query is made.

References:
https://docs.github.com/en/graphql/reference/users#contributioncalendar
https://docs.github.com/en/rest/activity/events#list-public-events-for-a-user
https://docs.github.com/en/rest/repos/repos#list-repositories-for-a-user
"""

import argparse
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request


API = "https://api.github.com"
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
          "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
QUERY = """query ProfileActivity($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
  }
}"""
LABELS = {
    "PushEvent": "Publicó cambios",
    "CreateEvent": "Creó un recurso",
    "PullRequestEvent": "Trabajó en una pull request",
    "PullRequestReviewEvent": "Revisó una pull request",
    "IssuesEvent": "Actualizó una incidencia",
    "IssueCommentEvent": "Comentó una incidencia",
    "ReleaseEvent": "Publicó una versión",
    "ForkEvent": "Creó un fork",
    "WatchEvent": "Marcó un repositorio con estrella",
}


class ActivityError(ValueError):
    """Remote data cannot safely produce a complete public snapshot."""


class HTTPStatusError(ActivityError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"GitHub request failed: HTTP {status}")


def integer(value, name):
    if type(value) is not int or value < 0:
        raise ActivityError(f"Invalid non-negative integer: {name}")
    return value


def iso_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ActivityError("Invalid calendar date")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ActivityError("Invalid calendar date") from None


def utc_timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise ActivityError("Invalid UTC event timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ActivityError("Invalid UTC event timestamp") from None


def validate_days(raw_days, total):
    """Reject partial/malformed calendars instead of silently inventing zeroes."""
    integer(total, "calendar total")
    if not isinstance(raw_days, list) or not raw_days:
        raise ActivityError("Contribution calendar is empty or malformed")
    days = []
    for item in raw_days:
        if not isinstance(item, dict):
            raise ActivityError("Invalid contribution day")
        day = iso_date(item.get("date"))
        count = integer(item.get("count"), "daily contributions")
        level = integer(item.get("level"), "contribution level")
        if level > 4 or (count == 0) != (level == 0):
            raise ActivityError("Contribution level disagrees with count")
        days.append({"date": day.isoformat(), "count": count, "level": level})
    days.sort(key=lambda item: item["date"])
    for previous, current in zip(days, days[1:]):
        if iso_date(current["date"]) - iso_date(previous["date"]) != timedelta(days=1):
            raise ActivityError("Calendar dates are duplicated or incomplete")
    if sum(day["count"] for day in days) != total:
        raise ActivityError("Contribution total disagrees with daily counts")
    return days


class CalendarHTML(HTMLParser):
    """Read GitHub's anonymous contribution cells, labels and total heading."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells = {}
        self.tooltips = {}
        self.headings = []
        self.capture = None
        self.parts = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag in ("td", "rect") and "data-date" in attrs:
            key = attrs.get("id")
            if not key or key in self.cells:
                raise ActivityError("Missing or duplicate calendar cell identifier")
            self.cells[key] = attrs
        if tag == "tool-tip":
            self.capture, self.parts = (tag, attrs.get("for")), []
        elif tag == "h2":
            self.capture, self.parts = (tag, None), []

    def handle_data(self, data):
        if self.capture:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if self.capture and self.capture[0] == tag:
            value = " ".join(" ".join(self.parts).split())
            if tag == "h2":
                self.headings.append(value)
            else:
                key = self.capture[1]
                if key in self.tooltips:
                    raise ActivityError("Duplicate contribution tooltip")
                self.tooltips[key] = value
            self.capture, self.parts = None, []


def parse_public_calendar(html):
    if not isinstance(html, str):
        raise ActivityError("Expected contribution HTML")
    parser = CalendarHTML()
    parser.feed(html)
    totals = [re.fullmatch(r"([\d,]+) contributions? in the last year", value)
              for value in parser.headings]
    totals = [int(match[1].replace(",", "")) for match in totals if match]
    if len(totals) != 1:
        raise ActivityError("Public contribution total is missing or ambiguous")
    days = []
    for key, attrs in parser.cells.items():
        tooltip = parser.tooltips.get(key, "")
        match = re.match(r"^(No|[\d,]+) contributions? on .+\.$", tooltip)
        if not match or not re.fullmatch(r"[0-4]", attrs.get("data-level", "")):
            raise ActivityError("Public contribution cell or tooltip is malformed")
        count = 0 if match[1] == "No" else int(match[1].replace(",", ""))
        days.append({"date": attrs["data-date"], "count": count,
                     "level": int(attrs["data-level"])})
    return validate_days(days, totals[0]), totals[0]


def parse_graphql_calendar(response):
    if not isinstance(response, dict) or response.get("errors"):
        raise ActivityError("GraphQL returned errors or malformed data")
    try:
        calendar = response["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        total = calendar["totalContributions"]
        weeks = calendar["weeks"]
        if not isinstance(weeks, list) or not weeks:
            raise ActivityError("GraphQL calendar has no weeks")
        days = []
        for week in weeks:
            if not isinstance(week["contributionDays"], list) or not week["contributionDays"]:
                raise ActivityError("GraphQL calendar has an empty week")
            for item in week["contributionDays"]:
                days.append({"date": item["date"], "count": item["contributionCount"],
                             "level": LEVELS[item["contributionLevel"]]})
    except (KeyError, TypeError):
        raise ActivityError("GraphQL contribution calendar is malformed") from None
    return validate_days(days, total), total


class GitHubClient:
    def __init__(self, token=None):
        self.token = token

    def request(self, url, payload=None, authenticate=True, as_json=True):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" or parts.netloc not in ("api.github.com", "github.com"):
            raise ActivityError("Refusing an unexpected source URL")
        headers = {"User-Agent": "Cristian-Bravo-Public-Activity/1.0",
                   "Accept-Language": "en-US,en;q=0.9"}
        if parts.netloc == "api.github.com":
            headers.update({"Accept": "application/vnd.github+json",
                            "X-GitHub-Api-Version": "2022-11-28"})
            if authenticate and self.token:
                headers["Authorization"] = "Bearer " + self.token
        else:
            headers["Accept"] = "text/html"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                content = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            raise HTTPStatusError(error.code) from None
        except (urllib.error.URLError, TimeoutError, UnicodeError):
            raise ActivityError("GitHub request failed or response could not be decoded") from None
        if not as_json:
            return content
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            raise ActivityError("GitHub returned malformed JSON") from None


def repository_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", value):
        raise ActivityError("Malformed public repository name")
    return value


def fetch_public_repositories(client, username):
    repos = {}
    for page in range(1, 101):
        result = client.request(f"{API}/users/{username}/repos?type=owner&per_page=100&page={page}")
        if not isinstance(result, list):
            raise ActivityError("Public repositories response is malformed")
        for item in result:
            if not isinstance(item, dict) or item.get("private") is not False:
                raise ActivityError("Public repository response failed privacy validation")
            name = repository_name(item.get("full_name"))
            expected = "https://github.com/" + name
            if item.get("html_url") != expected or name.split("/")[0].lower() != username.lower():
                raise ActivityError("Public repository identity is inconsistent")
            if name.lower() in repos:
                raise ActivityError("Repository pagination returned duplicate entries")
            repos[name.lower()] = expected
        if len(result) < 100:
            return repos
    raise ActivityError("Public repository pagination exceeded its safety limit")


def event_url(event, repo_url):
    payload = event.get("payload")
    if not isinstance(payload, dict):
        raise ActivityError("Public event payload is malformed")
    if event["type"] == "PushEvent":
        head = payload.get("head")
        if isinstance(head, str) and re.fullmatch(r"[0-9a-fA-F]{40}", head):
            return repo_url + "/commit/" + head
    for key in ("pull_request", "issue", "comment", "release"):
        value = payload.get(key)
        if isinstance(value, dict) and value.get("html_url"):
            url = value["html_url"]
            if not isinstance(url, str) or not url.startswith(repo_url + "/"):
                raise ActivityError("Public event URL has an unexpected destination")
            return url
    return repo_url


def select_public_events(events, username, public_repos, verify_repository, limit=4):
    if not isinstance(events, list):
        raise ActivityError("Public events response is malformed")
    selected, ids = [], set()
    excluded = f"{username}/{username}".lower()
    for event in events:
        if not isinstance(event, dict) or type(event.get("public")) is not bool:
            raise ActivityError("Public event privacy field is malformed")
        if event["public"] is not True:
            continue
        actor = event.get("actor")
        if not isinstance(actor, dict) or not isinstance(actor.get("login"), str):
            raise ActivityError("Public event actor is malformed")
        login = actor["login"]
        if login.lower() != username.lower() or login.lower().endswith("[bot]") or actor.get("type") == "Bot":
            continue
        if not isinstance(event.get("repo"), dict):
            raise ActivityError("Public event repository is malformed")
        name = repository_name(event["repo"].get("name"))
        if name.lower() == excluded:
            continue
        created_at = event.get("created_at")
        utc_timestamp(created_at)
        kind = event.get("type")
        if not isinstance(kind, str) or not isinstance(event.get("id"), str):
            raise ActivityError("Public event identity is malformed")
        if kind not in LABELS or event["id"] in ids:
            continue
        ids.add(event["id"])
        selected.append((created_at, name, event))
    selected.sort(key=lambda value: value[0], reverse=True)
    result, verified = [], dict(public_repos)
    for created_at, name, event in selected:
        if name.lower() not in verified:
            verified[name.lower()] = verify_repository(name)
        repo_url = verified[name.lower()]
        if not repo_url:
            continue  # A previously public event's repository may now be private/deleted.
        result.append({"type": event["type"], "repo": name, "repo_url": repo_url,
                       "url": event_url(event, repo_url), "created_at": created_at,
                       "label": LABELS[event["type"]]})
        if len(result) == limit:
            break
    return result


def fetch_recent_activity(client, username, public_repos):
    events = []
    for page in range(1, 4):  # The official public Events API exposes at most 300 events.
        result = client.request(f"{API}/users/{username}/events/public?per_page=100&page={page}")
        if not isinstance(result, list):
            raise ActivityError("Public events response is malformed")
        events.extend(result)
        if len(result) < 100:
            break

    def verify(name):
        try:
            # Anonymous lookup cannot reveal repositories accessible only to the token.
            value = client.request(f"{API}/repos/{name}", authenticate=False)
        except HTTPStatusError as error:
            if error.status in (404, 410):
                return None
            raise
        if not isinstance(value, dict) or type(value.get("private")) is not bool:
            raise ActivityError("Event repository privacy response is malformed")
        if value["private"]:
            return None
        if value.get("full_name", "").lower() != name.lower() or value.get("html_url") != "https://github.com/" + value.get("full_name", ""):
            raise ActivityError("Event repository identity is inconsistent")
        return value["html_url"]

    return select_public_events(events, username, public_repos, verify)


def aggregate(days, total):
    days = validate_days(days, total)
    since = iso_date(days[-1]["date"]) - timedelta(days=29)
    streak = longest = 0
    for day in days:
        streak = streak + 1 if day["count"] else 0
        longest = max(longest, streak)
    return {"date_from": days[0]["date"], "date_to": days[-1]["date"],
            "total_contributions": total,
            "active_days": sum(day["count"] > 0 for day in days),
            "last_30_days": sum(day["count"] for day in days if iso_date(day["date"]) >= since),
            "longest_streak": longest}


def collect_activity(username="cristian-bravo", client=None, now=None):
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", username):
        raise ActivityError("Invalid GitHub username")
    client = client or GitHubClient(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))
    now = now or datetime.now(timezone.utc)
    calendar_url = f"https://github.com/users/{username}/contributions"
    days, total = parse_public_calendar(client.request(calendar_url, authenticate=False, as_json=False))
    # GitHub's default graph includes the leading week, so it can contain >365 days.
    if not 365 <= len(days) <= 373 or not 0 <= (now.date() - iso_date(days[-1]["date"])).days <= 2:
        raise ActivityError("Public contribution calendar is incomplete or stale")
    source = "github-public-profile"
    if client.token:
        official_days, official_total = parse_graphql_calendar(client.request(
            API + "/graphql", payload={"query": QUERY, "variables": {"login": username}}))
        if official_days == days and official_total == total:
            source = "github-graphql-public-verified"
        # Token scopes may expose different aggregate counts; never publish those.
    repos = fetch_public_repositories(client, username)
    recent = fetch_recent_activity(client, username, repos)
    return {"schema_version": 1, "username": username,
            "generated_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            **aggregate(days, total), "public_repos": len(repos), "days": days,
            "recent_public_activity": recent, "calendar_source": source,
            "calendar_url": calendar_url}


def write_snapshot(path, snapshot):
    """Atomic replacement keeps the last successful snapshot intact on failure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".activity-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(snapshot, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="cristian-bravo")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "activity.json")
    args = parser.parse_args(argv)
    try:
        snapshot = collect_activity(args.username)
        write_snapshot(args.output, snapshot)
    except (ActivityError, OSError) as error:
        print(f"Activity update failed: {error}", file=sys.stderr)
        return 1
    print(f"Updated public activity: {snapshot['total_contributions']} contributions, {snapshot['public_repos']} public repositories.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
