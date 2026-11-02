"""Delivery metrics from normalised GitHub work items. Pure functions, no I/O.

A work item is a dict made by tracker.normalise(): repo, number, kind ("pr" or
"issue"), title, url, author, created, updated, closed, merged (datetimes or
None), labels, milestone, first_review, approved.
"""

import re
from datetime import timedelta
from collections import Counter
from statistics import median

DAY = 86400
AGE_BUCKETS = [(7, "< 1 week"), (30, "1-4 weeks"), (90, "1-3 months"), (365, "3-12 months"),
               (None, "> 1 year")]
CYCLE_BUCKETS = [(1, "< 1 day"), (3, "1-3 days"), (7, "3-7 days"), (14, "1-2 weeks"),
                 (30, "2-4 weeks"), (None, "> 4 weeks")]


def days_between(start, end):
    return (end - start).total_seconds() / DAY


def percentile(values, pct):
    """Nearest-rank percentile: the smallest value with at least pct% of values at or below it."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * pct // 100))  # ceiling division
    return ordered[int(rank) - 1]


def bucket(value, buckets):
    for limit, label in buckets:
        if limit is None or value < limit:
            return label


def week_start(moment):
    """Monday 00:00 UTC of the ISO week containing moment."""
    day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return day - timedelta(days=day.weekday())


def matches(labels, pattern):
    return [label for label in labels if re.search(pattern, label, re.IGNORECASE)]


def is_stale(item, as_of, stale_days):
    return item["closed"] is None and days_between(item["updated"], as_of) >= stale_days


def round_or_none(value, digits=1):
    return None if value is None else round(value, digits)


def compute(items, milestones, as_of, cfg):
    """All metrics for one scope (a single repo, or every repo together)."""
    window_start = as_of - timedelta(days=cfg["window_days"])
    in_window = lambda moment: moment is not None and window_start <= moment <= as_of
    prs = [i for i in items if i["kind"] == "pr"]
    issues = [i for i in items if i["kind"] == "issue"]

    # Cycle time: opened -> merged, for PRs merged inside the window.
    merged = [p for p in prs if in_window(p["merged"])]
    cycle = [days_between(p["created"], p["merged"]) for p in merged]

    # Review latency: opened -> first review by someone other than the author (sampled PRs only).
    checked = [p for p in merged if p["review_checked"]]
    reviewed = [p for p in checked if p["first_review"] is not None]
    review_hours = [days_between(p["created"], p["first_review"]) * 24 for p in reviewed]

    # Concentration: share of merged PRs written by the single most frequent author.
    authors = Counter(p["author"] for p in merged)
    top_share = round(100 * authors.most_common(1)[0][1] / len(merged)) if merged else None

    # Throughput per ISO week.
    weeks = {}
    first_week = week_start(window_start)
    week = first_week
    while week <= as_of:
        weeks[week] = {"week": week.date().isoformat(), "merged_prs": 0, "issues_opened": 0,
                       "issues_closed": 0}
        week += timedelta(days=7)
    for p in merged:
        weeks[week_start(p["merged"])]["merged_prs"] += 1
    for i in issues:
        if in_window(i["created"]) and week_start(i["created"]) in weeks:
            weeks[week_start(i["created"])]["issues_opened"] += 1
        if in_window(i["closed"]) and week_start(i["closed"]) in weeks:
            weeks[week_start(i["closed"])]["issues_closed"] += 1
    weekly = list(weeks.values())

    # Open work.
    open_items = [i for i in items if i["closed"] is None]
    age_counts = {label: {"pr": 0, "issue": 0} for _, label in AGE_BUCKETS}
    for i in open_items:
        age_counts[bucket(days_between(i["created"], as_of), AGE_BUCKETS)][i["kind"]] += 1
    stale = [i for i in open_items if is_stale(i, as_of, cfg["stale_days"])]
    blocked = [i for i in open_items if matches(i["labels"], cfg["blocked_labels"])]
    decisions = [i for i in open_items if matches(i["labels"], cfg["decision_labels"])]

    cycle_dist = {label: 0 for _, label in CYCLE_BUCKETS}
    for days in cycle:
        cycle_dist[bucket(days, CYCLE_BUCKETS)] += 1

    # Cycle-time trend: last 4 weeks vs the 4 weeks before.
    recent_cut, prior_cut = as_of - timedelta(days=28), as_of - timedelta(days=56)
    recent = [days_between(p["created"], p["merged"]) for p in merged if p["merged"] > recent_cut]
    prior = [days_between(p["created"], p["merged"]) for p in merged
             if prior_cut < p["merged"] <= recent_cut]

    return {
        "summary": {
            "merged_prs": len(merged),
            "closed_unmerged_prs": sum(1 for p in prs if in_window(p["closed"]) and p["merged"] is None),
            "cycle_median_days": round_or_none(median(cycle) if cycle else None),
            "cycle_p85_days": round_or_none(percentile(cycle, 85)),
            "cycle_recent_median_days": round_or_none(median(recent) if recent else None),
            "cycle_prior_median_days": round_or_none(median(prior) if prior else None),
            "review_sample": len(checked),
            "merged_authors": len(authors),
            "top_author_share_pct": top_share,
            "review_median_hours": round_or_none(median(review_hours) if review_hours else None),
            "reviewed_share_pct": round(100 * len(reviewed) / len(checked)) if checked else None,
            "issues_opened": sum(w["issues_opened"] for w in weekly),
            "issues_closed": sum(w["issues_closed"] for w in weekly),
            "open_prs": sum(1 for i in open_items if i["kind"] == "pr"),
            "open_issues": sum(1 for i in open_items if i["kind"] == "issue"),
            "stale": len(stale),
            "stale_open_prs": sum(1 for i in stale if i["kind"] == "pr"),
            "blocked": len(blocked),
            "needs_decision": len(decisions),
        },
        "weekly": weekly,
        "cycle_distribution": [{"bucket": k, "prs": v} for k, v in cycle_dist.items()],
        "open_by_age": [{"bucket": k, **v} for k, v in age_counts.items()],
        "milestones": milestone_progress(milestones, as_of),
        "stale_prs": top(sorted((i for i in stale if i["kind"] == "pr"), key=lambda i: i["updated"]), as_of),
        "blocked_items": top(sorted(blocked, key=lambda i: i["updated"]), as_of),
        "decision_items": top(sorted(decisions, key=lambda i: i["updated"]), as_of),
    }


def milestone_progress(milestones, as_of):
    rows = []
    for m in milestones:
        total = m["open_issues"] + m["closed_issues"]
        rows.append({
            "repo": m["repo"], "title": m["title"], "url": m["url"], "state": m["state"],
            "open": m["open_issues"], "closed": m["closed_issues"],
            "progress_pct": round(100 * m["closed_issues"] / total) if total else 0,
            "due_on": m["due_on"].date().isoformat() if m["due_on"] else None,
            "overdue": bool(m["due_on"] and m["due_on"] < as_of and m["state"] == "open"),
            "closed_at": m["closed_at"].date().isoformat() if m["closed_at"] else None,
        })
    rows.sort(key=lambda r: (r["state"] != "open", r["repo"], r["title"]))
    return rows


def top(items, as_of, limit=10):
    return [{"repo": i["repo"], "number": i["number"], "kind": i["kind"], "title": i["title"],
             "url": i["url"], "labels": i["labels"],
             "age_days": round(days_between(i["created"], as_of)),
             "idle_days": round(days_between(i["updated"], as_of))} for i in items[:limit]]
