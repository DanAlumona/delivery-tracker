"""Unit tests for the metric definitions, the status-note rules and the API plumbing.

No network: a fake client stands in for GitHub. Run: python -m unittest -v
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import metrics
import status_note
import tracker

AS_OF = datetime(2026, 11, 1, 23, 59, tzinfo=timezone.utc)  # a Sunday
CFG = {"window_days": 90, "stale_days": 30, "review_sample": 150,
       "blocked_labels": "blocked|needs-repro", "decision_labels": "needs-decision|proposal"}


def ago(days, hours=0):
    return AS_OF - timedelta(days=days, hours=hours)


def item(number, kind="pr", created=None, updated=None, closed=None, merged=None, labels=(),
         author="alice", first_review=None, approved=False, repo="o/r"):
    created = created or ago(10)
    return {"repo": repo, "number": number, "kind": kind, "title": f"Item {number}",
            "url": f"https://github.com/{repo}/pull/{number}", "author": author, "created": created,
            "updated": updated or closed or created, "closed": closed, "merged": merged,
            "labels": list(labels), "milestone": "", "review_checked": first_review is not None,
            "first_review": first_review, "approved": approved}


class HelpersTest(unittest.TestCase):
    def test_percentile_nearest_rank(self):
        values = list(range(1, 21))  # 1..20
        self.assertEqual(metrics.percentile(values, 85), 17)
        self.assertEqual(metrics.percentile(values, 50), 10)
        self.assertEqual(metrics.percentile(list(range(1, 11)), 85), 9)  # rank 8.5 rounds up to 9
        self.assertIsNone(metrics.percentile([], 85))

    def test_week_starts_on_monday(self):
        self.assertEqual(metrics.week_start(AS_OF).date().isoformat(), "2026-10-26")

    def test_stale_is_based_on_last_update(self):
        self.assertTrue(metrics.is_stale(item(1, updated=ago(30)), AS_OF, 30))
        self.assertFalse(metrics.is_stale(item(2, updated=ago(29)), AS_OF, 30))
        self.assertFalse(metrics.is_stale(item(3, created=ago(60), closed=ago(40)), AS_OF, 30))


class ComputeTest(unittest.TestCase):
    def setUp(self):
        self.items = [
            item(1, created=ago(5), merged=ago(4), closed=ago(4), first_review=ago(4, 12)),  # 1 day
            item(2, created=ago(10), merged=ago(7), closed=ago(7), author="bob"),             # 3 days, not checked
            item(3, created=ago(200), merged=ago(100), closed=ago(100)),                      # merged before window
            item(4, created=ago(20), closed=ago(2)),                                          # closed unmerged
            item(5, created=ago(400), updated=ago(45), labels=["needs-repro"]),               # open, stale, blocked
            item(6, kind="issue", created=ago(3)),                                            # open issue
            item(7, kind="issue", created=ago(50), closed=ago(1), labels=["proposal"]),       # closed issue
        ]
        self.result = metrics.compute(self.items, [], AS_OF, CFG)
        self.s = self.result["summary"]

    def test_cycle_time_only_counts_prs_merged_in_window(self):
        self.assertEqual(self.s["merged_prs"], 2)
        self.assertEqual(self.s["cycle_median_days"], 2.0)  # median of 1 and 3 days
        self.assertEqual(self.s["closed_unmerged_prs"], 1)

    def test_review_latency_and_coverage(self):
        self.assertEqual(self.s["review_sample"], 1)
        self.assertEqual(self.s["review_median_hours"], 12.0)
        self.assertEqual(self.s["reviewed_share_pct"], 100)

    def test_open_work(self):
        self.assertEqual((self.s["open_prs"], self.s["open_issues"]), (1, 1))
        self.assertEqual((self.s["stale"], self.s["blocked"]), (1, 1))
        self.assertEqual(self.s["needs_decision"], 0)  # the proposal issue is closed

    def test_author_concentration(self):
        self.assertEqual(self.s["top_author_share_pct"], 50)
        self.assertEqual(self.s["merged_authors"], 2)

    def test_weekly_throughput_adds_up(self):
        weekly = self.result["weekly"]
        self.assertEqual(sum(w["merged_prs"] for w in weekly), 2)
        self.assertEqual(sum(w["issues_opened"] for w in weekly), 2)  # issues 6 and 7
        self.assertEqual(sum(w["issues_closed"] for w in weekly), 1)
        self.assertEqual(weekly[-1]["week"], "2026-10-26")

    def test_open_items_bucketed_by_age(self):
        by_bucket = {b["bucket"]: b for b in self.result["open_by_age"]}
        self.assertEqual(by_bucket["> 1 year"]["pr"], 1)
        self.assertEqual(by_bucket["< 1 week"]["issue"], 1)

    def test_empty_repo_does_not_crash(self):
        s = metrics.compute([], [], AS_OF, CFG)["summary"]
        self.assertEqual(s["merged_prs"], 0)
        self.assertIsNone(s["cycle_median_days"])
        self.assertIsNone(s["top_author_share_pct"])


class MilestoneTest(unittest.TestCase):
    def test_progress_and_overdue(self):
        ms = [{"repo": "o/r", "title": "v1", "url": "u", "state": "open", "open_issues": 3,
               "closed_issues": 1, "due_on": ago(1), "closed_at": None}]
        row = metrics.milestone_progress(ms, AS_OF)[0]
        self.assertEqual(row["progress_pct"], 25)
        self.assertTrue(row["overdue"])


class StatusNoteTest(unittest.TestCase):
    def draft(self, items, milestones=()):
        scope = metrics.compute(items, list(milestones), AS_OF, CFG)
        return status_note.draft(items, {"All repos": scope, "o/r": scope}, ["o/r"], AS_OF, CFG)

    def test_lists_prs_merged_this_week_only(self):
        note = self.draft([item(1, merged=ago(2), closed=ago(2)), item(2, merged=ago(9), closed=ago(9))])
        self.assertIn("1 PRs merged", note)
        self.assertIn("Item 1", note)
        self.assertNotIn("Item 2", note)

    def test_flags_milestone_due_soon_and_behind(self):
        ms = [{"repo": "o/r", "title": "v2", "url": "u", "state": "open", "open_issues": 8,
               "closed_issues": 2, "due_on": AS_OF + timedelta(days=7), "closed_at": None}]
        note = self.draft([], ms)
        self.assertIn("milestone [v2](u)", note)
        self.assertIn("20% done", note)

    def test_flags_approved_pr_left_unmerged(self):
        self.assertIn("Approved but not merged", self.draft([item(9, updated=ago(8), approved=True)]))

    def test_quiet_week_says_nothing_flagged(self):
        self.assertIn("Nothing flagged by the rules this week.", self.draft([]))


class FakeClient:
    """Answers GitHub API URLs from a dict instead of the network."""
    def __init__(self, pages):
        self.pages = pages

    def get(self, url):
        return self.pages[url], None

    def get_all(self, path, max_pages=30):
        return self.pages[path]


def raw_issue(number, merged_at=None, pull=True):
    record = {"number": number, "title": f"T{number}", "html_url": f"https://github.com/o/r/pull/{number}",
              "user": {"login": "alice"}, "created_at": "2026-10-20T10:00:00Z",
              "updated_at": "2026-10-21T10:00:00Z", "closed_at": merged_at, "labels": [{"name": "bug"}],
              "milestone": None}
    if pull:
        record["pull_request"] = {"merged_at": merged_at}
    return record


class FetchTest(unittest.TestCase):
    def test_fetch_dedupes_and_ignores_reviews_after_merge(self):
        since = (AS_OF - timedelta(days=90)).strftime("%Y-%m-%dT00:00:00Z")
        reviews = "https://api.github.com/repos/o/r/pulls/{}/reviews?per_page=100"
        client = FakeClient({
            "/repos/o/r/issues?state=open": [raw_issue(2), raw_issue(3, pull=False)],
            f"/repos/o/r/issues?state=all&since={since}": [raw_issue(1, "2026-10-21T10:00:00Z"), raw_issue(2)],
            "/repos/o/r/milestones?state=all": [],
            reviews.format(1): [
                {"user": {"login": "alice"}, "state": "APPROVED", "submitted_at": "2026-10-20T11:00:00Z"},  # the author
                {"user": {"login": "bob"}, "state": "APPROVED", "submitted_at": "2026-10-22T10:00:00Z"},    # after merge
            ],
            reviews.format(2): [
                {"user": {"login": "bob"}, "state": "CHANGES_REQUESTED", "submitted_at": "2026-10-20T12:00:00Z"},
                {"user": {"login": "carol"}, "state": "APPROVED", "submitted_at": "2026-10-20T13:00:00Z"},
            ],
        })
        items, _ = tracker.fetch_repo(client, "o/r", AS_OF, CFG)
        by_number = {i["number"]: i for i in items}
        self.assertEqual(sorted(by_number), [1, 2, 3])  # #2 appears in both lists but counts once
        self.assertEqual(by_number[3]["kind"], "issue")
        self.assertIsNone(by_number[1]["first_review"])
        self.assertEqual(by_number[2]["first_review"].hour, 12)
        self.assertTrue(by_number[2]["approved"])  # the latest verdict wins


class DashboardTest(unittest.TestCase):
    def test_titles_cannot_break_out_of_the_script_tag(self):
        evil = "</script><script>alert(1)</script>"
        with tempfile.TemporaryDirectory() as tmp:
            tracker.write_dashboard(Path(tmp), {"title": evil})
            html = (Path(tmp) / "index.html").read_text(encoding="utf-8")
        self.assertNotIn(evil, html)
        payload = html.split("const DATA = ", 1)[1].split(";\n", 1)[0]
        self.assertEqual(json.loads(payload)["title"], evil)


if __name__ == "__main__":
    unittest.main()
