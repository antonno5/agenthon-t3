# Five hot-path hypotheses: preserved reports

## Executive summary

Five separate agents tested five simulator changes from one commit. Every candidate
passed its selected exact-output checks and all 65 public regressions. DEBUG guards
and lazy SciPy imports met the local performance criterion; history, quantity caching
and order copying did not. These Mac/Rosetta results are preliminary, not official
scores. The user selected DEBUG guards and startup for develop; the combined change
is documented separately in [startup-integration](../startup-integration/README.md).

## Reports and evidence

- [Consolidated comparison](comparison.json), [criterion](criteria.json) and
  [final independent consistency audit](final-consistency-audit.json).
- [DEBUG](agents/debug-logging/README.md): [result](agents/debug-logging/result.json).
- [Book history](agents/book-history/README.md): [result](agents/book-history/result.json).
- [Visible quantity](agents/level-quantity/README.md): [result](agents/level-quantity/result.json).
- [Order copying](agents/order-copy/README.md): [result](agents/order-copy/result.json).
- [Startup](agents/startup/README.md): [result](agents/startup/result.json).

Each `runs/<slug>/` contains independently verified timing/gate/source reports,
regression65, command records, diagnostic logs and event journals. The reports are
byte-identical historical snapshots; their paths, image IDs and measured commits
still identify the original experiments. They do not describe the current combined
build. Original reproduction commands refer to their experimental worktrees.

[archive-index.json](archive-index.json) maps original paths to the repository copies
and binds all 3,261 retained report/evidence files by SHA-256. Raw Parquet traces,
installed-source snapshots and runnable experimental implementations remain in the
original campaign/worktrees and their recorded Git branches. Public reference data
and scenario configurations were not duplicated here. The original campaign directory
is recorded in the index. Rejected changes were not applied to the baseline build.
