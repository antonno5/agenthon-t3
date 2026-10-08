Executive summary: the shared arena and sparse radix book preserved exact matching
and journal output on every selected market. In one fixed local timing series,
complete-container median time fell by 19.07% for cancellation churn and 7.21% for
multilevel crossing, and rose by 3.86% for deep-book state and 9.07% for the small
FIFO scenario. The Linux structure probe also used fewer allocation bytes. These
are emulated Linux/amd64 results on a Mac ARM64 host, `rankable: false`; production
adoption is false.

## Complete-container results

The primary clock is Docker `FinishedAt - StartedAt`, including startup,
simulation, finalization, output writes and hashing. Each unit used fresh baseline
and candidate containers, one excluded warmup per side and exactly five pairs in
AB/BA/AB/BA/AB order. All 40 timing samples and eight warmups are retained. There
were no extra repeats, discarded outliers or code changes after timing.

Reduction is `100*(1-median(candidate)/median(baseline))`. Positive means faster;
negative means slower. Medians are in seconds.

Clock caveat: candidate timing indices 2 and 3 for
`t3-s001-price-time-priority` show an apparent 18.671528 ms overlap in Docker
wall-clock intervals. The harness launched sequentially, checked idle containers
before each run and waited for exit. The cause is undetermined; VM clock
adjustment is only an unverified inference. Timestamp non-overlap is not
established. Original Docker durations and percentages remain unchanged, with no
reruns or code changes. Exact timestamps are in [clock-audit.json](clock-audit.json).

| Timing unit | Baseline median | Candidate median | Full-run reduction | Candidate faster pairs |
| --- | ---: | ---: | ---: | ---: |
| `t3-mr-deep-book-state-size` | 0.683108 | 0.709476 | -3.86% | 1/5 |
| `t3-mp05-cancel-churn-newest` | 0.655236 | 0.530268 | +19.07% | 5/5 |
| `t3-multilevel-crossing` | 0.436244 | 0.404774 | +7.21% | 4/5 |
| `t3-s001-price-time-priority` | 0.295502 | 0.322313 | -9.07% | 2/5 |

Cancellation churn improved in all five pairs and multilevel crossing in four.
Deep-book improved in one pair and the small FIFO unit in two. Results vary by
workload; these medians describe one fixed local series on emulated hardware.

[Standard result.json](result.json) is an exact copy of the campaign runner's
result. [final-report-audit.json](final-report-audit.json) verifies image/source
identities, every Docker-state duration, pair order, medians, percentages and
journal/developer-gate acceptance. Raw journals, profiles, timestamps and every
run record stay under [evidence/phase2b-timing/](evidence/phase2b-timing/).

## All timed samples

Each row lists all five seconds in pair-index order, without sorting by duration.
Actual within-pair launch order alternates AB/BA/AB/BA/AB.

| Unit | Side | Pair 0 | Pair 1 | Pair 2 | Pair 3 | Pair 4 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `t3-mr-deep-book-state-size` | baseline | 0.732203086 | 0.683108309 | 0.575812046 | 0.510778685 | 0.743561007 |
| `t3-mr-deep-book-state-size` | candidate | 0.927847442 | 0.709476102 | 0.654981629 | 0.842636734 | 0.578702021 |
| `t3-mp05-cancel-churn-newest` | baseline | 0.655235679 | 0.625465044 | 0.648004883 | 0.805534837 | 0.709551056 |
| `t3-mp05-cancel-churn-newest` | candidate | 0.510774298 | 0.520682988 | 0.545350916 | 0.530267787 | 0.631322002 |
| `t3-multilevel-crossing` | baseline | 0.579552163 | 0.379219805 | 0.424734615 | 0.436244387 | 0.529737344 |
| `t3-multilevel-crossing` | candidate | 0.404773906 | 0.446810616 | 0.374732106 | 0.381603227 | 0.481763248 |
| `t3-s001-price-time-priority` | baseline | 0.346320063 | 0.309809200 | 0.291408070 | 0.285641499 | 0.295502302 |
| `t3-s001-price-time-priority` | candidate | 0.322313178 | 0.347773317 | 0.308286171 | 0.282269522 | 0.439929104 |

Excluded warmups do not contribute to the medians.

| Unit | Baseline warmup seconds | Candidate warmup seconds |
| --- | ---: | ---: |
| `t3-mr-deep-book-state-size` | 0.887479643 | 1.023227734 |
| `t3-mp05-cancel-churn-newest` | 0.515389576 | 0.665227298 |
| `t3-multilevel-crossing` | 0.416604192 | 0.392477281 |
| `t3-s001-price-time-priority` | 0.333153896 | 0.355074222 |

