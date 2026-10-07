# Independent markets in a bounded process pool

Executive summary: each independent market now has its own working folder, random
state and output files. This prevents ABIDES's internal summary-log folders from
colliding when markets run together. The default is serial execution. Parallelism
is opt-in; the verified mode is `--workers 2`. The final two-worker image passes all six public batch
units and the mandatory single-market unit with exact matching of both trace
files. The 65-scenario public regression also passes (65/65, no errors).
The pool is slower on five of six measured batches. Homog-8 shows a preliminary
15.7% median reduction, but three noisy pairs do not establish a stable gain.
This is local developer evidence, `rankable=false`, not an official Final score.

Base: `a5dbe466f038389e96f44d6f71f1258e2eddcbb5`.
Branch: `codex/exp-20261005-03-process-batch`.
Final runtime source commit: `066bf374d653cf097a3b73be20dd9efc61d9446e`.
The immutable baseline already contains its four upstream patches, typed trace
buffers and message-ledger optimization. No upstream source, dependency, scorer,
card, tolerance, reference or public scenario was changed.

## Implementation

`simulate-batch --workers N` uses a bounded `ProcessPoolExecutor` with explicit
`spawn`. It caps N by four CPUs, affinity, hierarchical CPU quota, available
host/cgroup RAM, a 3072 MiB planning allowance per worker, 512 MiB parent reserve,
and market count. The allowance is not a measured memory limit. Missing memory
evidence and nested invocations fall back to serial. At most the selected worker count of tasks
is outstanding. The image and all compared runs limit BLAS/OpenMP threads to one.
A direct caller must set those limits before importing NumPy.

Every task invokes the unchanged `simulate`, which resets order/message counters
and rebuilds seeded RNGs. Input/output paths resolve before changing directory.
Each market uses a private scratch directory outside solver output; names use
PID, monotonic time and a local counter, with no RNG. `finally` restores cwd,
including serial calls with relative paths, and the parent removes scratch after
joining workers. Only the existing allowed sub outputs and `batch_events.json`
remain. Sorted metadata and aggregate schema/count/hash/rate contracts are
preserved. An exception stops scheduling, terminates and joins workers, removes
stale aggregate success and propagates a failing CLI exit. There is no retry or
participant re-invocation inside the simulator.

Abnormal-exit diagnostics record child exit codes before/after cleanup and cgroup
counters to stderr. On controlled failure, post-cleanup SIGTERM values describe
our cleanup, not a native crash. Optional batch diagnostics go outside output.
Their `worker_component_elapsed_sums` overlap across workers; they are never
subtracted from batch wall time or called exclusive time. Pool readiness includes
interpreter/import startup and may overlap early tasks. Unprofiled container wall
time includes pool setup/shutdown, private workspace/log cleanup and Parquet/
metadata writes. Container total, pool readiness and per-sub simulation phases
are recorded separately; no exclusive parent cold-start duration is inferred.

Aggregate memory is the sum of per-process high-water RSS once per worker plus
parent RSS, an estimate that can double-count shared pages. It is not a measured
concurrent peak. Diagnostic profiles separately read `memory.peak` after the CLI
via a host-supplied wrapper, including that wrapper and page cache. That is
container cgroup usage, not process RSS; unprofiled runs do not claim an exact
sampled cgroup peak.

## Provenance and failures

| Image | Immutable ID | Runtime source |
|---|---|---|
| Initial | `sha256:fd178ca955bacc096206a378597f825a0b305872b601aef7b83ee3913b7a9cdd` | `35ca21e` |
| Diagnostics | `sha256:2c1bf3eca58b5326079f880a72e23ab73f507ebb0534ebbc91985140eb2f09bd` | `401618c` |
| Final | `sha256:9db279bc721ac531b5a51f8dd95f09180011ce9fbc9d5d6d64239705fb893389` | `066bf37` |

The initial many-6 workers4 launch failed with `BrokenProcessPool`. Its original
stderr, unchanged inputs, adapter snapshot and image inspection remain under
`out/process-batch/first-failure/`. Cleanup removed that container before extra
diagnostics, so its child signal and `State.OOMKilled` are unavailable. A separate
same-input diagnostic reproduction succeeded: cgroup peak 618819584 bytes and
`oom_kill=0`. Those are successful-reproduction values, not evidence about the
first failure. Historical VM I/O/EXT4 errors lack time correlation and do not
establish causation. The initial failure remains unexplained; it is not attributed
to Rosetta, OOM, disk errors or the separate log race. Four-worker safety is not
claimed.

Repeated-seed/order stress independently reproduced `FileExistsError` in
`Kernel.write_summary_log`: processes raced creating shared
`./log/<unix-second>`. Per-market cwd/scratch fixes that concrete defect without
changing simulation logic or RNG. All measurements and partial campaigns before
this fix (`out/process-batch/manager/`, `out/process-batch/final/`) are invalid for
the performance decision. Their logs are retained, not silently replaced.

