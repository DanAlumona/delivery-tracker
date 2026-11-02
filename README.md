# Open-source delivery tracker

**Live dashboard:** https://danalumona.github.io/delivery-tracker/ (sample run, 90 days to 1 Nov 2026)

Built by [Daniel Alumona](https://www.linkedin.com/in/danielalumona). Key numbers were spot-checked against GitHub (see [Sample run](#sample-run-90-days-to-1-nov-2026)).

A small, read-only tool that answers the questions a technical product or program manager asks every week, using real public engineering data:

- **What shipped?** Merged PRs and closed issues per week.
- **How fast does work flow?** PR cycle time (opened to merged) and time to first review.
- **What's at risk?** Stale PRs, growing backlogs, milestones behind schedule, slowing cycle time.
- **What needs a decision?** Approved PRs left unmerged, items labelled blocked or "needs discussion".

**Why it exists.** Weekly delivery updates are usually put together by hand from GitHub and chat. They take an hour or more, vary with whoever writes them, and report activity rather than risk, so slips surface late. The signals are already in the tracker; this tool turns them into a consistent draft in minutes, leaving the person time to add context and push decisions. It's built for a technical program or product manager running a multi-team engineering effort; open-source maintainers checking project health can use it too.

It pulls issues, pull requests and milestones from 1-3 public GitHub repos and writes a static dashboard, two CSVs and an auto-drafted weekly status note. By default it tracks Jane Street's open-source OCaml libraries [`janestreet/core`](https://github.com/janestreet/core) and [`janestreet/base`](https://github.com/janestreet/base), plus [`ocaml/dune`](https://github.com/ocaml/dune), the OCaml build system their packages build with. Any public repo works.

| File | What it does |
|---|---|
| `tracker.py` | Command line: fetches data, normalises it, writes every output. |
| `github_client.py` | Read-only GitHub REST client. GET requests only, paginated, cached to `cache/`. |
| `metrics.py` | The metric definitions. Pure functions, no I/O, easy to test. |
| `status_note.py` | Drafts the weekly status note from the metrics, using simple stated rules. |
| `dashboard_template.html` | The dashboard. `tracker.py` embeds the data into it as `docs/index.html`. |
| `config.json` | Repos, time window, stale threshold, label patterns. |
| `docs/` | Outputs from the last run (committed as a sample). |

## Run it

Python 3.10+; standard library only, nothing to install.

```bash
python tracker.py
```

```bash
python tracker.py --gh-token
```

```bash
python tracker.py --repos rust-lang/rustup --as-of 2026-11-01
```

- Unauthenticated, GitHub allows 60 API calls an hour, so review latency is checked on only 10 PRs per repo. `--gh-token` borrows the GitHub CLI's token (`gh auth token`, 5,000 calls an hour) and checks up to 150. A `GITHUB_TOKEN` environment variable also works. The token is only sent to api.github.com, and only GET requests are made.
- Responses are cached in `cache/` for 12 hours. `--offline` uses the cache only; `--refresh` refetches.
- `--as-of` fixes the report date, so a cached run gives the same numbers every time.

Then open `docs/index.html` in a browser. It needs no server; the chart library (Chart.js 4.4.1) loads from cdnjs.

## Definitions

All metrics cover a window of the last 90 days (`window_days`) up to the report date, except open work, which counts everything still open.

| Metric | Definition |
|---|---|
| PR cycle time | `merged_at - created_at`, for PRs merged in the window. Reported as median and 85th percentile (nearest rank), because a few very old PRs skew the mean. |
| Time to first review | `created_at` to the first submitted review by someone other than the author, before the merge, for the most recently merged PRs that were checked (one API call per PR). Comments that aren't reviews don't count. The dashboard also shows what share of those PRs had any review before merge. |
| Throughput | PRs merged, issues opened and issues closed, per week starting Monday (UTC). |
| Stale | Open, and `updated_at` is 30+ days ago (`stale_days`). Any activity, including a comment, resets it. |
| Blocked / needs a decision | Open, with a label matching the `blocked_labels` or `decision_labels` pattern in `config.json`. Each repo labels differently, so these patterns are per-team configuration. |
| Top author share | Share of merged PRs written by the single most frequent author: a rough key-person-risk signal. |
| Milestone progress | `closed_issues / (open_issues + closed_issues)` as GitHub reports it. Overdue means open with a past due date. |

Status-note rules: a milestone is at risk if it's overdue, or due within 14 days and under 80% done; cycle time is flagged if the last 4 weeks' median is 1.5x or more the previous 4 weeks' and at least half a day longer; backlog is flagged if 4-week issues opened exceed closed by more than 5; with 20+ merged PRs, one author writing 50%+ of them is flagged, and so is fewer than half of sampled merged PRs having a review before merge. Approved PRs idle for 7+ days go under "needs a decision".

## Sample run (90 days to 1 Nov 2026)

`python tracker.py --gh-token --as-of 2026-11-01` (311 API calls, about 2 minutes; reruns from the cache are instant). Output is in `docs/`.

| Repo | Merged PRs | Median cycle | p85 cycle | Open PRs | Open issues | Stale (30+ days idle) |
|---|---:|---:|---:|---:|---:|---:|
| janestreet/core | 0 | n/a | n/a | 1 | 5 | 5 |
| janestreet/base | 0 | n/a | n/a | 7 | 9 | 9 |
| ocaml/dune | 960 | 0.1 days | 1.4 days | 120 | 917 | 970 |

What a TPM would take from it:
- **dune merges fast and mostly without formal review.** The median PR merges about 2 hours after opening; only 8% of the 150 most recent merged PRs had a GitHub review before merge. That may be a deliberate trust-the-maintainers norm, but it's worth asking about.
- **One author wrote 51% of merged PRs** (25 authors in total). That's a key-person risk for a build system many projects depend on.
- **The issue backlog is old.** 707 of 917 open issues are over a year old, and 80 open PRs have been idle 30+ days.
- **Jane Street's repos had no merged PRs in the window**, which is expected: see below.

Checked by hand against GitHub (search API and `gh pr view`, 2 Nov 2026): merged PR count (960), issues opened (97) and closed (70) in the window, open PR and issue counts per repo, stale open PRs (80), the cycle time of two PRs (dune#16877: 29 minutes; dune#16768: 7.0 days), one approval (dune#16658) and one milestone's progress (4.0.0: 2 of 9 closed, 22%).

## What the data does and doesn't show

- **Jane Street's repos are mirrors.** Jane Street develops in an internal monorepo and publishes to GitHub in bulk releases. PRs on GitHub are mostly external contributions, which are imported internally, so their "cycle time" measures the external-contribution path, not Jane Street's own engineering speed. They also use no GitHub milestones. That's why `ocaml/dune`, which is developed in the open with milestones, is in the default set.
- **Labels are a weak signal.** "Blocked" only counts what someone bothered to label. Real blockers often live in comments.
- **Merged isn't shipped.** For a library, shipped means released; this tool measures merged.
- **Review latency is sampled** (most recent merged PRs) to stay inside the rate limit; the dashboard shows the sample size.

Knowing what a metric can't tell you matters as much as the metric. In a real team, confirm these definitions with the engineering leads before reporting on them.

## How a TPM would use this

1. **Agree the definitions first.** Sit with the engineering leads, agree what "stale", "blocked" and "done" mean for them, and encode that in `config.json`. The numbers are only useful if engineers trust them.
2. **Use trends, not targets.** Cycle time and review latency show where work waits. Use them to start conversations ("reviews are taking 3 days; is that a capacity problem?"), never to rank people or teams.
3. **Draft the weekly update in minutes.** Run it Monday morning, edit the status note (add context the data can't see, remove false alarms), and send it. Most of the time saved goes into the "needs a decision" section, which is where a TPM adds value.
4. **Run the stale and blocked lists in standup or triage.** Each item gets an owner and a next step, or gets closed.
5. **Track milestones against dates.** Where a team uses milestones, flag slippage two weeks before the date, not on it.

## 5-minute demo

1. **(30s) The problem.** "Every week a TPM answers: what shipped, what's at risk, what needs a decision. Usually that's an hour of clicking through GitHub and chasing people. I wanted to see how much of it real public data can answer."
2. **(60s) The dashboard.** Open `docs/index.html`. Walk through the tiles for all repos, then switch the scope to `ocaml/dune`: merged PRs per week, cycle time median vs p85, issues opened vs closed.
3. **(60s) The honest caveat.** Switch to `janestreet/core`. Few PRs, no milestones. Explain why: the repos mirror an internal monorepo, so these numbers measure the external-contribution path. "The first job with any metric is knowing what it measures."
4. **(60s) The status note.** Scroll to the draft. Show one item from each section and click through to the GitHub item it came from. Explain the rules behind "at risk".
5. **(60s) Live change.** Run `python tracker.py --repos <any public repo> --gh-token`, refresh the page, and read the new status note.
6. **(30s) What I'd do next.** Release-based "shipped" (tags), per-team label config, a trend line for review latency, and sending the note to Slack once a human has approved it.

## Design choices

- **Standard library only.** `urllib`, `csv`, `json`, `statistics`; nothing to install, nothing to audit.
- **Read-only and cached.** GET requests only. The cache keeps reruns free and makes demos work offline.
- **Pure metric functions.** `metrics.py` takes plain dicts and returns plain dicts, so every definition can be read and tested on its own.
- **Static dashboard.** The data is embedded in the HTML, so it opens from disk or GitHub Pages with no server or build step. Titles are HTML-escaped before display.

## Licence

MIT. Data comes from the public GitHub REST API; each repo's content belongs to its owners.