## Secondary phase diagnostics

These are per-phase medians from the same five samples, in seconds. Core includes
trace finalization; a matcher-only clock is unavailable. Parquet writes and
hashing are separate. Independent phase medians need not add to the complete
container median. Full phase sample arrays are retained in `result.json`.

| Unit | Side | Core + trace finalization | Parquet write | Hashing | Configuration |
| --- | --- | ---: | ---: | ---: | ---: |
| `t3-mr-deep-book-state-size` | baseline | 0.126461033 | 0.218026259 | 0.038000478 | 0.003095093 |
| `t3-mr-deep-book-state-size` | candidate | 0.121881301 | 0.246893502 | 0.039270970 | 0.002639321 |
| `t3-mp05-cancel-churn-newest` | baseline | 0.099873509 | 0.242258084 | 0.050025389 | 0.003626162 |
| `t3-mp05-cancel-churn-newest` | candidate | 0.071228976 | 0.171479935 | 0.042434570 | 0.002473307 |
| `t3-multilevel-crossing` | baseline | 0.027024240 | 0.111078490 | 0.011553435 | 0.004223864 |
| `t3-multilevel-crossing` | candidate | 0.024807419 | 0.118296966 | 0.011783138 | 0.002516179 |
| `t3-s001-price-time-priority` | baseline | 0.003581144 | 0.075444200 | 0.002744162 | 0.002343639 |
| `t3-s001-price-time-priority` | candidate | 0.003936801 | 0.074536103 | 0.002793285 | 0.002339746 |

Cancellation-churn core/finalization falls from 0.099874 to 0.071229 seconds.
Deep-book core/finalization falls slightly, from 0.126461 to 0.121881, while its
complete-container median rises. Writer code and journal bytes are unchanged;
these phase observations do not isolate the book's contribution to each full-run
difference.

## Structure memory and operation counts

The pinned Linux allocation probe constructs 14,096 resting orders at 4,097
levels. It intercepts requested C++ allocations around structure construction,
including deque blocks and vector capacity, without snapshots or journals. It
excludes allocator metadata, stack objects, RSS and journal buffers.

| Requested allocation bytes, pinned Linux | Baseline | Candidate |
| --- | ---: | ---: |
| Live at the end of construction | 3,155,256 | 1,394,448 |
| Peak during construction | 3,336,568 | 1,431,296 |

[linux-book-checks.json](linux-book-checks.json) also records the operation probe.
Cancelling the newest order behind 10,000 FIFO entries takes one direct lookup
and one intrusive unlink, with zero radix visits. The baseline loop inspects
10,000 entries. Inserting/removing price 4095 among 4,096 even prices takes 24
radix visits and one cancellation lookup, with zero price shifts. The reference
suffix contains 2,048 entries: 4,096 logical suffix moves across insertion/removal,
separately for each of its two vectors, excluding reallocation moves. Production
counters compile out unless `T3_BOOK_DIAGNOSTICS` is enabled.

The 80,000-mutation diagnostic reaches 1,074 live orders and a 258,088-byte
arena/node/index payload-capacity high-water estimate. This excludes allocator
overhead and deque maps and differs from requested allocations. The host
ASan/UBSan allocation probe reports live baseline/candidate footprints of
17,521,896/1,358,112 bytes and peaks of 17,521,896/1,415,440 bytes. Host deque
allocation policy differs from the pinned Linux image; the host measurements do
not establish Linux process memory. Untimed simulation process-memory reports
are retained in [phase2a-correctness.json](phase2a-correctness.json), separately
from structure allocations and complete-container timing.

## Storage implementation

The shared exchange `BookArena` holds recycled active-order slots containing a
value copy of `Order`, previous/next FIFO links and a level handle. The trader's
sent snapshots remain independent of exchange partial fills. Globally monotone
native order IDs select direct 1024-entry handle blocks shared by both sides.
Full blocks exist only while they contain live orders; the directory retains one
pointer per 1024 historical IDs. Slot/directory growth is amortized; lookup and
FIFO unlink are constant time.

Each side uses a compressed binary radix tree of signed 64-bit prices with
sign-bit biased unsigned keys. An internal node selects the highest differing
bit; branch bits strictly decrease, bounding a walk at 64 steps. Empty-level
removal splices its sibling into its parent's position and recycles handles.
Insertion/deletion do not shift other levels, and storage does not depend on the
maximum price. A cached best leaf gives constant-time best access; retiring it
uses a bounded walk to find its replacement. FIFO append, head fills and arbitrary
cancellation use intrusive handles. Partial fills retain FIFO position;
cancellation validates ID, side and price against the exchange value.

