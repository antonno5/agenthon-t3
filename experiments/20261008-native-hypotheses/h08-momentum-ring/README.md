Executive summary: the circular MomentumTrader history preserves exact results on all three assigned public units. All 36 native runs pass the shared developer checks and both journals match in bytes, schemas, and ordered values. Complete-container median time changes are +0.37%, +1.58%, and -0.44%, with only 2/5, 1/5, and 3/5 paired wins. These small mixed changes do not establish a stable speedup. The candidate remains experimental and is not adopted.

The candidate replaces the shifting `Trader::mid_hist` vector with
`MomentumHistory`, a vector-backed circular history. Storage grows during startup;
once `lookback + 1` observations are stored, a new mid overwrites the oldest slot
and advances its index. The original startup threshold, past observation,
floating-point arithmetic, book-availability checks, and RNG order are preserved.
Only `baselines/native/engine.cpp` and the new
`baselines/native/momentum_history.hpp` change production code. No other hypothesis
or public configuration is included.

The implementation was frozen before timing at
`59d33ec60a3194dce02b5e15d09ca36cade75053`. All previously accepted native
optimizations remain in place. Source hashes match that commit and stayed unchanged
through the complete series. Historical Python experiments are motivation only;
every timed control is a fresh current-native production run.

The immutable images used for execution are:

- Baseline: `sha256:e7f01b18f284f8ff9a5e0fb5591a80dfdaa9e051f76e7076e07ae82293aedd89`.
- Candidate: `sha256:5adf25c85ca3be219ecba1202a2520658cdf1158bd5674637374ac669d1726bf`.

Builds use the local `track3-native:20261008` tag as `FROM`; its ID was checked
against the immutable baseline before and after each build, and before timing.
The shared Dockerfile and `run_focused.py` were not modified. One shared Docker
slot covered the complete build/check/timing subprocess. The slot is released;
no Docker operation, extra repeat, selective rerun, or tuning followed the series.

Each unchanged public unit had one excluded warmup per side followed by five
pairs in order AB, BA, AB, BA, AB. All executions used `colima-agenthon`,
`linux/amd64`, 4 CPUs, 16g memory, 16g memory-swap, and no network. Both image
runtime audits confirmed Python 3.11.17 and Arrow 15.0.2, imported the actual native
extension, and recorded its hash. `T3_ENGINE=native`, `T3_REQUIRE_NATIVE=1`, and
retained events/profile assertions reject a Python fallback.

Primary timing is Docker `State.FinishedAt - State.StartedAt`, in seconds.
Positive change means slower; negative change means faster. Wins compare the two
runs in the same pair; the change column compares the two five-sample medians.

| Public unit | Baseline median, s | Candidate median, s | Candidate time change | Paired wins |
|---|---:|---:|---:|---:|
| `t3-momentum-mix-priority` | 0.368097817 | 0.369470299 | +0.3729% | 2/5 |
| `t3-ra05-shock-momentum-heavy` | 0.315961023 | 0.320945222 | +1.5775% | 1/5 |
| `t3-sf-03-vol-clustering-momentum` | 0.355240477 | 0.353676733 | -0.4402% | 3/5 |

The first two units are **correct but slower by observed median**; the third has
a slightly lower observed median. Pair direction is mixed, and the run-to-run
spread exceeds these median changes. This evidence does not support adopting h08
as a complete-container optimization. No statistical significance claim is made.

All five primary samples are retained below in pair-index order 0–4; no outlier
is discarded. The machine-readable report also retains every pair, every
secondary phase sample, full policy, image metadata, provenance, and source hashes.

| Public unit | Side | Five full-container samples, s |
|---|---|---|
| `t3-momentum-mix-priority` | baseline | 0.368097817, 0.485477806, 0.414317763, 0.359973007, 0.342307346 |
| `t3-momentum-mix-priority` | candidate | 0.348122401, 0.373558769, 0.429702535, 0.369470299, 0.362464098 |
| `t3-ra05-shock-momentum-heavy` | baseline | 0.423265035, 0.319977434, 0.315961023, 0.294521904, 0.306940322 |
| `t3-ra05-shock-momentum-heavy` | candidate | 0.388423142, 0.365365429, 0.320945222, 0.308406406, 0.320743004 |
| `t3-sf-03-vol-clustering-momentum` | baseline | 0.424388538, 0.355240477, 0.354880677, 0.354503184, 0.364858796 |
| `t3-sf-03-vol-clustering-momentum` | candidate | 0.353676733, 0.362223450, 0.334287395, 0.347967618, 0.423360782 |

