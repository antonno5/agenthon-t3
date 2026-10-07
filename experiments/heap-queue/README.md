# Heap event queue experiment

Executive summary: the candidate removes locks from the simulator's event queue,
while keeping the same event ordering. It changes only queue storage and diagnostic
instrumentation. Acceptance requires identical financial and message traces, full
developer gates, and at least 5% less median time for a complete run on a relevant
workload. This is local developer evidence (`rankable=false`), not an official score.

## Scope and implementation

Base commit: `a5dbe466f038389e96f44d6f71f1258e2eddcbb5`.
Branch: `codex/exp-20261005-01-heap-queue`.
Pinned upstream: `f9cbe51342b7dedd9587e4e069040d68a5c6477f`.

The immutable baseline image is `orchestration-baseline:20261005-a5dbe46`.
It already includes the four official upstream patches, typed trace buffers and
optimized delivery ledger. `baselines/Dockerfile` remains the independent baseline;
the heap is applied only by this experiment's overlay Dockerfile.

`kernel_heap_queue.patch` replaces Kernel's queue constructor and supplies an
unbounded single-thread heap. `heappush`/`heappop` receive the original complete
`(deliver_at, (sender_id, recipient_id, message))` element. Sender, destination and
the pinned `Message.__lt__`/`message_id` therefore keep their existing priorities.
There is no insertion counter. The runner, delay/requeue branches, stop condition,
ledger, RNG and adapter output code are unchanged.

The replacement supports the used `put`, `get`, `empty` and `.queue` accesses,
plus `qsize`, `put_nowait` and `get_nowait`. Empty gets raise `queue.Empty`.
`block`/`timeout` arguments are accepted for call compatibility; this class has no
blocking, synchronization, bounded-capacity or task-accounting semantics. It is
safe only for the current single-thread Kernel event loop.

The component profiler selects `HeapEventQueue` exported by the active Kernel,
falling back to `PriorityQueue` for baseline. Diagnostic wrappers are restored on
exit. Unprofiled runs do not execute these wrappers.

All requested units exist, with no substitutions:

- `t3-s001-price-time-priority`
- `t3-s012-partial-fill-cancel-race`
- `t3-momentum-mix-priority`

## Reproduce CPU correctness checks

Run from the root of this worktree, using the checker environment only for tests.
The container runtime remains Python 3.11 and the immutable image dependencies.

```sh
CHECKER='/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python'
mkdir -p out/heap-queue
curl -fL 'https://codeload.github.com/jpmorganchase/abides-jpmc-public/tar.gz/f9cbe51342b7dedd9587e4e069040d68a5c6477f' -o out/heap-queue/upstream.tar.gz
tar -xzf out/heap-queue/upstream.tar.gz -C out/heap-queue
PYTHONPATH="$PWD" QFB2_ABIDES_SOURCE_DIR="$PWD/out/heap-queue/abides-jpmc-public-f9cbe51342b7dedd9587e4e069040d68a5c6477f" "$CHECKER" -m pytest tests/integration/test_heap_queue_kernel.py -m integration -q --basetemp=out/heap-queue/pytest --junitxml=out/heap-queue/tests.xml
PYTHONPATH="$PWD" "$CHECKER" -m pytest tests/test_buffered_trace.py tests/test_delivery_ledger.py -q --junitxml=out/heap-queue/adapter-tests.xml
```

The integration fixture checks the pinned Kernel SHA-256, applies and checks all
four official patches to a fresh full source tree, copies it, and applies the heap
overlay only to the candidate. It imports both actual packages, including the real
Kernel and Message dataclasses. Controlled agents and latency keep the event
schedule inspectable. Tests compare callback order, delivery-ledger tuples,
remaining heap contents and processed-event counts. They cover equal timestamps,
different senders/destinations, reverse insertion, MessageBatch, empty batches,
delayed requeue, empty queue, stop_time boundaries and randomized tuple order.
The executed source hashes are recorded in `out/heap-queue/environment-and-source.json`.
Temporary source copies under `out/heap-queue/pytest/` were removed during the
documented ENOSPC recovery; the pinned-source commands above regenerate them.

Check the three unit manifests with the pinned checker's `qfbench2 manifest verify`,
and run `qfbench2 manifest assert-public-safe` on all 71 units. Git LFS data must be
materialized first: both selected `.parquet` files must begin with `PAR1`.

## Build and validate with the manager's Docker slot