This sparse compressed radix index stores at most two tree nodes per live price
level. It removes both queue scans and price-vector shifts. Capacity growth and
diagnostic full-state walks remain separate operations. Only native book storage,
exchange accessors and book tests changed. Trader registries, scheduling, RNG,
Python adapters, finalization, Arrow writing, cards, traces and scorer code stay
at the common base.

## Correctness and fixed selection

[policy.json](policy.json) fixed four timing units before Docker measurements:
deep-book state for deep resting state and level changes; cancel churn for direct
lookup/cancel-newest STP; multilevel crossing for best replacement and partial
fills; and the small price-time unit for FIFO order and fixed overhead.
Correctness-only controls are `t3-mp02-stp-oldest-baseline` (cancel-oldest),
`t3-partialfill-atomicity` (residual state), `t3-s012-partial-fill-cancel-race`
(delayed sent snapshots), and `t3-gbatch-hetero-mix` (five independent markets).

All eight units pass pinned correctness across 16 fresh containers and 12 markets
per side: both journals match by bytes, schema and ordered values; all unchanged
shared developer gates pass; every market proves actual native execution. The
48 timing/warmup containers, 24 baseline/candidate comparisons and 40 per-side
repeat-stability comparisons also pass.
[phase2a-correctness.json](phase2a-correctness.json) records untimed gates;
[corpus-checks.json](corpus-checks.json) records focused manifests and firewall
checks; timing evidence retains the checks for every launch.

[run_host.py](run_host.py) extracts the exact base book with `git show`; its only
comparison-header edit renames the namespace. ASan/UBSan checks 80,000 seeded
mutations with FIFO/value/volume, tree, direct-index and free-slot invariants,
wrong-price/side/stale cancellation, slot reuse, partial fills, metadata, sent
value independence, exhaustion and best/middle/worst removal/reinsertion. Prices
include zero, gaps near 2^62 and values adjacent to INT64_MAX.
[run_engine_host.py](run_engine_host.py) compares all 19 native event/message
columns on the 12 markets under ASan/UBSan: 1,036,275 event rows and 897,242 ledger
rows match. Commands, source hashes and zero sanitizer diagnostics are committed
in [host-results.json](host-results.json) and
[engine-host-results.json](engine-host-results.json).

## Identities and retained evidence

Base source is `a7fb6c36d88395e49d40bc3b71e6dc79b2099bc9`; baseline image is
`sha256:51fcf856e5c5ee4b33a6f43e059bf23035eeba44e2cb2b96692851696179e4c6`.
Candidate image is `sha256:fb1eb09f18518152ce8140a35031da789c2363c3b29d24afa03cb5e4a556b070`,
built from `8162577af0251257b96834c804925bd6306d2669` and measured at clean HEAD
`2d995b4177bbc4ee9c4968e29fdda7335bd49e33`. Native source hashes match across
build, controls and timing. Runtime remains Python 3.11.17 / NumPy 1.26.4 /
pandas 1.5.3 / Arrow 15.0.2 / SciPy 1.17.1, identical libm dispatch, and
`-fno-fast-math -ffp-contract=off`.

[Dockerfile](Dockerfile), [recipe.json](recipe.json) and
[run_phase2a.py](run_phase2a.py) describe the native overlay and compiled checks.
[phase2a-image-audit.json](phase2a-image-audit.json) binds source/image/runtime
identities. Every build, probe, check and timing run used its entire subprocess
inside the campaign `docker_slot.py` serial slot, explicit `colima-agenthon`,
linux/amd64, 4 CPUs, 16 GiB memory and the same memory+swap limit, and network none
for runtime containers. VM lifecycle and global Docker context were unchanged.

The failed first build stays under
[evidence/phase2a-attempt-01/](evidence/phase2a-attempt-01/). GCC rejected a test-only
memory-probe formatting warning under `-Werror`; formatting and host sanitizer
verification were corrected before the successful committed build, with strict
diagnostics and meaningful tests retained. Successful build, Linux checks and
controls stay under [evidence/phase2a-attempt-02/](evidence/phase2a-attempt-02/),
with all timing evidence under [evidence/phase2b-timing/](evidence/phase2b-timing/).
Large raw evidence is ignored locally and linked/hashed by committed reports.
No all-public/regression65 suite, additional timing series, merge, push or
production adoption occurred.
