Executive summary: the recipient scheduler preserves exact outputs and passes
pinned Docker checks, but the fixed local timing series does not support a general
throughput improvement. The candidate is 0.85% faster on coarse tick ties and
3.66–16.81% slower on the other four units by complete-container medians. All
50 timing samples and 10 excluded warmups are retained. These emulated local
results are not official ranking evidence; the optimization is not adopted.


## Implementation and equivalence argument

`baselines/native/scheduler.hpp` keeps original arrivals in a heap. Each recipient
has a waiting heap sorted by `(sender, recipient, message_id)` and one entry in an
indexed global min-heap. The global comparison uses
`(time, sender, recipient, message_id)` exactly as the original scheduler. There
are no stale global entries. A message first enters a waiting queue only after the
kernel pops it and detects that its recipient is busy. Message references and
`t_send`, original `t_recv`, and causal metadata remain unchanged.

Nonnegative delays make kernel time and each recipient's busy time monotone.
All already-deferred messages for a recipient can therefore share its latest busy
time: the baseline would pop each older waiting entry, detect the same busy
recipient, and requeue it to that time. Those operations have no handler, ledger,
message release, or RNG effect. Deferring an arrival can advance an existing
waiting group before the old group is popped; any intervening deliveries to that
recipient can only advance its busy time further. Once eligible, waiting messages
must sort by sender/recipient/id rather than their original arrival time. New
arrivals remain independent and are compared with the waiting head by the full
original key. The implementation never precomputes `max(arrival, busy)` at send.

This elimination of pure requeues is valid only inside the positive, inclusive
stop horizon. When a deferral would move beyond `stop_time`, all waiting entries
are materialized at their current logical times and the scheduler switches
permanently to the original arrival heap. Every skipped requeue was at a positive
time within the horizon. Original arrivals have never been moved in advance, so
this preserves the first post-stop pop: it may deliver, or requeue and terminate.
The kernel still tests `current_time != 0 && current_time <= stop_time` at the
start of each iteration. Empty queues and initial wakeups keep the original loop.
Negative latency bounds, negative delays, or nonpositive start times use the
original heap algorithm from the start. A zero/nonpositive deferred time also
switches to that algorithm. These fallbacks preserve backwards-clock behavior.

## Scenario selection frozen before timing

Counts below are untimed runs of the independently extracted pinned baseline,
using only public scenario parameters. Heap size is the maximum total queue;
backlog is the maximum number of distinct deferred `(message_id, recipient)`
pairs, not the number of requeue attempts.

| Timing unit | Deliveries | Requeues | Requeues / delivery | Max heap | Max backlog / recipient | Reason |
|---|---:|---:|---:|---:|---:|---|
| t3-coarse-tick-ties | 63,338 | 128,084 | 2.02223 | 57 | 17 / 17 | Largest repeated busy-queue pressure, ties |
| t3-eq-deterministic-baseline | 18,568 | 8,130 | 0.43785 | 64 | 32 / 23 | Deterministic synchronized recipients |
| t3-s012-partial-fill-cancel-race | 178,236 | 84,132 | 0.47203 | 40 | 8 / 8 | Busy queue during fill/cancel races |
| t3-gb-pop-horizon-scale | 892,129 | 36,987 | 0.04146 | 309 | 14 / 7 | Scale and scheduler overhead at low pressure |
| t3-s001-price-time-priority | 664 | 38 | 0.05723 | 23 | 2 / 2 | Mandatory canonical order priority case |

`t3-mp07-heavy-flow-oldest` has only 126 requeues / 64,131 deliveries (0.00196),
with max heap 50 and max backlog 2. It moves to correctness-only, retaining STP
oldest coverage, while `s012` moves to timing. This decision precedes all Docker
measurement; the coordinator must synchronize the frozen policy into its plan.

Other correctness-only controls are `t3-s019-latency-jitter-kendall` (23 requeues;
random jitter), `t3-eq001-pareto-latency-tail` (1,760; tail latency), and all five
organizer-declared markets in `t3-gbatch-hetero-mix` (mixed agent kinds and process
isolation). Both journals and all shared developer gates remain mandatory for
all timing and control scenarios. No all-public or regression65 run is requested.

## Phase 1 evidence and reproduction

Run these from the worktree root using the shared read-only `.venv/bin/python`:

```sh
python expirements/20261008-radical-hypotheses/h03-recipient-scheduler/tests/host_checks.py --counts-only
python expirements/20261008-radical-hypotheses/h03-recipient-scheduler/tests/host_checks.py
python expirements/20261008-radical-hypotheses/h03-recipient-scheduler/tests/run_scheduler_tests.py
```

