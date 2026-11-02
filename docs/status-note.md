# Delivery status: week to 01 Nov 2026

Repos: janestreet/core, janestreet/base, ocaml/dune. Auto-drafted from public GitHub data; review before sending.

## What shipped

**janestreet/core**: 0 PRs merged, 0 issues closed.

**janestreet/base**: 0 PRs merged, 0 issues closed.

**ocaml/dune**: 91 PRs merged, 6 issues closed.
- [dune#16877](https://github.com/ocaml/dune/pull/16877) test: avoid login shells in trace polling helpers
- [dune#16859](https://github.com/ocaml/dune/pull/16859) doc(changes): document that actions must declare the packages they use
- [dune#16645](https://github.com/ocaml/dune/pull/16645) test(engine): cover parallel restoration of success prefixes
- [dune#16768](https://github.com/ocaml/dune/pull/16768) refactor(engine): cancel the loop-owned process context
- [dune#16874](https://github.com/ocaml/dune/pull/16874) test(scheduler): disable flaky signal watcher reproducer
- [dune#16873](https://github.com/ocaml/dune/pull/16873) refactor(engine): keep the active request in the loop state
- [dune#16871](https://github.com/ocaml/dune/pull/16871) perf(cache): load metadata at its enumerated path
- [dune#16869](https://github.com/ocaml/dune/pull/16869) refactor(boot): remove unused SIMD C flags
- ...and 83 more (see work_items.csv)

## At risk

- **janestreet/core**: 1 open PRs idle for 30+ days. Longest idle:
  - [core#182](https://github.com/janestreet/core/pull/182) Fix predicate typo that disabled five bisimulation operations (idle 56 days)
- **janestreet/base**: 4 open PRs idle for 30+ days. Longest idle:
  - [base#138](https://github.com/janestreet/base/pull/138) CI: Add profile to matrix (idle 1554 days)
  - [base#174](https://github.com/janestreet/base/pull/174) Fix MSVC compilation (idle 658 days)
  - [base#194](https://github.com/janestreet/base/pull/194) Fix CI compiler matrix (idle 72 days)
- **ocaml/dune**: one author wrote 51% of the 960 merged PRs (25 authors in total). Key-person risk if they're away.
- **ocaml/dune**: only 8% of the 150 most recent merged PRs had a review before merge. Fine if that's the team's norm; worth confirming.
- **ocaml/dune**: 80 open PRs idle for 30+ days. Longest idle:
  - [dune#11443](https://github.com/ocaml/dune/pull/11443) test(ctypes): showcase deps field not supporting the full dependency specification (idle 612 days)
  - [dune#12978](https://github.com/ocaml/dune/pull/12978) fix: show clear error when running uninstalled dev tool (idle 314 days)
  - [dune#13337](https://github.com/ocaml/dune/pull/13337) feat(scope): add scope stanza for library visibility control (idle 160 days)

## Needs a decision

- Approved but not merged for 7+ days: merge, or say what's blocking? [base#194](https://github.com/janestreet/base/pull/194) Fix CI compiler matrix
- Approved but not merged for 7+ days: merge, or say what's blocking? [dune#16658](https://github.com/ocaml/dune/pull/16658) fix(install): preserve codesign metadata when re-signing on macOS
- Approved but not merged for 7+ days: merge, or say what's blocking? [dune#16307](https://github.com/ocaml/dune/pull/16307) refactor(opam_solver): no priority avoidance for avoid-version
- Approved but not merged for 7+ days: merge, or say what's blocking? [dune#15528](https://github.com/ocaml/dune/pull/15528) fix(stdune): preserve Windows flock handles and errors
- Labelled proposal: [dune#8840](https://github.com/ocaml/dune/issues/8840) rfc(pkg): progress indicator for downloads
- Labelled proposal: [dune#12992](https://github.com/ocaml/dune/issues/12992) rfc: n2-style live progress display
- Labelled requires-team-discussion: [dune#4039](https://github.com/ocaml/dune/issues/4039) flambda with -nostdlib and transtive stdlib not finding cmx
- **ocaml/dune**: 44 open items carry a blocking label. Unblock, re-scope or close? Oldest idle: [dune#11444](https://github.com/ocaml/dune/issues/11444) ERROR while compiling dune.3.17.2 ($HOME/.cache/dune perms problem?)

## Numbers (last 90 days)

| Repo | Merged PRs | Median cycle (days) | p85 cycle (days) | Median first review (hours) | Open PRs | Open issues | Stale |
|---|---:|---:|---:|---:|---:|---:|---:|
| All repos | 960 | 0.1 | 1.4 | 26.5 | 128 | 931 | 984 |
| janestreet/core | 0 | n/a | n/a | n/a | 1 | 5 | 5 |
| janestreet/base | 0 | n/a | n/a | n/a | 7 | 9 | 9 |
| ocaml/dune | 960 | 0.1 | 1.4 | 26.5 | 120 | 917 | 970 |
