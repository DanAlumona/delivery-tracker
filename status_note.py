"""Auto-draft a weekly status note: what shipped, what's at risk, what needs a decision.

The draft is a starting point for a human: every line links to its source, and
the rules that flag a risk are simple and stated in the README.
"""

from datetime import timedelta

import metrics


def link(item):
    return f"[{item['repo'].split('/')[1]}#{item['number']}]({item['url']}) {item['title']}"


def draft(items, scopes, repos, as_of, cfg):
    week_ago = as_of - timedelta(days=7)
    lines = [f"# Delivery status: week to {as_of:%d %b %Y}", "",
             f"Repos: {', '.join(repos)}. Auto-drafted from public GitHub data; "
             "review before sending.", ""]

    # --- What shipped ---
    lines += ["## What shipped", ""]
    for repo in repos:
        merged = sorted((i for i in items if i["repo"] == repo and i["merged"] and i["merged"] > week_ago),
                        key=lambda i: i["merged"], reverse=True)
        closed_issues = [i for i in items if i["repo"] == repo and i["kind"] == "issue"
                         and i["closed"] and i["closed"] > week_ago]
        lines.append(f"**{repo}**: {len(merged)} PRs merged, {len(closed_issues)} issues closed.")
        for pr in merged[:8]:
            lines.append(f"- {link(pr)}")
        if len(merged) > 8:
            lines.append(f"- ...and {len(merged) - 8} more (see work_items.csv)")
        for m in scopes[repo]["milestones"]:
            if m["closed_at"] and m["closed_at"] > week_ago.date().isoformat():
                lines.append(f"- Milestone closed: [{m['title']}]({m['url']})")
        lines.append("")

    # --- At risk ---
    risks = []
    for repo in repos:
        s = scopes[repo]["summary"]
        for m in scopes[repo]["milestones"]:
            if m["state"] != "open" or not m["due_on"]:
                continue
            due_soon = m["due_on"] <= (as_of + timedelta(days=14)).date().isoformat()
            if m["overdue"]:
                risks.append(f"**{repo}**: milestone [{m['title']}]({m['url']}) is overdue "
                             f"(due {m['due_on']}, {m['progress_pct']}% done, {m['open']} open).")
            elif due_soon and m["progress_pct"] < 80:
                risks.append(f"**{repo}**: milestone [{m['title']}]({m['url']}) due {m['due_on']} "
                             f"is only {m['progress_pct']}% done ({m['open']} open).")
        recent, prior = s["cycle_recent_median_days"], s["cycle_prior_median_days"]
        if recent and prior and recent >= 1.5 * prior and recent - prior >= 0.5:
            risks.append(f"**{repo}**: median PR cycle time rose to {recent} days over the last 4 weeks "
                         f"(from {prior} days the 4 weeks before).")
        if s["merged_prs"] >= 20 and s["top_author_share_pct"] >= 50:
            risks.append(f"**{repo}**: one author wrote {s['top_author_share_pct']}% of the {s['merged_prs']} merged PRs "
                         f"({s['merged_authors']} authors in total). Key-person risk if they're away.")
        if s["reviewed_share_pct"] is not None and s["review_sample"] >= 20 and s["reviewed_share_pct"] < 50:
            risks.append(f"**{repo}**: only {s['reviewed_share_pct']}% of the {s['review_sample']} most recent merged PRs "
                         "had a review before merge. Fine if that's the team's norm; worth confirming.")
        last4 = scopes[repo]["weekly"][-4:]
        opened, closed = sum(w["issues_opened"] for w in last4), sum(w["issues_closed"] for w in last4)
        if opened > closed + 5:
            risks.append(f"**{repo}**: issue backlog grew by {opened - closed} over 4 weeks "
                         f"({opened} opened, {closed} closed).")
        stale = scopes[repo]["stale_prs"]
        if stale:
            risks.append(f"**{repo}**: {s['stale_open_prs']} open PRs idle for {cfg['stale_days']}+ days. Longest idle:")
            risks += [f"  - {link(i)} (idle {i['idle_days']} days)" for i in stale[:3]]
    lines += ["## At risk", ""] + ([f"- {r}" if not r.startswith("  ") else r for r in risks]
                                   or ["- Nothing flagged by the rules this week."]) + [""]

    # --- Needs a decision ---
    decisions = []
    for repo in repos:
        approved = [i for i in items if i["repo"] == repo and i["kind"] == "pr" and i["closed"] is None
                    and i["approved"] and metrics.days_between(i["updated"], as_of) >= 7]
        for pr in approved[:3]:
            decisions.append(f"Approved but not merged for 7+ days: merge, or say what's blocking? {link(pr)}")
        for i in scopes[repo]["decision_items"][:3]:
            decisions.append(f"Labelled {', '.join(metrics.matches(i['labels'], cfg['decision_labels']))}: {link(i)}")
        blocked = scopes[repo]["blocked_items"]
        if blocked:
            decisions.append(f"**{repo}**: {scopes[repo]['summary']['blocked']} open items carry a blocking label. "
                             f"Unblock, re-scope or close? Oldest idle: {link(blocked[0])}")
    lines += ["## Needs a decision", ""] + ([f"- {d}" for d in decisions]
                                            or ["- Nothing flagged by the rules this week."]) + [""]

    # --- Numbers ---
    lines += ["## Numbers (last {} days)".format(cfg["window_days"]), "",
              "| Repo | Merged PRs | Median cycle (days) | p85 cycle (days) | Median first review (hours) | Open PRs | Open issues | Stale |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    na = lambda v: "n/a" if v is None else v
    for name, scope in scopes.items():
        s = scope["summary"]
        lines.append(f"| {name} | {s['merged_prs']} | {na(s['cycle_median_days'])} | {na(s['cycle_p85_days'])} | "
                     f"{na(s['review_median_hours'])} | {s['open_prs']} | {s['open_issues']} | {s['stale']} |")
    lines.append("")
    return "\n".join(lines)