The scripts extract source from base commit
`a7fb6c36d88395e49d40bc3b71e6dc79b2099bc9` using Git and compile locally with
`-fno-fast-math -ffp-contract=off`. They do not install dependencies or invoke
Docker. They read public parameters from the shared materialized corpus, leaving
its cards, scorer and traces untouched. Extracted baseline source and binaries
live under the ignored local [evidence directory](evidence/).

[Structural counts](structural_counts.json) describe the original Sim.
[Scheduler checks](scheduler_checks.json) compare deliveries, all immutable entry
fields, busy clocks, final popped entry and requeue status, final current time,
and every remaining queued entry. The comparator and original heap helpers are
extracted independently, with hashes recorded. There are 24,698,436 generated
queue operations: baseline performs 6,470,396 pops and candidate 4,645,099. These
counts are structural evidence, without a timing clock. The same tests pass
ASan/UBSan. Explicit cases cover busy-time sorting, stop inclusion, final
post-stop delivery and requeue, empty heap, initial zero time, popped zero,
and horizon fallback before a pending post-stop entry could be skipped.

[Full Sim checks](host_sim_checks.json) compare length-prefixed bytes of all 7
trace columns and all 12 message columns. All 93 configurations match. The 80
additional cases vary RNG seed, default/exchange/pipeline delays, inclusive stop
boundaries, initial zero time and negative latency fallback. Raw input and column
files are linked from each row and remain local in `evidence/host/`.
The host is arm64 and uses one common `math.log` parameter mapping for both
engines. These tests establish host differential behavior; pinned x86 numeric
path, Arrow byte equality, actual native provenance and shared developer gates
are phase 2 checks. [Test evidence](test_evidence.json) records this distinction.
[Read-only manifest and firewall checks](manifest_checks.json) passed on all nine
selected public units. The original checkout has the pinned base commit and clean
`baselines/`; scorer, cards, checker, adapter, writer and numeric build script are
unchanged in this isolated branch.

## Phase 2 recipe and measurement contract

[Dockerfile](Dockerfile) extends the coordinator's shared overlay recipe only with
provenance metadata and a separate Linux queue correctness test binary;
[recipe.json](recipe.json) records its hash and build command template. It rebuilds
only the native extension on the common pinned baseline. Python 3.11,
PyArrow 15.0.2 and `baselines/build_native.py` floating-point flags are unchanged.
Use the coordinator's dispatched baseline identity as `BASE_IMAGE`.
All Docker builds, probes, correctness runs and timings must use the exclusive
`docker_slot.py`; do not alter VM lifecycle or global Docker context.

[policy.json](policy.json) freezes five timing units, four controls, linux/amd64,
explicit `colima-agenthon`, 4 CPU, 16 GiB memory and swap, and disabled runtime
network. The unchanged differential checker and shared gates must confirm both
journals' byte/schema/ordered-value equality and actual native execution before
measurement. Each unit gets fresh baseline/candidate runs, one excluded warmup
per side and five AB/BA pairs, retaining every outlier. The primary clock is
Docker `FinishedAt - StartedAt`; core/finalization/write/hash phases are separate.
Full-run percentage is `100 * (1 - median(candidate) / median(baseline))`, positive
for faster, negative for slower. No extra repeats or tuning after results, and no
speed claim if correctness fails. `result.json` now contains the actual fixed phase 2b series. No merge, push or production adoption is authorized here.

## Phase 2a pinned checks

`tests/phase2a.py` must run as one subprocess under the coordinator's serial slot.
It builds the immutable candidate, audits installed Python files and the native
extension/source manifest, runs the 12,000 queue cases with pinned Linux g++,
and compares 80 generated full-Sim configurations in both pinned images.
`tests/pinned_cases.py` uses the installed native binding, preserving its actual
x86 NumPy parameter mapping. It compares every binding value and exception, and
checks bytes/schema/ordered values in both journals for every nonempty case via
the unchanged repository checker. Negative latency, zero initial time and stop
boundaries from the host cases are included. The shared runner then performs
actual-native and developer-gate checks on every declared timing/control unit.
This phase creates no timing samples and calculates no speed percentage.