Secondary phase medians are diagnostics, in seconds. Native core includes trace
finalization, so it is not matcher-only or ring-only time. These phases cannot
replace the primary full-container measure.

| Public unit | Side | Core + trace, s | Parquet write, s | Hashing, s |
|---|---|---:|---:|---:|
| `t3-momentum-mix-priority` | baseline | 0.035082019 | 0.084199373 | 0.010529523 |
| `t3-momentum-mix-priority` | candidate | 0.032246410 | 0.096732685 | 0.010002786 |
| `t3-ra05-shock-momentum-heavy` | baseline | 0.016880614 | 0.070912642 | 0.007074381 |
| `t3-ra05-shock-momentum-heavy` | candidate | 0.018004398 | 0.073360802 | 0.007345687 |
| `t3-sf-03-vol-clustering-momentum` | baseline | 0.025837661 | 0.101975974 | 0.012103285 |
| `t3-sf-03-vol-clustering-momentum` | candidate | 0.026503107 | 0.087754762 | 0.010880097 |

Correctness evidence covers all 36 retained outputs, including warmups. Imported
shared developer gates pass on each output. There are 48 exact comparison sets
(18 baseline/candidate and 30 within-side stability sets), each checking both
`trace.parquet` and `message_trace.parquet` for byte equality, schema metadata and
types, and exact ordered values/nulls. Native output digests match the retained
files. This is an accepted correctness experiment with `rankable: false` and
`adopted: false`; it is not a correctness failure.

Before timing, pinned Linux/amd64 standalone tests passed vector-reference history
checks for lookback 1, 5, 12, 1024, 16384, and 1,000,000. They cover startup,
multiple wraps, exact floating-point bits (including signed zeros, subnormals,
infinities, and NaN payloads), threshold decisions, available book sides, and
copy/move state. The maximum lookback includes full startup, 257 overwrites, and
a full retained-history drain. The adapter's 1–1,000,000 envelope is unchanged.

A mixed native fixture with a scheduled shock, momentum lookbacks 1, 5, 12, 1024,
and three seeds (17, 767052790, 1007636279) produced identical dumps of all native
trace and message columns against the base vector engine. Each momentum agent
places orders. The Linux dump has 41,407,632 bytes and SHA-256
`b23eb8a68594fbd18e20b1401660fbc0a4a9e02d5224f7f3c167cf39d356c8d8`, also matching
the host dump. macOS arm64 checks passed Apple Clang 17 syntax compilation,
reference tests, AddressSanitizer, and UndefinedBehaviorSanitizer. These synthetic
fixtures are correctness diagnostics; their elapsed times were not measured or
used as public performance evidence.

`result.json` preserves the complete focused-runner result and adds host/pinned
diagnostics. `docker-recipe.json` records the executed procedure;
`run_phase2.py` is the executed build/check/measurement wrapper. Raw evidence,
including every retained journal, lives only under `out/h08-momentum-ring`:

- `host/host-checks.json`: host command transcripts and fixture identity.
- `phase2/provenance.json`: build logs/hashes, pinned diagnostics, runtime audits.
- `phase2/pinned/`: Linux standalone binaries and exact native-column dumps.
- `phase2/timing/summary.json`: all 36 records, inputs, and 48 comparisons.
- `phase2/timing/runs/`: all warmup and timed raw/retained outputs and validations.
- `phase2/timing/result.json`: unchanged raw focused-runner result.

The shared-slot command used for this granted series was:

```sh
'/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python' \
  '/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-native-hypotheses/docker_slot.py' -- \
  '/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python' \
  expirements/20261008-native-hypotheses/h08-momentum-ring/run_phase2.py
```

This is an execution record, not authorization for another timing series. The
wrapper refuses to reuse its existing evidence directory. Host-only checks remain
available through `host_checks.py` without Docker.

Timing was collected on an ARM64 Mac with emulated Linux amd64 containers, not
the official timing hardware. The three assigned units have lookbacks 5, 5, and
12; no large-lookback synthetic timing is substituted for those public configs.
No all-public/full71 regression, merge, cherry-pick, push, or production change
was performed. Shared scoring was imported, never copied; no private sealed data
or answer keys were accessed. Source `AGENTS.md` was followed within the focused
scope; its referenced parent `../../AGENTS.md` is absent from both checked locations.
