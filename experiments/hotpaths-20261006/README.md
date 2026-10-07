# Hot-path hypothesis campaign, 6 October 2026

## Executive summary

Five agents completed five isolated experiments from commit `0af6939d8815b9e39376e5c6f7fef3538cec06f1`. Every candidate passed its selected exact-output checks, actual developer gates, independent installed-source reconstruction and all 65 public regressions. The manager independently verified artifact digests, timings and Docker isolation. The final consistency audit rechecked 545 file bindings, 270 selected runs, 330 exact trace-file comparisons and 325 successful regression records.

| Hypothesis | Median time reduction on declared primary workloads | Verdict |
| --- | --- | --- |
| DEBUG preparation | t3-momentum-mix-priority: +6.84%; t3-mr-deep-book-state-size: +8.64% | `local_gain_supported_requires_linux_confirmation` |
| Book history analysis | t3-mr-deep-book-state-size: -1.15% | `not_supported_regression_guardrail` |
| Visible quantity cache | t3-mr-deep-book-state-size: -10.24%; t3-mr-cancel-replace-churn: -8.08% | `not_supported_regression_guardrail` |
| Order copying | t3-mr-cancel-replace-churn: +1.59%; t3-mp07-heavy-flow-oldest: +19.76% | `not_supported_regression_guardrail` |
| Process startup | t3-s001-price-time-priority: +20.23%; t3-s012-partial-fill-cancel-race: +10.69% | `local_gain_supported_requires_linux_confirmation` |

Positive percentages mean shorter full-container runs. All evidence is preliminary: Mac ARM64, Colima linux/amd64 through Rosetta, `rankable=false`. Three pairs cannot establish general or official performance. Combined changes were not measured. No changes were merged, pushed or submitted.

## Method and controls

The preregistered criterion requires at least 5% lower median full Docker State lifetime on **every** declared primary workload and no median slowdown greater than 5% on **any** selected workload. Each unit uses three unprofiled AB/BA/AB pairs; warmups and profiles are excluded. Raw pairs, overlapping ranges and inconsistent pair directions appear in `comparison.json`. Component benchmarks and import/init probes are diagnostic evidence only.

The manager owned one serial Docker slot, using immutable image IDs, 4 CPUs, 16 GB memory and swap, and no network for timed runs. Container State and independently retained Docker start/die events confirm isolation. All 52 installed Python files were reconstructed from each measured Git commit and compared byte for byte. The 71-unit corpus and reference cache were frozen.

A Docker guest-clock anomaly invalidated the original DEBUG mp02 timings: its serial containers had impossible overlapping timestamps. The complete unit was rerun with the same images and full AB/BA/AB schedule under a recorded retry policy. All original evidence remains under `runs/debug-logging/differential`; selected evidence combines four original units with the complete `differential-clock-retry` unit. No timing was selected for being favorable.

The common source writes a forbidden batch-root `profile.json`. The identical contract wrapper on both sides removes only this diagnostic after successful execution. Original rejection is retained; scorer, sanitation rules, thresholds and public references were unchanged. A separate negative control altered one sent message to have a dangling causal parent, updated the ledger digest, and was rejected by the actual causality gate.

Timestamp-based bytecode-cache inventories are recorded for each image. Measurements include the images as built and disposable-process startup; they do not establish steady-state effects or attribute observed slowdowns to recompilation.

## Scope and evidence

- **DEBUG preparation**: Guard 65 eager DEBUG formatting calls in six files. Component rendering avoided at disabled DEBUG; practical verdict uses full runs.
- **Book history analysis**: Replace full DataFrame with complete QuoteTime Series; existing Python dropout reducer unchanged. Incremental stage-2 prototype rejected: mutable historical L2 aliases can invalidate cached metrics. Compact history was not shipped; no claim that historical snapshots were eliminated.
- **Visible quantity cache**: Maintain exact visible quantity through level mutations, including partial and PTC fills. External direct edits to order.quantity or visible_orders can bypass cache maintenance. L2 snapshot caching was deferred; it is not included in the measured patch.
- **Order copying**: Specialized exact-core immutable-tag copying; skip one safe PTC outer snapshot. Preserves upstream subtype/custom-attribute and memo limitations; no incidental semantics fixes. Rejected slower all-field atomic scan is retained separately.
- **Process startup**: Load optional scipy.spatial.distance lazily, preserving explicit and wildcard exports. Import/init probes diagnose startup; only full simulations determine practical gain. Optional latency-distance fallback still loads SciPy on first use.

`comparison.json` is the canonical consolidated result; `manifest.json` records branches, final evidence commits and common ancestry. `criteria.json` preserves the criterion registered before timings. Each `runs/<slug>/result.json` is a copy of the final agent result with independent manager verification. The same report is committed inside its own worktree at `experiments/<slug>/result.json`.

Per hypothesis, `pipeline.json`, `manager-audit.json`, `agent-evidence-audit.json`, `independent-source-audit.json`, `bytecode-cache-inventory.json`, `manager-gate-recheck/summary.json`, `regression65/report.json`, raw differential runs, commands, image sources and SHA-256 bindings provide reproducible evidence. Failed or superseded preparations are retained separately and do not enter selected timings.
