"""Open-source delivery tracker.

Pulls issues, pull requests and milestones from public GitHub repos (read-only),
computes delivery metrics, and writes:
  docs/index.html          static dashboard (open it directly, no build step)
  docs/work_items.csv      one row per issue or PR
  docs/weekly.csv          throughput per repo per week
  docs/status-note.md      auto-drafted weekly status note

Usage:
  python tracker.py                         # repos from config.json
  python tracker.py --repos ocaml/dune      # any public repo(s)
  python tracker.py --gh-token              # use `gh auth token` (5,000 calls/hour)
  python tracker.py --offline               # cached responses only
"""

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import metrics
import status_note
from github_client import GitHubClient, find_token

HERE = Path(__file__).parent


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def normalise(repo, raw):
    """Turn one /issues API record (issue or PR) into a flat work item."""
    pr = raw.get("pull_request")
    return {
        "repo": repo,
        "number": raw["number"],
        "kind": "pr" if pr else "issue",
        "title": raw["title"],
        "url": raw["html_url"],
        "author": raw["user"]["login"],
        "created": parse_time(raw["created_at"]),
        "updated": parse_time(raw["updated_at"]),
        "closed": parse_time(raw["closed_at"]),
        "merged": parse_time(pr.get("merged_at")) if pr else None,
        "labels": [label["name"] for label in raw["labels"]],
        "milestone": raw["milestone"]["title"] if raw.get("milestone") else "",
        "review_checked": False,
        "first_review": None,
        "approved": False,
    }


def add_reviews(client, repo, pr):
    """First review by someone other than the author, and whether the latest verdict is approval."""
    reviews, _ = client.get(f"https://api.github.com/repos/{repo}/pulls/{pr['number']}/reviews?per_page=100")
    others = [r for r in reviews if r.get("user") and r["user"]["login"] != pr["author"]
              and r.get("submitted_at")]
    pr["review_checked"] = True
    if pr["merged"]:  # only reviews that happened before the merge count
        others = [r for r in others if parse_time(r["submitted_at"]) <= pr["merged"]]
    if others:
        pr["first_review"] = min(parse_time(r["submitted_at"]) for r in others)
        verdicts = [r["state"] for r in others if r["state"] in ("APPROVED", "CHANGES_REQUESTED")]
        pr["approved"] = bool(verdicts) and verdicts[-1] == "APPROVED"


def fetch_repo(client, repo, as_of, cfg):
    since = (as_of - timedelta(days=cfg["window_days"])).strftime("%Y-%m-%dT00:00:00Z")
    raw = client.get_all(f"/repos/{repo}/issues?state=open")
    raw += client.get_all(f"/repos/{repo}/issues?state=all&since={since}")
    items = {}
    for record in raw:
        items[record["number"]] = normalise(repo, record)  # dedupe: open items appear in both lists
    items = list(items.values())

    window_start = as_of - timedelta(days=cfg["window_days"])
    merged = sorted((i for i in items if i["merged"] and i["merged"] >= window_start),
                    key=lambda i: i["merged"], reverse=True)
    open_prs = sorted((i for i in items if i["kind"] == "pr" and i["closed"] is None),
                      key=lambda i: i["updated"], reverse=True)
    for pr in merged[:cfg["review_sample"]] + open_prs[:cfg["review_sample"]]:
        add_reviews(client, repo, pr)

    milestones = []
    for m in client.get_all(f"/repos/{repo}/milestones?state=all"):
        milestones.append({"repo": repo, "title": m["title"], "url": m["html_url"], "state": m["state"],
                           "open_issues": m["open_issues"], "closed_issues": m["closed_issues"],
                           "due_on": parse_time(m["due_on"]), "closed_at": parse_time(m["closed_at"])})
    return items, milestones