The original `orchestration-baseline:20261005-a5dbe46` also writes forbidden root
`profile.json`; its `path_not_allowed` retention failure is separately reproduced
for every batch. Timings use the explicitly labelled serial contract-only control
`orchestration-control:20261005-a5dbe46`: it removes that file after successful
main, retaining identical algorithms/RNG/IDs/dependencies. Neither the allowlist
nor sanitizer was weakened. The candidate keeps sub profiles only.

## Final validation

The final campaign is `out/process-batch/validated/`, separate from old images.
Correctness runs every sub in isolated control, then full developer gates,
unchanged no-follow retention and both-file byte comparisons against isolated
control and each published reference. Candidate workers1/2 each run twice; every
aggregate covers the expected subs exactly once with matching footer counts,
hashes and rate formula. All six units exist unchanged: dense-3, hetero-mix,
homog-4, homog-8, many-6 and varsize. No unit-name substitution was required.
`t3-s001-price-time-priority` passes its full developer gates too.

Real repeated-seed/order stress uses eight copies of two existing homog-4 configs,
reverses creation/scheduled content order, and checks both files in workers1/2.
No public unit/config/reference/card is modified. Timing uses one warm-up per
control/candidate1/candidate2 mode followed by three alternating adjacent AB/BA
control/pool pairs, with candidate1 observations outside those pairs. All outputs
are rechecked. Method instrumentation is disabled; the small outside-output
batch diagnostic cost is included in both candidate modes. The final default is
serial, so there is no duplicated default-auto campaign or auto speedup claim.

The startup phase is only four unchanged copies of short public s001, serial vs
selected two-worker pool: one warm-up each and three AB/BA pairs, eight launches.
The n=1 serial fallback is covered by targeted tests/correctness. There is no
120-run matrix or unsupported universal crossover threshold. Profiles are a
separate phase. Regression65 uses workers1 and the manager's read-only map of
published reference traces. The single adapter and regression runner are
unchanged; their CLI compatibility and 65-record map JSON/symlink/SHA checks
passed before the actual regression. The first run was interrupted after 29
completed scenarios. Its log and retained outputs are preserved. A local resume
helper rechecks those 29 through the unchanged runner functions without a
participant launch, preserving their original hashes; only the remaining 36
scenarios launch containers. Each result is checkpointed. The combined final
report passes all 65 scenarios with zero failures and zero errors. Resume
evidence is
`out/process-batch/validated/regression65-resume/` and its separate log is
`out/process-batch/validated-regression65-resume.log`. Regression is additional
evidence; selected units still require full gates and both message/fill traces.

Local tests: 32 targeted batch/evidence/timing-plan tests passed, plus existing
ledger/C3 checks and CLI/routing checks recorded in `result.json`. Manifest verify
and public firewall passed for all 71 units. The checker is Python 3.13 with
`PYTHONPATH` set to this worktree; ABIDES runs only in pinned Docker Python 3.11.
The manager also independently audited 438 produced traces against published
manifest SHA values; its audit is in
`/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-05/batch_manager_validation.json`.

## Measured result

Container wall time includes startup, simulation, output writes and shutdown.
Each cell shows median [min, max] seconds and sample CV over three unprofiled
repeats. Warm-ups are separate in the raw records. Positive reduction means faster.

| Unit (markets) | Serial control | Candidate workers1 | Candidate workers2 | Reduction vs control |
|---|---|---|---|---|
| dense-3 (3) | 3.667 [3.305, 4.178]; 11.8% | 3.416 [3.139, 4.724]; 22.5% | 4.670 [4.418, 4.884]; 5.0% | -27.3% |
| hetero-mix (5) | 6.958 [5.833, 9.505]; 25.3% | 7.657 [6.846, 8.816]; 12.7% | 7.460 [7.176, 8.452]; 8.7% | -7.2% |
| homog-4 (4) | 6.195 [4.863, 7.193]; 19.2% | 9.320 [6.823, 11.066]; 23.5% | 7.589 [5.272, 8.013]; 21.2% | -22.5% |
| homog-8 (8) | 8.383 [7.420, 8.820]; 8.7% | 11.096 [9.418, 11.312]; 9.8% | 7.071 [6.379, 9.223]; 19.6% | +15.7% |
| many-6 (6) | 5.682 [5.160, 5.818]; 6.3% | 6.113 [5.513, 6.305]; 6.9% | 6.410 [5.319, 7.075]; 14.1% | -12.8% |
| varsize (4) | 4.301 [4.160, 4.366]; 2.5% | 4.415 [4.098, 4.472]; 4.7% | 4.616 [4.565, 5.510]; 10.8% | -7.3% |

