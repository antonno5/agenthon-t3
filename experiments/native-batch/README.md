Executive summary: two workers preserved every event and message but took 19–52% more full-container time than the serial baseline in the four tested public batches. The new adapter with one worker took 7–19% more time. All 104 scheduled runs passed correctness checks. These local arm64-host/linux-amd64-container measurements have `rankable: false` and do not support enabling two workers by default. The experiment remains on its branch.

Archive scope: this directory contains reports and measured data only. Implementation, runners, tests and Docker recipes remain on `codex/exp-20261008-native-batch-parallel` at `546d7f0e9ceba4e17a39a9891d7e2be72f85d294`. Commands below are historical recipes for that experimental checkout; the referenced scripts are not included in this archive. Production code is unchanged. JSON records are preserved byte-for-byte as experiment-completion snapshots.

The implementation is commit `11a9a6c77184d3335932a026c1dee93bea8e3ad6`. This runner is a separate commit so another experiment can cherry-pick the implementation without the measurement scaffolding. Matching, RNG state, native `run_write`, the concurrent two-file writer, and journal hashing are unchanged.

## Fixed comparison

The baseline image must resolve to `sha256:e7f01b18f284f8ff9a5e0fb5591a80dfdaa9e051f76e7076e07ae82293aedd89`, declared source commit `7a5abca889c1fdd77e01edfa9f85762becc1f17b`. The default tag is `track3-native:20261008`. The runner checks the tag against that immutable ID before and after building. Its Dockerfile adds only `simulate_batch.py`, has no `RUN` steps, and does not compile or replace C++ code. Every measurement launches an immutable image ID. Source probes verify matching native-extension hashes, unchanged `simulate.py`/`native.py`, matching package/Python versions, and the candidate dispatcher's source hash.

All containers, including probes and diagnostics, use `linux/amd64`, four CPUs, 16 GiB memory, 16 GiB memory plus swap, and no network. Runs are sequential in the explicit `colima-agenthon` context. The shared advisory lock covers the entire build/check/timing subprocess. The disk cap is not enforced by this local harness and this limitation is recorded.

Correctness covers all six public batch units: `t3-gbatch-homog-4`, `t3-gbatch-homog-8`, `t3-gbatch-hetero-mix`, `t3-gbatch-varsize`, `t3-gbatch-dense-3`, and `t3-gbatch-many-6`. Each gets one baseline, candidate workers1, and candidate workers2 run. The first four units form the timing and memory scope.

| Phase | Count | Used for timing |
|---|---:|---|
| Public correctness, 6 units × 3 modes | 18 | No |
| Native repeat/isolation and fallback/error scripts | 2 | No |
| Warmups, 4 units × 3 modes × 1 | 12 | No |
| Timing, 4 units × 3 modes × 5 | 60 | Yes |
| Whole-container memory, 4 units × 3 modes | 12 | No |

There are 104 scheduled containers, plus two separate runtime/source provenance probes. No historical timing serves as a control. One warmup per unit/mode is retained and excluded. Each mode has five retained timed repeats. Even repeats use `base_serial, workers2, workers1`; odd repeats use `workers1, workers2, base_serial`. Baseline/workers2 are always adjacent AB/BA pairs. Workers1 is a separately retained contemporaneous overhead control, alternating before and after the pair; it does not replace the baseline.

## Historical preparation recipe (experimental checkout)

Use the shared host environment for the scorer dependency. `plan` copies only participant-facing scenario inputs, verifies public manifests/firewall through imported shared toolkit functions, freezes source/input hashes, and writes a result scaffold. It does not call Docker. The evidence directory must be fresh.

```sh
task_python='/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python'
task_root='/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-native-io-batch/worktrees/native-batch-parallel'
task_area='/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-native-io-batch'
task_out="$task_area/native-batch/experiment-20261008"
"$task_python" "$task_root/experiments/native-batch/run_experiment.py" plan \
  --out "$task_out" \
  --slot-wrapper "$task_area/docker_slot.py" \
  --memory-probe "$task_area/memory_probe.py"
```

The script defaults to this worktree's public units and existing `scripts/run_differential_experiment.py`. `--helper` can explicitly select the identical helper in the source repository. The helper's path and hash are frozen, along with the exact source hash of the external slot wrapper and memory probe. The runner does not copy scoring implementations.

## Historical execution recipe (experimental checkout)

```sh
"$task_python" "$task_area/docker_slot.py" -- \
  "$task_python" "$task_root/experiments/native-batch/run_experiment.py" run \
  --plan "$task_out/plan.json"
```

The runner requires the wrapper's active owner record to identify this runner. It refuses changed source, input or plan hashes. `execution-started.json` makes each plan a one-shot execution; failures preserve evidence and a rerun requires a fresh plan/output directory. A rejected run stops the experiment before later samples.

## Checks and clocks

Public runs reuse `run_once`, retention, `exact_tree` and developer `gates` from the existing differential helper. Retention uses shared no-follow sanitization and the unit's exact output allowlist. Only scenarios are mounted into containers; public reference traces remain in the host checker. No sealed data is accessed.

Every sanitized output is compared with the same unit's newly generated baseline correctness output. `exact_tree` checks schema and ordered values. An additional audit literally compares both journals in bounded byte chunks, independently reads their SHA256, checks both sidecar declarations, verifies native events/profile provenance, and checks event/message counts against Parquet footer row counts. It validates aggregate counts and sorted scenario order. These checks occur after the container exits and outside the timed window. Every repeat and warmup receives the same checks.

