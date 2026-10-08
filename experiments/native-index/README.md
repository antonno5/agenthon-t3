# Native simulation with the adopted price index

Executive summary: this experiment ports the complete supported market-simulation
loop to C++ while retaining the price-index algorithms already adopted in our
Python engine. It also transfers compact events, pooled messages, direct ledger
columns, reduced sorting, native Parquet output and cheaper process startup.
The candidate was validated as an experiment and adopted into the production
Docker recipe on 2026-10-08. See [integration.json](integration.json) for the
production build and targeted integration checks; the results below retain the
original experimental image and measurement identities.

## Production integration (2026-10-08)

The self-contained `baselines/` Docker build now compiles the extension in a
separate builder stage and installs it alongside the original optimized Python
matching package. Its native sources and build script equal the tested experiment;
all installed Python sources and pinned numeric-library versions equal the tested
image. The final runtime selects native execution automatically and keeps the
Python path for unsupported mappings and explicit legacy/verification/profiling
modes. The previously ignored experimental build script is now tracked so its
historical Docker recipe is reproducible from a checkout.

The production image passed seven targeted integration checks: STP oldest, deep
book, cancel churn, heterogeneous batch, price-time priority, Python collector
verification, and native execution with a read-only root filesystem as UID 65534.
Native journals are byte-identical to the tested experimental image; developer
gates passed. The production builder also passed 80,000 differential book
mutations, and 28 host installation/CLI/documentation checks passed. Compilers stay
in the builder. The full public suite and paired timing experiment were already
completed on the same source implementation and were not repeated for integration.

[Integration record](integration.json) retains the production image identity,
source hashes, checks and evidence hashes. Logs and retained journals are local
under `out/native-integration-20261008/`. The earlier experiment's `adopted: false`
field is preserved as a historical snapshot; the integration record records
`adopted: true`. No new timing claim is made for the production smoke runs.

## Source and compatibility

Sources originate from `antonno5/agenthon-t3` at
`f563be0c2278aabae3036318e7a1869f0ba63d47`; original hashes are retained in
[provenance.json](provenance.json). ABIDES and NumPy redistribution notices are
retained in the source and image. The four adapter agents are byte-identical to
our baseline. All four scenario mapping helpers were checked for AST equality.

The image inherits `python-book-price-offset:20261007`, immutable baseline ID
`sha256:4a54f2c8a59d8f7bd7d23373bf96e54025d01a7560289fdcf1a0f3d0a56fdfbe`.
Its optimized Python matching package is retained as fallback, including the
compatible facade, centralized mutations, binary price search and price-key
prefix offset. At the time of the experiment, uncommitted production Dockerfile/skill edits
were outside its scope. The later integration preserves the writable `/tmp`
working directory and leaves the unrelated skill edit untouched.

The C++ engine implements the adapter's single-symbol visible limit-order flow,
cancellations, partial fills, self-trade prevention, four scheduled agent types,
latency models and sparse oracle. It is not a replacement for every arbitrary
Python ABIDES extension or hidden/PTC public method. Unsupported mapped scenarios
use the existing Python engine; timed experimental runs assert that every market
actually used the native engine. `--engine python` forces the original engine.
`--trace-mode verify` exercises the original Python collector against its legacy
extraction; native outputs are compared separately with both canonical journals.

## Preserved and transferred ideas

The donor's linear price lookup is replaced in [book.hpp](native/book.hpp) by:

- ascending numeric keys (negative bid prices), with `std::lower_bound` lookup;
- an O(1) best-price check before binary search and a cheap worse-than-tail append;
- incremental maintenance of keys, rather than rebuilding them during lookup;
- a reusable inactive prefix with compaction when the prefix is at least 64 entries
  and at least as large as the live book; empty books reset immediately;
- the same prefix for level objects, so best-level removal shifts neither levels
  nor keys; new best levels can reuse retired slots;
- centralized cancellation, fill-volume updates and empty-level removal;
- FIFO `deque` queues and an incrementally maintained aggregate volume per level.

Middle insertion/removal still moves vector elements. Cancellation finds the
level in O(log L) (O(1) at the best price), then scans that level's queue for the
order ID. It does not claim O(1) arbitrary cancellation. Normal native state is
private and owned by these operations, so volume totals need no global mutation
hooks or compatibility cache invalidation.

Other transferred ideas are native scalar snapshots, logging only retained event
types, an unlocked event heap preserving the original tie order, recycled message
slots with delivery reference counts, a ledger appended in delivery order, one
stable order-trace sort plus linear quote merge, native column buffers passed to
Arrow, parallel writing of the two output files, lazy imports, precompiled Python
bytecode and CLI exit after output files have been closed. RNG, rounding and
NumPy-log dispatch retain the donor's exact numeric compatibility implementation.

## Verification and measurement

The native price-side state-machine test compares 80,000 generated mutations with
a simple ordered reference, checks FIFO and partial fills, verifies aggregate
volumes and binary positions, and tests prefix reuse, reset and compaction.
The unchanged Python facade/index tests are also run inside the candidate image.

The experiment imports the existing bounded differential runner and shared
**developer** verifier; it does not copy scoring rules. Every output is sanitized
before reading. Both `trace.parquet` and `message_trace.parquet` are compared for
schema metadata and exact ordered values. Image IDs, sources, inputs, individual
samples, failures and Docker state timestamps are retained locally under
`out/native-index-20261007/` (the experiment was continued on 2026-10-08).

Seven focused workloads use one excluded warmup and five measured runs of each
image. The baseline/candidate order alternates between pairs. Containers are
strictly sequential, linux/amd64, four CPUs, 16 GiB, network disabled. The primary
clock is Docker `FinishedAt - StartedAt`, including process startup and exit.
Complete adapter time is also recorded. Native core time includes trace
extraction, whereas the Python simulation phase excludes it, so those internal
clocks are not presented as an identical timing boundary. Local Mac/emulated
measurements are non-rankable and are not official Linux/B200 results.

```bash
docker --context colima-agenthon build --platform linux/amd64 \
  -f experiments/native-index/Dockerfile -t native-index:20261008 .
.venv/bin/python experiments/native-index/run_experiment.py \
  --phase timing --out out/native-index-20261007/timing
```

Use a fresh output directory for every run. Validation results and performance
samples are added below only after the corresponding checks complete.


## Results

Runtime tests: **159 passed**; 80,000 native price-side mutations, 100 mixed RNG scripts and 100,000 NumPy-log values passed.

All **65 single public units and 6 batch units** passed the shared developer verifier and exact ordered trace/message checks. Every measured native run and each batch sub used the C++ engine.

Paired median full-container times, seconds (five measured repeats per image):

| Workload | Python | Native + retained index | Speedup |
|---|---:|---:|---:|
| t3-mp02-stp-oldest-baseline | 3.764 | 0.324 | 11.62x |
| t3-mr-deep-book-state-size | 15.717 | 0.540 | 29.11x |
| t3-mp05-cancel-churn-newest | 10.062 | 0.489 | 20.59x |
| t3-s001-price-time-priority | 1.237 | 0.289 | 4.28x |
| t3-s012-partial-fill-cancel-race | 8.736 | 0.435 | 20.10x |
| t3-cancelmodify-lifecycle | 7.551 | 0.387 | 19.50x |
| t3-mp07-heavy-flow-oldest | 3.900 | 0.320 | 12.19x |

Geometric mean of the seven container-time ratios: **14.61x**. This describes these focused workloads, not an official or universal speedup.

See [result.json](result.json) for every sample, complete adapter times, internal clock limits, source audit and validation evidence. Production engine files and production build wiring remain unchanged.