def write_csvs(out, items, scopes, as_of, cfg):
    with open(out / "work_items.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["repo", "number", "kind", "title", "author", "state", "created", "closed", "merged",
                         "cycle_days", "first_review_hours", "age_days", "idle_days", "stale",
                         "blocked", "labels", "milestone", "url"])
        iso = lambda d: d.strftime("%Y-%m-%d %H:%M") if d else ""
        for i in sorted(items, key=lambda i: (i["repo"], i["number"])):
            state = "merged" if i["merged"] else ("closed" if i["closed"] else "open")
            cycle = round(metrics.days_between(i["created"], i["merged"]), 2) if i["merged"] else ""
            review = (round(metrics.days_between(i["created"], i["first_review"]) * 24, 1)
                      if i["first_review"] else "")
            writer.writerow([i["repo"], i["number"], i["kind"], i["title"], i["author"], state, iso(i["created"]),
                             iso(i["closed"]), iso(i["merged"]), cycle, review,
                             round(metrics.days_between(i["created"], i["closed"] or as_of)),
                             round(metrics.days_between(i["updated"], as_of)),
                             metrics.is_stale(i, as_of, cfg["stale_days"]),
                             bool(i["closed"] is None and metrics.matches(i["labels"], cfg["blocked_labels"])),
                             "; ".join(i["labels"]), i["milestone"], i["url"]])
    with open(out / "weekly.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["repo", "week_starting", "merged_prs", "issues_opened", "issues_closed"])
        for repo, scope in scopes.items():
            for w in scope["weekly"]:
                writer.writerow([repo, w["week"], w["merged_prs"], w["issues_opened"], w["issues_closed"]])


def write_dashboard(out, data):
    template = (HERE / "dashboard_template.html").read_text(encoding="utf-8")
    payload = json.dumps(data).replace("</", "<\\/")  # never let a title close the <script> tag
    (out / "index.html").write_text(template.replace("/*__DATA__*/null", payload), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repos", nargs="+", help="owner/name of 1-3 public repos (overrides config.json)")
    parser.add_argument("--config", default=HERE / "config.json")
    parser.add_argument("--out", default=HERE / "docs")
    parser.add_argument("--as-of", help="report date YYYY-MM-DD (default: now, UTC)")
    parser.add_argument("--gh-token", action="store_true", help="authenticate with `gh auth token`")
    parser.add_argument("--offline", action="store_true", help="use cached responses only")
    parser.add_argument("--refresh", action="store_true", help="ignore the cache and refetch")
    args = parser.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    repos = args.repos or cfg["repos"]
    as_of = (datetime.fromisoformat(args.as_of).replace(hour=23, minute=59, tzinfo=timezone.utc)
             if args.as_of else datetime.now(timezone.utc))
    token = find_token(args.gh_token)
    if not token:
        cfg["review_sample"] = min(cfg["review_sample"], cfg["review_sample_unauthenticated"])
    client = GitHubClient(HERE / "cache", token=token, offline=args.offline,
                          max_age_hours=0 if args.refresh else cfg["cache_hours"])

    all_items, all_milestones = [], []
    for repo in repos:
        items, milestones = fetch_repo(client, repo, as_of, cfg)
        print(f"{repo}: {len(items)} work items, {len(milestones)} milestones")
        all_items += items
        all_milestones += milestones

    scopes = {"All repos": metrics.compute(all_items, all_milestones, as_of, cfg)}
    for repo in repos:
        scopes[repo] = metrics.compute([i for i in all_items if i["repo"] == repo],
                                       [m for m in all_milestones if m["repo"] == repo], as_of, cfg)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_csvs(out, all_items, scopes, as_of, cfg)
    note = status_note.draft(all_items, scopes, repos, as_of, cfg)
    (out / "status-note.md").write_text(note, encoding="utf-8")
    write_dashboard(out, {"as_of": as_of.strftime("%Y-%m-%d %H:%M UTC"), "repos": repos, "config": cfg,
                          "scopes": scopes, "status_note": note})

    print(f"\n{'Repo':<18}{'Merged PRs':>11}{'Median cycle':>14}{'p85 cycle':>11}"
          f"{'1st review':>12}{'Open':>7}{'Stale':>7}{'Blocked':>9}")
    for name, scope in scopes.items():
        s = scope["summary"]
        fmt = lambda v, unit: "n/a" if v is None else f"{v}{unit}"
        print(f"{name:<18}{s['merged_prs']:>11}{fmt(s['cycle_median_days'], 'd'):>14}"
              f"{fmt(s['cycle_p85_days'], 'd'):>11}{fmt(s['review_median_hours'], 'h'):>12}"
              f"{s['open_prs'] + s['open_issues']:>7}{s['stale']:>7}{s['blocked']:>9}")
    print(f"\nWindow: last {cfg['window_days']} days to {as_of:%Y-%m-%d}. "
          f"Live API calls this run: {client.calls}. Outputs in {out}/")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as err:
        raise SystemExit(f"error: {err}")