```sh
docker --context colima-agenthon build --platform linux/amd64 --build-arg BASE_IMAGE=orchestration-baseline:20261005-a5dbe46 -f experiments/heap-queue/Dockerfile -t orchestration-heap-queue:20261005-a5dbe46 .
PYTHONPATH="$PWD" "$CHECKER" experiments/heap-queue/validate.py --context colima-agenthon --baseline orchestration-baseline:20261005-a5dbe46 --candidate orchestration-heap-queue:20261005-a5dbe46 --repeats 3 --output out/heap-queue/validation
```

Use a fresh `--output` directory for each validation run. The script executes both
images sequentially: one warmup each, three unprofiled repeats in alternating
AB/BA order, then one separate component profile each. It uses identical mounted
inputs, scenario seeds, `buffered` trace mode, `--network none`, `--cpus 4`,
`--memory 16g`, and `--memory-swap 16g`. Every run checks all developer gates and
exact SHA-256 equality of both Parquet files against the public references.
It also compares these hashes across all baseline/candidate repeats.

Full-run time comes from Docker's container start/finish timestamps. Adapter and
simulation phases are reported separately. The difference between container and
adapter time includes cold process/import startup and other work outside the
adapter. Each repeat starts a fresh process; warmups warm host/cache state, not an
in-process simulator. The candidate introduces no JIT. Component profiles are
diagnostic and excluded from speed medians. Full-run acceptance uses the 5%
threshold; a smaller gain is a speed rejection even when correctness passes.

The unprofiled queue-only benchmark uses actual runtime `Message` and `MessageBatch`
objects, 100,000 complete events, tied times and one delayed requeue. Input creation
and order hashing are excluded from the timed region. Its exact launch template is:

```sh
docker --context colima-agenthon run --rm --platform linux/amd64 --network none --cpus 4 --memory 16g --memory-swap 16g -v "$PWD/experiments/heap-queue/queue_microbenchmark.py:/bench.py:ro" orchestration-heap-queue:20261005-a5dbe46 python /bench.py --repeats 1 --warmups 0
```

Run the same command with the immutable baseline image. The saved component
experiment launches one warmup pair in AB order and three fresh-process pairs in
BA/AB/BA order. `component-records.json` retains all eight exact commands, ordered
event hashes and raw measurements. Synthetic component speed does not decide the
full-simulator verdict.

## Required public regression

The manager supplies an external symlink map of the unchanged published public
references. It contains all 65 singles and a source/SHA mapping; it is not generated
by either simulator image. This run uses that map directly and changes no reference:

```sh
mkdir -p out/heap-queue/tmp
DOCKER_CONTEXT=colima-agenthon TMPDIR="$PWD/out/heap-queue/tmp" PYTHONPATH="$PWD" "$CHECKER" regression_suite/run_regression.py --candidate-image orchestration-heap-queue:20261005-a5dbe46 --scenarios-dir regression_suite/scenarios/ --reference-dir '/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-05/public-regression-reference-map' --output-dir out/heap-queue/regression --workers 1
```

The existing regression CLI has no context option; the manager expressly authorized
`DOCKER_CONTEXT=colima-agenthon` for it. All experiment-owned Docker commands use
explicit `--context colima-agenthon`. Regression complements the three-unit full
developer checks, which include the required message-ledger semantics and exact
comparison of both files.

The first 65-case attempt hit host ENOSPC after 28 PASS results. Its log and those
28 cases' PASS evidence, trace digests, events and stylized reports are retained in
`regression-checkpoint.json` and `regression.failed-enospc.log`. Repeat only the
other 37 unchanged config symlinks with `--scenarios-dir
out/heap-queue/regression-retry-inputs` and `--output-dir
out/heap-queue/regression-retry`; keep every other flag above unchanged.
The final combined summary verifies that the disjoint input sets cover exactly
the original 65 scenario IDs. `storage-recovery.json` records permitted scratch
cleanup; all selected benchmark traces and raw measurements remain saved.

Raw container output, individual gates, hashes, timings and profiles remain in
ignored `out/heap-queue/validation/`. `result.json` and the experiment report retain
the decision and evidence locations. Mac ARM64 execution of linux/amd64 through
Rosetta cannot establish performance on official Linux CPU hardware.

## Limitations

The three full-gate workloads and 65-single regression do not establish all-71-unit
admissibility. The known baseline batch root
`profile.json` retention defect is outside this experiment and is not changed or
hidden. No scorer, tolerance, card, scenario, reference or output allowlist is edited.
