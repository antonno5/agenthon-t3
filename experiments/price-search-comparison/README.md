# Python price-search comparison

## Executive summary

The implementations have different strengths. The hybrid makes existing-price
lookup about 3.3x faster at four levels and 6.0x faster at 1,024 levels in the
synthetic benchmark. Its insert-and-delete churn is about 1.2x and 9.8x slower at
those sizes because the dictionary stores list positions and must adjust the
suffix after middle mutations. It does not make every book operation faster.

In the full simulator, bisect has lower simulation medians on five of six units;
the hybrid wins batch. Cancel-churn favors bisect in all five measured pairs,
with approximately 10% less simulation time. Batch favors the hybrid in four of
five simulation pairs, with approximately 13% less simulation time. The STP-newest
and deep-book simulation median differences are only about 1.5–1.6%, with mixed
paired results; these do not establish a reliable speed difference. These local
VM measurements, including a documented VM recovery, do not establish production
latency or statistical significance. For the current cancel/churn workload, the
simpler bisect implementation is the stronger default; a workload dominated by
operations on existing levels can favor the hybrid.

Both isolated worktrees start from the same stage-3 mutation base. The user
removed full candidate regressions from the critical path. Order-book suites
passed 99 tests for bisect and 101 for the hybrid. All 72 scheduled simulator
runs were accepted and all 96 stability/pair journal comparisons were exact.
All 210 synthetic case/pair domain comparisons matched. On 7 October 2026, the
user selected bisect for the default engine in `codex/develop`; the hybrid remains
an archived comparison variant. This comparison does not measure either candidate
or stage 3 against the preceding linear-search implementation.

## Implementations

The shared base is `ac1baaba2c89ce3ac9e5df58be57dab2daf96082` on
`codex/book-mutations-base`. Stage 3 centralizes removal, quantity changes, queue
movement and empty-level deletion. Lifecycle notifications, snapshots, history,
PTC counterpart operations and time priority retain their original ordering.
This comparison does not measure stage 3 against its predecessor.

| Variant | Branch | Implementation |
| --- | --- | --- |
| `bisect` | `codex/book-bisect` | List subclass with a lazy ordering certificate; binary search directly over levels, with no persistent price dictionary. |
| `dict + bisect` | `codex/book-dict-bisect` | List subclass with `price -> position` dictionary; existing-price lookup uses the dictionary, new-price placement uses binary search. |

Both preserve public list operations and fall back to original traversal for
plain replacement lists and unusual levels. The hybrid adjusts suffix positions
when a level is inserted/deleted in the middle; append and final-level deletion
avoid that loop. Price queues are unchanged in this experiment. Neither candidate
adds an order-ID index.

## Fixed measurement schedule

`policy.json` was frozen before either candidate was timed. Its original digest is
`4d8e1ac25c5bb5a7ffeb5e9121de3a50b20f6ab5c3dc5061248572b2fe1b74b9`.
`validation-override.json` records the user's subsequent removal of full candidate
regressions and repeated whole-repository tests. The timing schedule is unchanged.
The shared-base regression had already finished; it is retained as existing
information. It is not required by the revised comparison workflow.

Six public units run five measured pairs each after one warmup pair. Pair order
alternates AB/BA. Containers run serially under `colima-agenthon`, `linux/amd64`,
4 CPUs, 16 GiB, networking disabled, without detailed profiling. The unchanged
`scripts/run_differential_experiment.py` checks both event and message journals
against public references and between candidates on every run, including all
four batch sub-scenarios. In its generic output, `baseline` means the bisect
candidate here; it does not mean canonical ABIDES.

The primary metric is full Docker State lifetime, including cold startup,
simulation and output. Secondary simulation time is self-reported by the
adapter; batch simulation time sums its four sub-scenario phases. Every sample
is retained, including slowdowns. This is a local macOS VM/emulation comparison;
it does not establish production latency or statistical significance.

The synthetic benchmark runs seven alternating pairs, 200 discarded warmup
operations and 2,000 measured operations per case. It covers 1/4/16/64/256/1024
levels and lookup, add, cancel, modify and new-level churn. Initialization is
excluded; mutations, queue operations and index maintenance remain timed.
Domain output hashes must match for every case/pair. `microbench.py` is frozen by
the policy's SHA-256. These figures describe warm synthetic books and are separate
from the full simulator timings.

## Compatibility limits

Normal public list methods/operators and price/side assignments invalidate the
metadata. Explicit calls to base `list` mutators can bypass subclass hooks;
same-length reordering by `list.__setitem__` or `list.reverse` is unsupported.
Direct writes through `vars(level)` also bypass invalidation. Plain replacement
lists retain original traversal for integrations using those techniques.
Duplicate prices and custom comparator objects use compatibility paths as needed.
All direct queue storage and FIFO behavior remain unchanged.

## Evidence

