Executive summary: The compact trader order registry passes pinned correctness checks: every retained run executes natively, both Parquet journals match exactly, and all shared developer gates pass. Five paired full-container timings per assigned unit are retained, including outliers. The deep-book median is 7.25% faster; cancel-churn is 0.56% slower and lifecycle is 5.31% slower. Performance is experimental on an emulated amd64 host; no production adoption is made.

## Implementation

`baselines/native/agent_orders.hpp` owns independent `Order` values. An index maps
global order ids to vector slots. Active slots form a doubly linked insertion-order
list; deleted slots form a free list. Insertions append to the active tail even
when they recycle an interior slot. Ordinary deletion updates only two neighbors,
with no suffix-position recalculation. Existing-id assignment retains position.

The native engine generates every new order id from one increasing global counter;
therefore insertion order equals the previous map's ascending-id order, including
after recycling and compaction. `cancel_all_orders` copies payloads in that order.
Sending cancels does not remove the agent's snapshots. Partial executions subtract
the delivered quantity; full executions and delivered cancellations remove the
id. Unknown or repeated notifications preserve the prior behavior.

After deletion, capacity greater than 64 is compacted when live size is at most
one quarter of capacity. A rebuild walks insertion order once, updates the lookup,
and resets the free list. Slot ids are stable between these bounded rebuilds;
iterators/references are invalidated by mutation and never escape the registry
in the engine. Retained slot capacity is bounded by `max(64, 4 * active_size)`.
Neither mutable book orders nor message snapshots are shared with this registry.
`book.hpp` and all other accepted optimizations are unchanged.

## Host correctness evidence

Run from this worktree with the source repository's Python environment:

```sh
task_python='/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python'
"$task_python" expirements/20261008-native-hypotheses/h04-agent-orders/host_checks.py
"$task_python" expirements/20261008-native-hypotheses/h04-agent-orders/host_engine_check.py
```

The standalone registry test covers full/partial executions, delayed notifications,
book/message snapshot independence, repeated/unknown cancellations, stable slots,
free-slot reuse, sparse-id gaps, assignment, compaction, copy/move behavior and
50,000 mutations against the former sorted-map bookkeeping. It runs with `-O2`
and AddressSanitizer/UndefinedBehaviorSanitizer. The complete engine also passes
host syntax compilation with warnings as errors.

The full-engine comparison builds the original `engine.cpp` from commit
`ebb266470bee09a426df85d0b2c342b4854b7082` and this candidate on the host. Both use
identical configs produced by the existing public scenario mapper. It compares
all seven trace columns and all twelve message columns, including lengths and
null markers, as exact ordered bytes. All three assigned units pass. This check
uses host ARM64 NumPy/libm and bypasses Arrow; it does not establish pinned Linux
Parquet parity or supply timing evidence. Raw files stay in ignored
`out/h04-agent-orders`; compact evidence is in `result.json`.

## Measurement recipe (already executed under the phase-2 grant)

The executed wrapper is `phase2.py`, invoked through the shared `docker_slot.py`.
It builds from the local tag `track3-native:20261008` and validates its immutable ID
before and after build. Commands below record the completed invocation; they do not
authorize additional repeats. The frozen implementation commit comes from the
READY manifest, and is distinct from the later report commit.

```sh
task_area='/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-native-hypotheses'
task_python='/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python'
"$task_python" "$task_area/docker_slot.py" -- "$task_python" \
  "$task_area/worktrees/h04-agent-orders/expirements/20261008-native-hypotheses/h04-agent-orders/phase2.py"
```

The shared runner asserts actual native execution, immutable images, exact bytes,
schemas and ordered values for both journals, matching emitted SHA256 digests,
and imported shared developer scoring gates for every retained output. It uses
4 CPUs, 16g RAM, 16g memory-swap, no network, Linux amd64 and the named context.
There is one excluded warmup per side and five AB/BA pairs, each with a fresh
baseline. Preserve every outlier. The complete Docker lifecycle is primary;
native core plus trace/write/hash phases are secondary. A correct but slower
candidate is distinct from a correctness failure. Results remain non-rankable.

Only these units are allowed:

- `t3-mp05-cancel-churn-newest`
- `t3-mr-deep-book-state-size`
- `t3-cancelmodify-lifecycle`

No Docker invocation has been executed in phase 1. No full71 regression,
sealed/oracle/answer-key access, scoring implementation copies, pushes, merges or
cherry-picks into develop are part of this experiment. Historical Python results
are motivation only; phase 2 uses fresh contemporary native controls.

## Pinned Docker results

The compact trader order registry passes pinned correctness checks: every retained run executes natively, both Parquet journals match exactly, and all shared developer gates pass. Five paired full-container timings per assigned unit are retained, including outliers. The deep-book median is 7.25% faster; cancel-churn is 0.56% slower and lifecycle is 5.31% slower. Performance is experimental on an emulated amd64 host; no production adoption is made.

| Unit | Baseline median, s | Candidate median, s | Time reduction | Candidate wins | Result |
|---|---:|---:|---:|---:|---|
| `t3-mp05-cancel-churn-newest` | 0.500643 | 0.503448 | -0.56% | 1/5 | correct-but-slower |
| `t3-mr-deep-book-state-size` | 0.648350 | 0.601350 | +7.25% | 4/5 | correct-and-faster |
| `t3-cancelmodify-lifecycle` | 0.422033 | 0.444429 | -5.31% | 2/5 | correct-but-slower |

