# Active start offset for numeric price keys

## Executive summary

Historical median simulation-time changes: STP oldest -0.8%, Deep-book -17.8%, Cancel churn -12.7%. Negative means less time. Only the new candidate was launched; separate schedules do not establish a causal speedup. At measurement time, the offset implementation remained experimental.

## Subsequent develop integration

The user subsequently selected this measured implementation for `codex/develop`.
See [the integration record](integration.json) for the adopted source identity
and fresh-installation checks. `policy.json` and `result.json` retain the
experiment's historical `adopted: false`; the integration record describes
the later decision. Existing correctness and timing evidence is reused.

The candidate passed 146 order-book tests, 18 warmup/measured runs on the
three requested units, 33 exact journal/stability comparisons and 210 synthetic
domain comparisons. One separate cancellation diagnostic run also passed actual
developer gates and exact journal comparison. No old timing container was run.

## Implementation and frozen policy

The candidate inherits the measured numeric-vector image adopted in develop.
Its only changed installed Python file is `matching/state.py`. Head key removal
advances a private active-start offset; head insertion reuses an unused prefix
slot. Binary search is limited to active keys and returns a logical level index.
Middle/tail changes maintain active keys; public slices/reorderings rebuild once.
Empty books reset storage. Compaction occurs when the discarded prefix reaches
64 keys and is at least as large as the live key count. Certified storage is
bounded by twice the live level count plus 63 integer slots. Removed keys do not
retain PriceLevel objects. The actual level list continues to shift.

Tests cover both sides, head reuse without key-array shifts, compaction boundaries,
middle/tail/slice changes with nonzero offsets, sustained memory bounds, removed
level reclamation, deepcopy/pickle and price edits. Existing semantic book tests
remain unchanged. The vector invariant tests compare the active slice.

## Measurement scope

Only the offset candidate is launched under colima-agenthon, linux/amd64, four
CPUs, 16 GiB and no network, strictly serially. Each requested public unit has
one excluded warmup and five measured repetitions. Full developer gates and
exact event/message journals are checked for every run. Current numeric-vector
timings are reused from `out/price-vector-20261007/`; the earlier direct-key bisect
image is not the timing baseline. No full corpus regression is launched.

The unchanged synthetic benchmark retains seven repetitions at six depths, with
200 warmup and 2,000 measured operations for each case. Index mutation is timed.
Existing-level operations and middle/new-level churn reuse saved comparable cases.
Head-offset usage is proved by structural tests and measured separately through
an untimed cancellation diagnostic; it has no invented historical timing ratio.

## Requested simulator measurements

Medians in seconds. Positive time change means slower. Every sample, mean and
range is retained in `result.json`.

| Unit | Container: vector | Container: offset | Change | Simulation: vector | Simulation: offset | Change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| STP oldest | 3.947 | 3.900 | -1.2% | 2.529 | 2.508 | -0.8% |
| Deep-book | 19.270 | 16.077 | -16.6% | 17.080 | 14.039 | -17.8% |
| Cancel churn | 11.466 | 10.106 | -11.9% | 9.392 | 8.196 | -12.7% |

Simulation-time ranges across all five measured repetitions:

| Unit | Vector min–max, s | Offset min–max, s |
| --- | ---: | ---: |
| STP oldest | 2.451–3.145 | 2.446–2.625 |
| Deep-book | 14.872–17.773 | 13.536–14.646 |
| Cancel churn | 9.315–9.558 | 8.056–9.506 |

## Untimed cancellation diagnostics

The instrumented run records 48008 cancellation requests,
47933 successful cancellations and 22265 cancellations
removing a price level. Of these, 3271 remove its first level
(14.7% of successful level-removing cancels).
Across fills and cancels combined, 22324 keys are removed,
3318 head removals advance the offset,
3235 insertions reuse a prefix slot, and
0 compactions occur. The vector is rebuilt
0 times. Full counters and search-depth distribution are
in `result.json`. Instrumented operation times include profiling overhead and
are not comparable benchmark samples.
Middle cancellations account for 65.2%
of level-removing cancellations. At search time, the live price count on
one side is most often five or six; see the complete histogram in `result.json`.

