# Heap queue experiment result

Executive summary: removing locks makes the event queue faster while preserving
the same trades and agent communications. All required correctness checks pass.
The complete run improves by 8.10% on momentum but slows down on the other two
workloads. This is a preliminary, workload-specific local result, not an official
score or a global adoption recommendation.

## Identity and scope

- Base: `a5dbe466f038389e96f44d6f71f1258e2eddcbb5`; upstream: `f9cbe51342b7dedd9587e4e069040d68a5c6477f`.
- Branch: `codex/exp-20261005-01-heap-queue`; tested code: `e90768b2c6dd2d2f6725a40e0652158fcfc47c69`.
  The reporting commit is the final branch HEAD.
- Worktree: `/Users/iopogiba/.codex/worktrees/38bb/Агентон`.
- Measured baseline image ID: `sha256:0bd010981f4f4a8aa8bdd074e5342a56bfe91daf25e5c5d7e04c075d082c99e2`.
- Measured candidate image ID: `sha256:e25e89f200d76a864e99cc2ff2cf8288b2967f90a8759b852e7330cbff024769`.

The independent immutable baseline already includes all four official patches,
typed trace buffers and the optimized ledger. Only the heap overlay and diagnostic
queue selection change. No scenarios, cards, scorer, tolerances, references or
output allowlists are changed. All three requested unit names exist.

## Complete-run timing

One warmup per image, then three unprofiled fresh-process paired repeats in
BA/AB/BA order; separate diagnostic profiles follow. Inputs, seeds and buffered
trace mode are identical. Caps: 4 CPU, 16 GiB, no network, sequential execution.
Docker start/finish timestamps measure full container time; host gate checking is
outside it. Runtime versions and source hashes are audited separately.

| Unit | Baseline median, s | Heap median, s | Full time reduction | Local verdict |
|---|---:|---:|---:|---|
| t3-s001-price-time-priority | 1.913813 | 2.037012 | -6.44% | reject_speed |
| t3-s012-partial-fill-cancel-race | 15.815387 | 17.045614 | -7.78% | reject_speed |
| t3-momentum-mix-priority | 7.111925 | 6.535962 | +8.10% | accept_local (preliminary) |

| Unit | Baseline raw repeats, s | Heap raw repeats, s |
|---|---|---|
| t3-s001-price-time-priority | 1.902976, 1.913813, 2.152648 | 2.109715, 1.925156, 2.037012 |
| t3-s012-partial-fill-cancel-race | 15.815387, 13.957501, 17.484697 | 16.927932, 17.045614, 19.102222 |
| t3-momentum-mix-priority | 7.529271, 7.111925, 6.576393 | 5.881567, 6.535962, 6.775223 |

Momentum ranges overlap (6.576–7.529 s vs 5.882–6.775 s). Its final paired candidate
is slower. The +8.10% median passes the stated practical threshold only for this
workload and only as preliminary local evidence. No extra repeats were requested.

## Component and startup separation

The queue-only median is 0.413454842 s baseline versus
0.239332983 s candidate: **1.728×** speedup.
This unprofiled benchmark enqueues/drains 100,000 real Message/MessageBatch events
and performs one delayed requeue. Input construction and hashing are excluded.
One warmup pair and three BA/AB/BA pairs run in pinned container Python. All eight
ordered-output hashes match. This synthetic result does not determine full-run speed.

| Unit | Baseline simulation, s | Heap simulation, s | Baseline cold/other, s | Heap cold/other, s |
|---|---:|---:|---:|---:|
| t3-s001-price-time-priority | 0.131536 | 0.084367 | 1.710510 | 1.705949 |
| t3-s012-partial-fill-cancel-race | 13.311366 | 13.990988 | 1.724409 | 1.882914 |
| t3-momentum-mix-priority | 5.073559 | 4.754713 | 1.579062 | 1.482837 |

Cold/other is container minus adapter time, including interpreter/import startup.
Each repeat launches a new process. Warmups affect host/cache state; there is no
new JIT or claim of in-process warmed execution. Phase medians are calculated
independently. Detailed queue timers are diagnostic, excluded from speed medians.
Both profiles have identical queue call counts: 2,108 / 787,106 / 578,984 for
S001 / S012 / momentum, and the profiler measures the candidate heap class.

## Correctness and public regression

59 targeted tests pass with no skips. They execute real pinned Kernel and Message
classes after all four baseline patches, then the independent heap overlay. Ties,
sender/destination order, reverse insertion, MessageBatch, delayed requeue, empty
queue and stop-time boundary behavior match. Ruff passes. Runtime source SHA-256
matches the CPU-tested source; simulator dependencies match across both images.

All 30 selected-unit runs (warmups, unprofiled repeats and diagnostics) pass every
developer gate g0–g3, including message-ledger semantics. Both files are exact in
all 60 reference comparisons. Three manifests and all 71 public firewall checks pass.

Public regression: **65/65 PASS**, via 28 recorded first-attempt PASS plus 37 retry
PASS after host storage recovery. The ID sets are disjoint and cover exactly all
65 original configs. The unmodified public runner, one worker and external published
reference map are used; no simulator-generated references or tolerance overrides.
Retry wall clock: 351.067 s. The first attempt's
timer could not persist due to ENOSPC; first-to-last log span is 410.439 s, not a
precise full-invocation duration. Regression time is separate from speed medians.

The first attempt retained 28 PASS records, then environment ENOSPC failures.
Its full log and checkpoint provenance remain. Own scratch cleanup freed
47,716,785 bytes; successful duplicate regression
traces were removed only after exact public SHA and PASS evidence were saved.
Every selected benchmark trace and raw measurement remains. The manager reclaimed
space with independent APFS clones of identical public data, verifying SHA; input
content and Git state stayed unchanged. Free space was checked before retry.

## Reproduce and evidence

Run from the worktree root. Full commands and source preparation are in README.md;
result.json stores exact benchmark/component and both regression invocation commands.

```sh
docker --context colima-agenthon build --platform linux/amd64 --build-arg BASE_IMAGE=orchestration-baseline:20261005-a5dbe46 -f experiments/heap-queue/Dockerfile -t orchestration-heap-queue:20261005-a5dbe46 .
PYTHONPATH="$PWD" "/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python" experiments/heap-queue/validate.py --context colima-agenthon --baseline orchestration-baseline:20261005-a5dbe46 --candidate orchestration-heap-queue:20261005-a5dbe46 --repeats 3 --output out/heap-queue/validation
```

Raw data remain in ignored `out/heap-queue/`. Key evidence: `final-tests.xml`,
`input-integrity.json`, `runtime-attestation.json`, `validation/records.json`,
`component-summary.json`, `regression-checkpoint.json`,
`regression-retry/report.json` and `regression-combined-summary.json`.

No required validation remains for this experiment. Full gates on all 71 units,
the six batch cases and official Linux timing are outside this result’s scope.
The baseline batch root-profile retention defect is recorded in README and unchanged.

Docker slot is released; no experiment containers remain running.