`result.json` records image IDs, exact commits, all measured samples, medians,
paired ratios and synthetic results. Raw builds, installed-source inventories,
order-book test logs, canonical output trees and timing summaries are retained
under `out/price-search-comparison/`. The installed-source comparison allows only
state, price-level and hybrid-index changes relative to the common base. Existing
batch-adapter edits are identical in both images and receive no speedup credit.
The worktrees remain available independently. The user explicitly selected
bisect for integration on 7 October 2026; this does not change the frozen timing
results or historical worktree/image identities.

## VM recovery

During the candidate run in the final deep-book timing pair, the Colima VZ VM
entered `error` state and Docker RPC stopped responding. This is an environment
failure without a completed candidate timing, not evidence of an algorithm
slowdown. `out/price-search-comparison/vm-incident/` preserves the incident, partial
summary, host-agent error log and container state after recovery.

After restarting only the `agenthon` profile with unchanged resources, the driver
reuses 29 completed pairs (including warmups). A separate recovery warmup pair is
excluded from timing statistics. The interrupted pair is rerun in its original
AB order; its already completed unpaired A remains in the initial evidence and
is excluded from the paired summary. The original runner source, `run_once`,
output validation and comparison functions are unchanged. A scratch recovery
driver supplies cached records for already completed pairs and local evidence
links to their already sanitized output directories. The remaining scheduled
pairs run normally. The final summary is under `differential-resumed/`; the initial
`differential/` evidence is preserved. No full regression is added after recovery.

## Measured results

Medians of five measured repetitions per variant, in seconds. Warmups are
excluded. Batch simulation time is the sum of its four sub-simulations.

| Unit | Container: bisect | Container: hybrid | Simulation: bisect | Simulation: hybrid |
| --- | ---: | ---: | ---: | ---: |
| Price-time priority | 1.295 | 1.467 | 0.060 | 0.067 |
| STP newest | 4.891 | 4.668 | 2.886 | 2.929 |
| STP oldest | 4.616 | 5.517 | 2.830 | 3.436 |
| Batch (four scenarios) | 3.591 | 3.010 | 1.605 | 1.396 |
| Deep-book state size | 23.608 | 24.421 | 20.313 | 20.637 |
| Cancel churn | 10.253 | 11.323 | 8.320 | 9.282 |

The full-container metric includes startup and output, so it can favor a different
variant than the simulation phase (as in STP newest). No startup overhead is
credited to the matching algorithm. Per-unit min/max ranges, all five samples
and within-pair ratios are in `result.json`. No aggregate score or selected best
repeat is reported.

| Synthetic operation | Levels | Bisect, µs/op | Hybrid, µs/op | A/B ratio |
| --- | ---: | ---: | ---: | ---: |
| `lookup` | 4 | 2.157 | 0.651 | 3.31 |
| `add_existing` | 4 | 2.208 | 0.810 | 2.73 |
| `cancel_existing` | 4 | 3.221 | 2.038 | 1.58 |
| `modify_existing` | 4 | 5.007 | 3.650 | 1.37 |
| `new_level_churn` | 4 | 9.017 | 10.822 | 0.83 |
| `lookup` | 1024 | 4.492 | 0.748 | 6.00 |
| `add_existing` | 1024 | 4.715 | 1.016 | 4.64 |
| `cancel_existing` | 1024 | 5.586 | 2.222 | 2.51 |
| `modify_existing` | 1024 | 8.042 | 4.065 | 1.98 |
| `new_level_churn` | 1024 | 14.985 | 146.293 | 0.10 |

Synthetic medians use seven repetitions. A/B > 1 favors the hybrid. Lookup
measures only existing-price traversal; new-level churn measures one insertion
and cancellation per operation. Synthetic cancel/modify retain seeded levels,
so they do not pay empty-level deletion/index-shift costs. These synthetic ratios
are not simulator speedups. All six sizes and every sample are in `result.json`.

### Frozen source identity

| Variant | Commit | Immutable image |
| --- | --- | --- |
| `bisect` | `7d9f92d4f218d2f181b51f4f99f99ff240267ded` | `sha256:484ef5d44a7b71da3f2e67af21c2c8744510467648aaedf17aa083186e1dc886` |
| `dict-bisect` | `924b5c2b2bf7186d70d2efdc067cf472e806aff8` | `sha256:92c149d21b210b41d56ae5bc5f5cf322145293433a7bd5d4b03379268c008bab` |

The primary checkout now contains the common mutation refactor and the exact
measured bisect source. The hybrid implementation remains in its worktree.
Queue implementations are unchanged.

## Adoption

On 7 October 2026, bisect was selected for `codex/develop` by explicit user
instruction. The integrated matching sources, compatibility shims, manifest and
installer are byte-identical to the measured bisect worktree. This uses the
existing image/source audit and runtime/journal evidence rather than repeating
the full public regression. Installer and documentation guards are checked on
the integrated tree before committing. The serial batch adapter's already
existing output-contract fix is committed separately; its bytes were held equal
in both measured images and are not credited to price-search performance.