## Comparable synthetic operations

Medians in microseconds per operation. Positive means slower. These component
timings cannot substitute for whole-simulator results.

| Levels | Operation | Vector, µs | Offset, µs | Change |
| ---: | --- | ---: | ---: | ---: |
| 1 | lookup | 1.251 | 1.264 | +1.0% |
| 1 | add_existing | 1.828 | 1.829 | +0.1% |
| 1 | cancel_existing | 2.801 | 2.786 | -0.5% |
| 1 | modify_existing | 4.314 | 4.307 | -0.2% |
| 1 | new_level_churn | 7.223 | 7.189 | -0.5% |
| 4 | lookup | 1.628 | 1.657 | +1.7% |
| 4 | add_existing | 1.717 | 1.746 | +1.7% |
| 4 | cancel_existing | 2.901 | 2.837 | -2.2% |
| 4 | modify_existing | 4.671 | 4.671 | +0.0% |
| 4 | new_level_churn | 7.998 | 8.078 | +1.0% |
| 16 | lookup | 1.770 | 1.785 | +0.8% |
| 16 | add_existing | 1.819 | 1.829 | +0.5% |
| 16 | cancel_existing | 2.795 | 2.885 | +3.2% |
| 16 | modify_existing | 4.874 | 4.852 | -0.5% |
| 16 | new_level_churn | 8.123 | 8.516 | +4.8% |
| 64 | lookup | 1.823 | 1.849 | +1.4% |
| 64 | add_existing | 1.831 | 1.868 | +2.1% |
| 64 | cancel_existing | 2.876 | 2.960 | +2.9% |
| 64 | modify_existing | 4.700 | 4.780 | +1.7% |
| 64 | new_level_churn | 8.207 | 8.716 | +6.2% |
| 256 | lookup | 1.863 | 1.939 | +4.1% |
| 256 | add_existing | 2.102 | 2.163 | +2.9% |
| 256 | cancel_existing | 2.945 | 3.044 | +3.3% |
| 256 | modify_existing | 4.944 | 5.006 | +1.2% |
| 256 | new_level_churn | 8.410 | 8.964 | +6.6% |
| 1024 | lookup | 2.072 | 2.141 | +3.3% |
| 1024 | add_existing | 2.244 | 2.274 | +1.3% |
| 1024 | cancel_existing | 3.133 | 3.218 | +2.7% |
| 1024 | modify_existing | 5.290 | 5.217 | -1.4% |
| 1024 | new_level_churn | 9.174 | 9.515 | +3.7% |

## Assessment

The head-offset mechanism operates as intended, with prefix reuse and bounded storage verified.

24 of 30 comparable synthetic medians are slower; component timings do not corroborate the large full-run reductions.

Cancel-churn head removal is a minority of level-removing cancellations; the price search mostly sees five or six live levels on a side.

Full-run differences remain observations against saved schedules. No concurrent load, VM scheduling or host frequency attribution was measured.

At measurement time the candidate was kept experimental: these results do not establish a repeatable net gain from the offset alone.


## Reproduction

Build the isolated image using
`docker --context colima-agenthon build --platform=linux/amd64 --network=none
-t python-book-price-offset:20261007 experiments/price-offset`.
Run `.venv/bin/python experiments/price-offset/run_experiment.py --out
out/price-offset-new` with a fresh directory. Source guards reject changed
baseline modules. Regenerate the report with `.venv/bin/python
experiments/price-offset/summarize.py --out out/price-offset-new`.

The measurement run did not include main-engine adoption, submission repacking or registry publication.
Stored baseline and candidate measurements are unpaired and local/non-rankable.