Pinned phase 2a is complete. [Readiness](phase2-readiness.json) records the immutable
image, source audit, runtime versions and evidence hashes. The candidate image is
`sha256:1e7fcc47642b134db12feba0cc04a91475785f7ffdf0d38af48a93ccd196f1e7`.
The build/source commit is `b05b1a210e7b0f690a802095954648d65cfd0a45`;
subsequent commits publish report documents without changing native sources.
All 18 unit runs (13 markets per image, counting batch subs) were accepted by the
unchanged differential checker and shared developer gates. Both journals matched
bytes, schema and ordered values, with actual native execution in every market.
The pinned Linux queue test passed 12,000 generated and 9 explicit cases. The
80 generated Sim cases matched every binding value/exception/schema and all
60 produced journal files, including 12 negative-latency cases and 8 zero-start
cases. Source manifests, installed Python files, baseline root layers, and the
Python 3.11.17 / NumPy 1.26.4 / pandas 1.5.3 / Arrow 15.0.2 / SciPy 1.17.1 stack
were audited. No timing samples were run.

Raw [phase 2a evidence](evidence/phase2a-03/) and
[controls summary](evidence/phase2a-03/controls/summary.json) remain ignored locally.
Two preliminary failures are retained in `evidence/phase2a-01/` (relative script
path guard, before Docker) and `evidence/phase2a-02/` (BuildKit interpreted a local
image ID as a registry name). Both were corrected in committed test orchestration.
The build uses the coordinator baseline tag after asserting its exact immutable
ID under the lock, and verifies the candidate preserves all baseline root layers.
Runtime probes and correctness runs use immutable image identities.

## Completed fixed paired timing

The single authorized phase 2b series completed with **60 accepted runs**: 50
timed samples and 10 excluded warmups. Both journals preserve byte/schema/ordered
value equality, actual native execution and unchanged shared developer gates.
Native sources remained unchanged throughout the run. The four correctness-only
units also passed the separate phase 2a controls (including every batch market).

Primary clock: Docker `FinishedAt - StartedAt`, including the whole container.
Each unit has one excluded warmup per side followed by five pairs ordered
`AB, BA, AB, BA, AB` (A baseline, B candidate). Every sample and outlier is kept;
there were no extra repeats, post-result tuning, code changes or production adoption.
Runs used `colima-agenthon`, linux/amd64, 4 CPU, 16 GiB memory/swap and network none.
These are local Linux amd64 runs emulated on a Mac arm64 host, `rankable: false`.
Full-run reduction is `100 * (1 - median(candidate) / median(baseline))`;
positive means faster and negative means slower.

| Timing unit | Baseline median (s) | Candidate median (s) | Full-run reduction | Faster pairs |
|---|---:|---:|---:|---:|
| t3-coarse-tick-ties | 0.398980278 | 0.395569199 | +0.85% | 3/5 |
| t3-eq-deterministic-baseline | 0.289331119 | 0.300787170 | -3.96% | 2/5 |
| t3-s012-partial-fill-cancel-race | 0.520623768 | 0.577441461 | -10.91% | 1/5 |
| t3-gb-pop-horizon-scale | 1.096446378 | 1.280710363 | -16.81% | 1/5 |
| t3-s001-price-time-priority | 0.304854649 | 0.316010948 | -3.66% | 2/5 |

The candidate has a small positive full-run median difference only on coarse
tick ties (+0.85%, faster in 3/5 pairs). The other four medians are slower.
This fixed local series does not support an overall throughput benefit for H03.
The small coarse-tick difference and subsecond runs should not be treated as a
robust performance improvement. No significance claim is made.

Structural counts show a real opportunity to remove requeues (2.022 per delivery
in coarse ties, 0.472 in partial-fill/cancel, 0.438 in deterministic baseline),
but fewer queue operations alone did not improve the complete run consistently.
Core plus finalization medians are lower on coarse ties and partial-fill/cancel,
and higher on the remaining units. Write/startup variability also contributes to
the full container result; phase diagnostics do not establish its cause.

### All full-container samples

The five values on each row follow pair indices 0–4, preserving AB/BA matching.
Warmups are shown separately and are excluded from medians and percentages.