Verdict: **not accepted as general acceleration**. Only homog-8 crosses the
15% median criterion; one of its three adjacent pairs regresses by 24.3%, and
control/pool ranges overlap. The same candidate serial observations help expose
pool cost, but their variation also prevents treating a ratio as a stable
portable gain. No extra repeats were selected after seeing these results.

Four short s001 copies take median 2.044 seconds serial versus 3.685 seconds
with two workers: 80.3% longer. Pool readiness alone has median 1.404 seconds
and includes interpreter/import work; it may overlap tasks. This supports the
serial default and explicit `--workers 2` opt-in. It does not establish a
universal market-count crossover.

Separate diagnostic profiles measure cgroup memory.peak, including the wrapper
and page cache. They are not used for the unprofiled speed verdict.

| Unit | Control peak MiB | Two-worker peak MiB | Pool ready seconds |
|---|---:|---:|---:|
| dense-3 | 144.5 | 354.0 | 1.263 |
| hetero-mix | 171.0 | 376.9 | 1.275 |
| homog-4 | 150.7 | 363.9 | 1.867 |
| homog-8 | 176.2 | 382.0 | 1.289 |
| many-6 | 162.9 | 368.9 | 1.454 |
| varsize | 150.2 | 367.5 | 1.315 |

All profile launches exit zero with `State.OOMKilled=false`. The saved sub
profiles distinguish simulation from configuration, trace finalization, Parquet
writes and hashing. `profile-summary.json` records each sub, elapsed phase sums
and complete output checks. Cross-worker elapsed sums overlap; they cannot be
subtracted from batch wall time. Raw host launch, adapter batch, readiness,
component and memory evidence is under `out/process-batch/validated/`.

The measured VM is the same pinned local Docker instance throughout: four CPUs
and 18818052096 bytes host memory, ARM64 host emulating linux/amd64; Docker
29.5.2. ABIDES uses Python 3.11, NumPy 1.26.4, pandas 1.5.3 and PyArrow 15.
Measured batch containers are sequential with four CPUs, 16 GiB memory/swap
and network none. The unchanged regression runner sets four CPUs, 16 GiB memory
and network none; it does not add an explicit swap cap.
This local runtime is not the official timing platform.

## Reproduction

The manager must grant the exclusive Docker slot. Do not run concurrently with
another experiment or change the global Docker context. From this worktree:

```sh
TASK_CHECKER='/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python'
tar -cf - baselines/abides_fork/simulate_batch.py experiments/process-batch/Dockerfile | \
  docker --context colima-agenthon build --platform linux/amd64 \
  --build-arg BASE_IMAGE=orchestration-baseline:20261005-a5dbe46 \
  -f experiments/process-batch/Dockerfile -t orchestration-process-batch-final:20261005 -
PYTHONPATH="$PWD" "$TASK_CHECKER" experiments/process-batch/run.py \
  --units-dir "$PWD/units" --out "$PWD/out/process-batch/validated" \
  --candidate orchestration-process-batch-final:20261005 \
  --phase correctness --correctness-workers 1 2
for phase in stress timing startup profile; do
  PYTHONPATH="$PWD" "$TASK_CHECKER" experiments/process-batch/run.py \
    --units-dir "$PWD/units" --out "$PWD/out/process-batch/validated" \
    --candidate orchestration-process-batch-final:20261005 \
    --pool-workers 2 --phase "$phase" --repeats 3
done
```

The public regression runner has no context argument. The scoped wrapper below
always supplies explicit `--context colima-agenthon` without global changes:

```sh
export TASK_DOCKER="$(command -v docker)"
mkdir -p out/process-batch/docker-bin out/tmp
cat > out/process-batch/docker-bin/docker <<'SH'
#!/bin/sh
exec "$TASK_DOCKER" --context colima-agenthon "$@"
SH
chmod +x out/process-batch/docker-bin/docker
PATH="$PWD/out/process-batch/docker-bin:$PATH" DOCKER_CONTEXT=colima-agenthon \
  PYTHONPATH="$PWD" TMPDIR="$PWD/out/tmp" "$TASK_CHECKER" regression_suite/run_regression.py \
  --candidate-image orchestration-process-batch-final:20261005 \
  --scenarios-dir regression_suite/scenarios \
  --reference-dir '/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-05/public-regression-reference-map' \
  --output-dir "$PWD/out/process-batch/validated/regression65" --workers 1
```

Every measured batch container uses network none, four CPUs and 16 GiB including
swap cap. The
same colima-agenthon VM is used sequentially. Raw launch/container/adapter times,
medians, min/max and sample CV must accompany the >=15% elapsed-time criterion
on batches with >=4 markets. Local Mac ARM64/linux-amd64 Rosetta results must not
be extrapolated to official Linux CPU timings. Four-worker unresolved risk and
short-job startup cost justify the conservative serial default and explicit
opt-in pool; no universal optimality is claimed.