`check_native_batch.py` retains derived inputs for seeds 0, 42, 42 and `2**32-1`, repeats workers1/workers2 batches, reverses seed dispatch order, and compares each journal with an isolated same-process native run. It checks native provenance and lazy imports. `check_native_batch_failures.py` uses real native and Python execution to verify two native markets followed by serial unsupported-config fallback. It triggers a real C++ writer error with a nonexistent output parent, checks safe serial retry in auto mode, and checks joined workers and complete cleanup in strict mode while preserving pre-existing files. A strict unsupported-config preflight must dispatch zero tasks.

The primary timing is Docker `State.FinishedAt - State.StartedAt`, preserving nanosecond timestamps through the imported helper. It includes configuration, simulation, both file writes, file reads for hashing, metadata publication and interpreter/container exit. Docker CLI launch elapsed time, the adapter's wall clock, and the per-market phase profiles remain secondary diagnostics. Concurrent markets' phase durations must not be summed to infer the whole-batch critical path.

Memory is measured separately with `memory_probe.py`, which keeps a small parent alive while reading cgroup `memory.peak` after the simulator child exits. The cgroup high-water includes that parent and file cache. Child `ru_maxrss` covers the whole child process and all native threads. Both are retained separately, without treating max individual market reports as an exact concurrent peak. Unavailable cgroup memory stays `null`; a missing value is not zero. Memory containers never contribute timing samples. Candidate batch self-reported RSS is also a process-lifetime high-water, not an isolated per-market or batch-only peak.

## Evidence

`plan.json` and its SHA256 freeze all 104 scheduled operations before execution. `results.json` starts with `status: prepared`, `accepted: false`, no runs and no timing results. On execution it records images, source/runtime probes, package versions, every ordered run, checks and errors. Timing summaries are produced only when the complete experiment is accepted. They retain all five samples, medians, ranges, paired base/workers2 ratios and workers1/base median ratios, each marked nonrankable.

`evidence/runs/<unit>/<kind>-<index>/<mode>/` retains raw and sanitized outputs, stdout/stderr, Docker State timestamps, the helper's record and the independent audit. `native-checks/` retains real repeat/isolation/error inputs, outputs, logs and check reports. `memory/<unit>/<mode>/` retains raw/sanitized journals, the memory diagnostic and container logs. `provenance/`, `build.log`, and the result metadata retain the immutable-image and source evidence. The runner never overwrites older experiment evidence or adopts the change into develop.

## Completed local result

The complete predeclared schedule finished successfully without unplanned reruns. Baseline image ID is `sha256:e7f01b18f284f8ff9a5e0fb5591a80dfdaa9e051f76e7076e07ae82293aedd89`; candidate image ID is `sha256:f1305d6a2cfb50d5b5bb3a9b6b46be16895576006a191c06457d796362a7f5dc`. The checker and Docker server report arm64; images are Linux/amd64. Short cross-architecture container runtimes limit generalization to official timing hardware.

Five-sample medians below use full Docker container lifetimes. Workers1 is the overhead control. Positive percentage means more elapsed time.

| Public batch | Baseline, s | Workers1, s | Workers2, s | Workers1 overhead | Workers2 slowdown |
|---|---:|---:|---:|---:|---:|
| t3-gbatch-homog-4 | 0.325511 | 0.370446 | 0.496246 | 13.8% | 52.5% |
| t3-gbatch-homog-8 | 0.414842 | 0.478139 | 0.535289 | 15.3% | 29.0% |
| t3-gbatch-hetero-mix | 0.358755 | 0.428321 | 0.439508 | 19.4% | 22.5% |
| t3-gbatch-varsize | 0.341878 | 0.367066 | 0.407545 | 7.4% | 19.2% |

The adjacent-pair median baseline/workers2 ratios were 0.642, 0.772, 0.821, 0.840 in the same unit order; every value is below one. Workers2 adapter self-reported medians also rose in all four units. The data records the elapsed-time regression; it does not isolate its cause. All five raw samples, ranges and adapter medians are retained in `result.json`.

The 102 public batch output trees passed retention and imported developer gates. Independent audits checked 1062 journal hashes/counts/provenance records, including 1002 literal journal comparisons against fresh baseline anchors. The native script checked 35 repeated/reordered/isolated native outputs, each with two journals. Four real fallback/error cases passed. All scheduled warmups and diagnostics were excluded from the 60 timing samples.

Untimed cgroup high-water memory is shown separately. Each value includes the small probe parent and file cache; child process RSS is retained separately in `result.json`. These distinct counters are not assumed equal.

| Public batch | Baseline cgroup, MiB | Workers1 cgroup, MiB | Workers2 cgroup, MiB |
|---|---:|---:|---:|
| t3-gbatch-homog-4 | 43.1 | 45.6 | 53.6 |
| t3-gbatch-homog-8 | 45.0 | 46.7 | 57.6 |
| t3-gbatch-hetero-mix | 52.1 | 54.7 | 62.2 |
| t3-gbatch-varsize | 45.8 | 48.2 | 60.1 |

Full records and all raw/sanitized journals are retained at `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-native-io-batch/native-batch/experiment-20261008`. The committed `result.json` is a summary with immutable image IDs, frozen source hashes, all timing arrays and pointers/hashes for full evidence. No old timings were reused, and no implementation merge, push or develop adoption occurred. Only reports and measurement data are archived in develop.