| Unit | Baseline timing samples (s) | Candidate timing samples (s) |
|---|---|---|
| t3-coarse-tick-ties | [0.375859966, 0.358854624, 0.508453202, 0.398980278, 0.420350493] | [0.347346038, 0.377128346, 0.408821633, 0.470665291, 0.395569199] |
| t3-eq-deterministic-baseline | [0.322061752, 0.227972892, 0.342512890, 0.277859913, 0.289331119] | [0.328242568, 0.322606905, 0.296113147, 0.300787170, 0.288318224] |
| t3-s012-partial-fill-cancel-race | [0.520623768, 0.515734695, 0.478400795, 0.629572431, 0.572418372] | [0.533638035, 0.588490931, 0.743492685, 0.572865573, 0.577441461] |
| t3-gb-pop-horizon-scale | [1.005776797, 1.096446378, 1.217932199, 1.063438283, 1.769588505] | [1.659388557, 1.160097831, 1.280710363, 1.368085301, 1.144264118] |
| t3-s001-price-time-priority | [0.277255073, 0.304854649, 0.351768772, 0.303107713, 0.306958528] | [0.322257849, 0.315436164, 0.316010948, 0.330238550, 0.280594370] |

| Unit | Baseline excluded warmup (s) | Candidate excluded warmup (s) |
|---|---:|---:|
| t3-coarse-tick-ties | 0.467497094 | 0.383979272 |
| t3-eq-deterministic-baseline | 0.338385196 | 0.443906680 |
| t3-s012-partial-fill-cancel-race | 0.530966202 | 0.533340525 |
| t3-gb-pop-horizon-scale | 1.163676900 | 1.197582338 |
| t3-s001-price-time-priority | 0.333151825 | 0.321365368 |

### Secondary phase diagnostics

The pinned telemetry combines simulation core and trace finalization as
`simulation_and_trace_finalize`; it does not independently expose matcher-only
or finalization-only clocks. Parquet write and hashing are separate. These phase
clocks omit container startup and other work, so their medians need not sum to
the complete-container median. Configuration is retained as an additional phase.

| Unit | Core + finalization B / C (s) | Parquet write B / C (s) | Hash B / C (s) | Configuration B / C (s) |
|---|---:|---:|---:|---:|
| t3-coarse-tick-ties | 0.028936017 / 0.027635658 | 0.118167137 / 0.103355051 | 0.011769049 / 0.012264815 | 0.002623653 / 0.003393497 |
| t3-eq-deterministic-baseline | 0.008839167 / 0.009334308 | 0.065728834 / 0.072543490 | 0.004035183 / 0.004007849 | 0.002497165 / 0.002888861 |
| t3-s012-partial-fill-cancel-race | 0.075806784 / 0.067200040 | 0.160823021 / 0.200793116 | 0.030051047 / 0.036213790 | 0.002332208 / 0.003714109 |
| t3-gb-pop-horizon-scale | 0.308912137 / 0.377211284 | 0.423922409 / 0.502031737 | 0.093922269 / 0.092025483 | 0.002837179 / 0.003230114 |
| t3-s001-price-time-priority | 0.003554846 / 0.004168072 | 0.066738956 / 0.077484026 | 0.002729386 / 0.003272743 | 0.002137479 / 0.002463748 |

All phase samples below use the same five paired runs; B = baseline, C = candidate.