Positive reduction means faster; negative means slower. The primary clock is Docker State
FinishedAt minus StartedAt, and reductions compare the two five-sample medians.
The excluded warmups and all measured outliers remain in raw evidence. No reruns,
extra repeats, or implementation tuning followed the timing series.

### All five paired samples

Pair order is AB, BA, AB, BA, AB (A = baseline; B = candidate).

| Unit | Pair | Order | Baseline, s | Candidate, s | Candidate time change |
|---|---:|---|---:|---:|---:|
| `t3-mp05-cancel-churn-newest` | 1 | AB | 0.500643 | 0.446169 | -10.88% |
| `t3-mp05-cancel-churn-newest` | 2 | BA | 0.514707 | 0.591380 | +14.90% |
| `t3-mp05-cancel-churn-newest` | 3 | AB | 0.504961 | 0.537108 | +6.37% |
| `t3-mp05-cancel-churn-newest` | 4 | BA | 0.455365 | 0.466121 | +2.36% |
| `t3-mp05-cancel-churn-newest` | 5 | AB | 0.476492 | 0.503448 | +5.66% |
| `t3-mr-deep-book-state-size` | 1 | AB | 0.599284 | 0.648058 | +8.14% |
| `t3-mr-deep-book-state-size` | 2 | BA | 0.692513 | 0.583366 | -15.76% |
| `t3-mr-deep-book-state-size` | 3 | AB | 0.690310 | 0.601350 | -12.89% |
| `t3-mr-deep-book-state-size` | 4 | BA | 0.642869 | 0.619608 | -3.62% |
| `t3-mr-deep-book-state-size` | 5 | AB | 0.648350 | 0.587816 | -9.34% |
| `t3-cancelmodify-lifecycle` | 1 | AB | 0.449321 | 0.403668 | -10.16% |
| `t3-cancelmodify-lifecycle` | 2 | BA | 0.436818 | 0.490692 | +12.33% |
| `t3-cancelmodify-lifecycle` | 3 | AB | 0.422033 | 0.421560 | -0.11% |
| `t3-cancelmodify-lifecycle` | 4 | BA | 0.416661 | 0.474349 | +13.85% |
| `t3-cancelmodify-lifecycle` | 5 | AB | 0.412644 | 0.444429 | +7.70% |

### Secondary phase medians

These participant phase measurements supplement the full-container clock. Native core
includes trace finalization; it is not a matcher-only measurement. All five secondary
samples for every phase and side are retained in `result.json`.

| Unit | Phase | Baseline, s | Candidate, s |
|---|---|---:|---:|
| `t3-mp05-cancel-churn-newest` | `configuration` | 0.002123 | 0.002400 |
| `t3-mp05-cancel-churn-newest` | `hashing` | 0.030570 | 0.032627 |
| `t3-mp05-cancel-churn-newest` | `parquet_write` | 0.150622 | 0.150614 |
| `t3-mp05-cancel-churn-newest` | `simulation_and_trace_finalize` | 0.082225 | 0.079844 |
| `t3-mr-deep-book-state-size` | `configuration` | 0.002727 | 0.002438 |
| `t3-mr-deep-book-state-size` | `hashing` | 0.033915 | 0.031589 |
| `t3-mr-deep-book-state-size` | `parquet_write` | 0.194355 | 0.189800 |
| `t3-mr-deep-book-state-size` | `simulation_and_trace_finalize` | 0.164155 | 0.143958 |
| `t3-cancelmodify-lifecycle` | `configuration` | 0.002203 | 0.002441 |
| `t3-cancelmodify-lifecycle` | `hashing` | 0.019447 | 0.020875 |
| `t3-cancelmodify-lifecycle` | `parquet_write` | 0.126468 | 0.130655 |
| `t3-cancelmodify-lifecycle` | `simulation_and_trace_finalize` | 0.056021 | 0.056427 |

### Provenance and correctness

Frozen implementation: `d1119e633be385478441c8f0e2e1623d258f21e7`.
Production image source commit: `7a5abca889c1fdd77e01edfa9f85762becc1f17b`;
candidate source base: `ebb266470bee09a426df85d0b2c342b4854b7082`.

Baseline image: `sha256:e7f01b18f284f8ff9a5e0fb5591a80dfdaa9e051f76e7076e07ae82293aedd89`.
Candidate image: `sha256:514d208681e44c99af3b7ef2f9d74b3eea7dbb0554b980000c56a44dea1743ca`.
Focused-test builder image: `sha256:335cdaf7ba08dbd50ab3626139f9051352f56d9064d741403bec079732b299c9`.

The baseline tag was checked before and after both builds, before timing and after
timing; every check found the immutable production image. All Docker operations
ran inside the campaign's exclusive slot. Shared Dockerfile, runner and slot hashes
were checked against `plan.json`; the shared checker SHA256 is also retained.

Pinned registry tests passed in optimized and UBSan builds. Both runtime probes
confirmed Python 3.11.17, Arrow 15.0.2, x86_64 and a loaded native extension.
All 36 retained outputs (6 excluded warmups, 30 timed runs) passed actual-native
assertions, emitted digest validation and shared developer gates. All 48 cross-side
and repeat-stability comparisons passed exact bytes, schemas and ordered values
for both journals. Native source hashes match the frozen READY manifest.

Raw build/check logs: `out/h04-agent-orders/phase2`. Raw journals, gate results,
container state timestamps and comparisons: `out/h04-agent-orders/docker`.
Large evidence and Parquet files are ignored and have not been committed.

This is an ARM64 Mac running emulated Linux amd64 containers, not official timing
hardware. The sample spread and fixed container costs limit conclusions from small
median changes. Developer results are non-rankable, and the candidate stays experimental.