| Unit | Phase | Baseline samples (s) | Candidate samples (s) |
|---|---|---|---|
| t3-coarse-tick-ties | simulation_and_trace_finalize | [0.028936017, 0.027792144, 0.038852848, 0.027224943, 0.030014552] | [0.024167921, 0.025761238, 0.030167575, 0.027635658, 0.028447070] |
| t3-coarse-tick-ties | parquet_write | [0.101218936, 0.097524331, 0.190708154, 0.118167137, 0.131381301] | [0.088258684, 0.103355051, 0.121903401, 0.139462421, 0.102495736] |
| t3-coarse-tick-ties | hashing | [0.011262082, 0.011060407, 0.013104034, 0.011769049, 0.012404361] | [0.010154607, 0.014041532, 0.010906335, 0.014125814, 0.012264815] |
| t3-coarse-tick-ties | configuration | [0.002623653, 0.002622067, 0.004926604, 0.002499233, 0.002740026] | [0.003393497, 0.002671954, 0.003204184, 0.004579669, 0.003691472] |
| t3-eq-deterministic-baseline | simulation_and_trace_finalize | [0.009553195, 0.008682173, 0.011384656, 0.008218037, 0.008839167] | [0.009738185, 0.009334308, 0.009157343, 0.009987465, 0.008845159] |
| t3-eq-deterministic-baseline | parquet_write | [0.078125811, 0.087659766, 0.060472313, 0.056664069, 0.065728834] | [0.074747744, 0.076824411, 0.063390830, 0.072543490, 0.067720938] |
| t3-eq-deterministic-baseline | hashing | [0.005646034, 0.004035183, 0.003877629, 0.003957265, 0.004499811] | [0.004017026, 0.006579889, 0.004007849, 0.003838035, 0.003939963] |
| t3-eq-deterministic-baseline | configuration | [0.002125879, 0.002497165, 0.003540539, 0.002792957, 0.002147852] | [0.002888861, 0.003650142, 0.002366763, 0.002109425, 0.002956718] |
| t3-s012-partial-fill-cancel-race | simulation_and_trace_finalize | [0.060748318, 0.077708338, 0.061914441, 0.079514001, 0.075806784] | [0.062128048, 0.067200040, 0.090714127, 0.062654003, 0.068992851] |
| t3-s012-partial-fill-cancel-race | parquet_write | [0.160823021, 0.162190034, 0.160449618, 0.202658050, 0.157149018] | [0.195429048, 0.224947648, 0.260410670, 0.200793116, 0.193769782] |
| t3-s012-partial-fill-cancel-race | hashing | [0.054796850, 0.030051047, 0.028117683, 0.030489455, 0.026060371] | [0.030208267, 0.037268159, 0.040618785, 0.030459071, 0.036213790] |
| t3-s012-partial-fill-cancel-race | configuration | [0.002308531, 0.002278569, 0.002332208, 0.003271369, 0.002502995] | [0.003839907, 0.002517249, 0.005397930, 0.003714109, 0.003439955] |
| t3-gb-pop-horizon-scale | simulation_and_trace_finalize | [0.301668067, 0.308912137, 0.319702102, 0.297188575, 0.571911895] | [0.467256749, 0.324603877, 0.377211284, 0.385603596, 0.351314600] |
| t3-gb-pop-horizon-scale | parquet_write | [0.366845799, 0.423922409, 0.523484888, 0.402789389, 0.692963984] | [0.735837331, 0.502031737, 0.447775131, 0.531174162, 0.400554680] |
| t3-gb-pop-horizon-scale | hashing | [0.088497313, 0.093922269, 0.110030567, 0.093495065, 0.123878367] | [0.096910143, 0.089560742, 0.083336003, 0.103496731, 0.092025483] |
| t3-gb-pop-horizon-scale | configuration | [0.002827939, 0.002837179, 0.004608302, 0.002342806, 0.003148185] | [0.003230114, 0.002552960, 0.002522217, 0.004033200, 0.003431052] |
| t3-s001-price-time-priority | simulation_and_trace_finalize | [0.003677728, 0.003505399, 0.003554846, 0.003510610, 0.003694328] | [0.004651744, 0.004118403, 0.004168072, 0.004174760, 0.004087936] |
| t3-s001-price-time-priority | parquet_write | [0.062184832, 0.068144335, 0.089801843, 0.066738956, 0.055906027] | [0.079801970, 0.066394146, 0.077484026, 0.086097905, 0.053875032] |
| t3-s001-price-time-priority | hashing | [0.002441382, 0.002729386, 0.003149748, 0.003208400, 0.002476365] | [0.003272743, 0.003485902, 0.003843518, 0.002832695, 0.002592918] |
| t3-s001-price-time-priority | configuration | [0.001994998, 0.002137479, 0.003234306, 0.002294872, 0.002126663] | [0.002796221, 0.002210862, 0.002463748, 0.003200473, 0.002129753] |

[Standard result.json](result.json) is copied verbatim from the runner and contains
all full-run samples, paired comparisons, phase samples, immutable image/source
identities, checker hashes and local timing limitations. Raw
[timing evidence](evidence/phase2b-timing/) and its
[summary](evidence/phase2b-timing/summary.json) contain all retained journals,
checks, records and actual-native/phase telemetry. The
[launch log](evidence/phase2b-timing-launch.log) records the only timing series.
[Report audit](report_audit.json) records sample/order validation and phase 2a
evidence pointers. Large evidence remains ignored in this experiment directory.

Measured implementation/report-preparation commit: `f4f39fcf114219afddefd2cac7da2a97ab479d1e`.
Candidate build source commit: `b05b1a210e7b0f690a802095954648d65cfd0a45`; the later pre-timing
commit adds readiness/report documents with an identical native source manifest.
Baseline immutable image: `sha256:51fcf856e5c5ee4b33a6f43e059bf23035eeba44e2cb2b96692851696179e4c6`.
Candidate immutable image: `sha256:1e7fcc47642b134db12feba0cc04a91475785f7ffdf0d38af48a93ccd196f1e7`.
