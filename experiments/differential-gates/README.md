# Differential developer checks

## Executive summary

A simulator is useful only if its faster runs still produce the same market events
and message deliveries. This experiment adds a local comparison tool that checks
two images against the public references and against each other. It keeps every
repeat, reports the first changed value, and refuses incomplete or failed runs.
It does not change the simulator or scoring rules and produces no official score.

Instrument validation passed on four representative units using real paired image
launches. Both ordered traces and all developer gates passed; 22 actual-output
negative cases were rejected, including three independently verified existing cases.
All measurements are local and non-rankable. No simulator-wide speedup is adopted.

The branch starts at `a5dbe466f038389e96f44d6f71f1258e2eddcbb5`, including the four
upstream patches, typed trace buffers and delivery-ledger optimization. No other
experiment branch was imported. The available local `AGENTS.md` was followed;
its referenced `../../AGENTS.md` is absent.

## What the command checks

`scripts/run_differential_experiment.py run` selects separate baseline/candidate
images, freezes their Docker image IDs, and runs sequentially in the explicit
`colima-agenthon` context. Default selection is the four units below, whose names
exist in the checkout; no replacement was necessary:

- `t3-s001-price-time-priority`
- `t3-mp01-stp-newest-baseline`
- `t3-mp02-stp-oldest-baseline`
- `t3-gbatch-homog-4`

`--units` selects names explicitly. `--all-public` requires all 71 cards. The run
preflight verifies selected public manifests and the firewall with the shared toolkit
before any Docker probe or simulation. Both
options together, duplicate names, unknown units and fewer than three measured
repeats are rejected. `--trace-mode` applies identically to both images; this is
an image comparison, not legacy versus buffered execution in one image.

Each unit runs one baseline/candidate warmup pair, at least three unprofiled
AB/BA/AB pairs, then a separate diagnostic pair with `--profile-components`.
`--no-profile` omits the diagnostic pair, preserving the warmup/repeat contract.
Warmup and profile timings never enter the timing medians. Warmup warms host
caches; every invocation is a new Python process, so per-process JIT/cache state
is not claimed to survive. `container_sec` is Docker State `FinishedAt - StartedAt`;
`host_launch_sec` separately records host CLI elapsed time. The adapter's reported
clock and the residual from container lifetime are separate fields. The residual combines startup
and other container work; it is not an isolated JIT measurement. Component
timings remain diagnostic, not evidence of an unprofiled component speedup.

Inputs are copied with the existing `_stage_input`: only scenario JSON inputs
are mounted read-only, never unit reference traces. Containers get 4 CPU,
16 GiB memory, equal swap limit and no network. The runner checks the timing
slot is idle before each simulation. Disk quota is not enforced by this local
launcher and is explicitly marked false. GPU attachment/timing is outside this
CPU/Rosetta developer experiment.

Every invocation has a hard timeout and bounded stdout/stderr capture. Timeout
kill and final removal also use the explicit Docker context. Raw solver output
is retained only after the existing no-follow C3 sanitizer accepts it. Logs and
runner records live outside solver output. The shared `qfbench2-common` library
is imported, not copied; both sides use `build_developer_verifier` and all actual
g0–g3 gates, including batch isolation and ledger self-consistency on every sub.

For every sanitized output, both `trace.parquet` and `message_trace.parquet`
are compared with available public references. For batch units, the sub list
comes from the organizer's `batch.json`. Sampled reference ledgers may be absent;
the scorer still requires/checks every output sub ledger and the differential
comparison always checks all output ledgers. Each pair and every repeat are
also compared with one another, in original row and field order, without sorting
or tolerance. SHA-256 byte equality, Arrow field/type/metadata schema equality
and exact value equality are recorded separately. Different compression can
give identical values with different bytes. Current pinned-stack acceptance
requires all three checks. The first changed row/column and two adjacent rows
on either side are recorded; missing files and malformed Parquet fail closed.
The runner separately audits declared trace SHA in each events sidecar and any
batch aggregate digest. This matters because the current batch developer scorer
does not bind sub sidecar hashes. Its unchanged verdict and the extra digest
audit are recorded independently; a bad declaration fails runner acceptance.

Evidence records the runner commit/dirty status and source hashes, caller-declared
image source commits, image IDs and repository digests, host/Docker identity,
checker and runtime dependency versions, input/reference hashes, seeds, exact
commands, raw clocks, gate reports, output hashes and optional component profiles.
Runtime versions must match. Host cgroup peak charged memory is saved when available;
on macOS the VM cgroup is normally inaccessible and this field is null. It is kept
separate from process RSS, which the host does not sample. The pinned adapter's
self-reported peak RSS is recorded separately and remains self-reported.

The output directory must be fresh. `summary.json` begins with `complete=false`
and `accepted=false`, is updated after each invocation and remains unsuccessful
on exceptions. Completion requires the full schedule and acceptance also requires
all planned pair/stability comparisons and every gate. Failure exits nonzero.
Even two identically wrong images fail against the references and developer gates.
All evidence has `rankable=false`; Mac ARM64 / linux-amd64 Rosetta times cannot
be extrapolated to official Linux timing.

## Development cycle

After replacing any simulator component, complete this required cycle:

1. Build a separate candidate image from its recorded source revision with the same
   pinned runtime dependencies and baseline patches. Keep the baseline image immutable.
2. Run `make differential-check` with explicit images, candidate source commit, relevant
   units and a fresh output directory. Include `t3-s001-price-time-priority` and the
   affected STP/batch families. Use `DIFF_ALL_PUBLIC=1` when the campaign calls for all 71.
3. Require `summary.json` to be complete and accepted: both exact trace files, ordered
   fields/rows/schemas/SHA, actual full developer gates, batch isolation and every
   paired repeat must pass. Keep unprofiled repeats separate from the diagnostic profile.
   A nonzero exit or incomplete result blocks acceptance of the component change.
4. Save the report, raw evidence paths and verdict, then commit the code, meaningful tests
   and experiment record. Keep speedup and component timings separate; all local evidence
   remains `rankable=false`. A partial unit selection is not an all71 simulator admission.

The Make target uses the repository Python 3.13 checker and the public toolkit pinned by
`make setup` to `qfbench2-common[data]` at `v2.4.4`. Its preflight verifies the installed
version and Git source/tag rather than accepting an unpinned or editable common package.
`PYTHONPATH` explicitly selects this checkout. `DIFF_CHECKER` permits the already pinned
manager checker path; it never replaces the Python 3.11 simulation runtime.
The runner uses `docker --context colima-agenthon` and fresh outputs, and Make propagates
its nonzero status. It does not launch a VM or install dependencies. Wait for the manager's
Docker slot before invoking a real comparison.

```bash
make differential-check \
  DIFF_CHECKER='/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python' \
  BASELINE_IMAGE=orchestration-control:20261005-a5dbe46 \
  CANDIDATE_IMAGE=my-optimized-simulator:local \
  CANDIDATE_COMMIT='full-candidate-source-commit' \
  DIFF_UNITS='t3-s001-price-time-priority t3-mp01-stp-newest-baseline t3-mp02-stp-oldest-baseline t3-gbatch-homog-4' \
  DIFF_OUT=out/differential-gates/component-change-01 \
  DIFF_ARGS="--original-baseline-image orchestration-baseline:20261005-a5dbe46 --control-description 'CLI wrapper removes only root profile.json after successful batch main'"
```

Replace the candidate image/commit with the built candidate's actual values. For all-public
selection, omit `DIFF_UNITS` and set `DIFF_ALL_PUBLIC=1`. Every rerun must choose a fresh
`DIFF_OUT`. `DIFF_ARGS` forwards optional control provenance, repeat, profile and input-root
options; it does not change the mandatory developer gates or make them rankable. Omitting
images, source commit, units/all-public or output directory makes the target fail closed.

## Direct runner commands

This experiment changes the host-side runner only; it needs no image build.
Use the existing contract-only control for the positive self-comparison below.
The manager's control uses the serial baseline unchanged and a CLI wrapper that
removes only the prohibited root `profile.json` after successful batch execution.
It preserves sub profiles and all simulation traces. The original baseline image
is probed separately for each selected batch, and its `path_not_allowed` refusal
is retained under `original_baseline_failures`. Acceptance of the control run
requires those expected original contract failures to be evidenced. The control
is explicitly recorded as `baseline_role=contract_only_control`; it is never
presented as the untouched original image.

```bash
cd '/Users/iopogiba/.codex/worktrees/1797/Агентон'
T3_PY='/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python'
export PYTHONPATH="$PWD"
"$T3_PY" scripts/run_differential_experiment.py run \
  --baseline-image orchestration-control:20261005-a5dbe46 \
  --candidate-image orchestration-control:20261005-a5dbe46 \
  --candidate-commit a5dbe466f038389e96f44d6f71f1258e2eddcbb5 \
  --original-baseline-image orchestration-baseline:20261005-a5dbe46 \
  --control-description 'CLI wrapper removes only root profile.json after successful batch main' \
  --control-source-dir '/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-05/control' \
  --units t3-s001-price-time-priority t3-mp01-stp-newest-baseline \
          t3-mp02-stp-oldest-baseline t3-gbatch-homog-4 \
  --repeats 3 --trace-mode buffered --out out/differential-gates/control-control-01
```

For another experimental image, replace `--candidate-image` and its declared
source commit only. For exhaustive checking, replace `--units ...` with
`--all-public`. Every rerun must choose another fresh output directory.
`--units-dir` can point at a separately materialized public corpus; the runner
detects LFS pointer stubs instead of treating them as Parquet. The manager has
now materialized the pinned public corpus in this worktree without changing Git.

To preserve the original failure as a standalone negative comparison, run the
same command with both images set to `orchestration-baseline:20261005-a5dbe46`,
omit the three control options, and choose a new output directory. Batch
acceptance must fail at the unchanged sanitizer. Do not delete the root profile
inside this runner or widen the allowlist to make that comparison succeed.

The `check` subcommand accepts already captured baseline/candidate output
directories and performs sanitation, both actual developer verifier runs and
the same reference/differential exact comparisons without invoking Docker:

```bash
"$T3_PY" scripts/run_differential_experiment.py check \
  --unit units/t3-s001-price-time-priority \
  --baseline-output /absolute/path/to/baseline/raw \
  --candidate-output /absolute/path/to/candidate/raw \
  --out out/differential-gates/recheck-01
```

## Explicit batch-role arguments

Images may expose a serial default and an optional parallel batch mode. Select that
mode through explicit argv rather than an image wrapper:

```bash
PYTHONPATH="$PWD" "$T3_PY" scripts/run_differential_experiment.py run \
  --baseline-image orchestration-control:20261005-a5dbe46 \
  --candidate-image sha256:9db279bc721ac531b5a51f8dd95f09180011ce9fbc9d5d6d64239705fb893389 \
  --candidate-commit 066bf374d653cf097a3b73be20dd9efc61d9446e \
  --candidate-batch-args-json '["--workers","2","--batch-diagnostics","/diagnostics/batch.json"]' \
  --original-baseline-image orchestration-baseline:20261005-a5dbe46 \
  --control-description 'CLI wrapper removes only root profile.json after successful batch main' \
  --units t3-gbatch-homog-4 --out out/differential-gates/control-batch-workers2-01
```

This immutable ID is the manager-validated `orchestration-process-batch-final:20261005`
image built from the supplied source commit. Wait for this experiment's assigned
Docker slot before running it. `--baseline-batch-args-json` and `--candidate-batch-args-json`
are JSON arrays of strings, defaulting to empty. They apply only to their role's
`simulate-batch` command. The original-baseline contract probe keeps empty extra args;
single-unit commands never receive batch options. The exact arrays are saved in
metadata `role_specific_batch_args`, every invocation's `batch_cli_args`, and the
immutable image's full launch command. The harness refuses overrides of input/output
mount paths, trace mode or profiling through these arguments.

Batch diagnostics use a dedicated `/diagnostics` mount outside solver output.
The only accepted diagnostic path is `/diagnostics/batch.json`. The runner retains
the bounded JSON with the shared no-follow sanitizer and its SHA, and requires
requested/selected worker counts to agree with explicit `--workers`. `/dev/stdout`
is refused: this adapter unlinks that path before writing, losing the diagnostic
from captured stdout. Diagnostic aggregation is present in these batch timings;
detailed component profiling remains a separate run.

The current `orchestration-process-batch-final:20261005` defaults to serial1; its
parallel comparison must explicitly pass `--workers 2`. Keep the contract-only
baseline serial. Use `--baseline-batch-args-json` only if the selected baseline
image supports those arguments. For Make, forward the JSON with its shell quoting
preserved, for example:

```bash
DIFF_ARGS="--candidate-batch-args-json '[\"--workers\",\"2\",\"--batch-diagnostics\",\"/diagnostics/batch.json\"]'"
```

A separate clearly identified heap-image run can cover the three representative
single units; a batch-image run can cover batch isolation. Combine those two run
reports by unit/image/source commit, preserving their commands and separate timings.
This is representative tool coverage, not one combined speedup or all71 admission.
Use the corresponding `--source-run` for each output-only negative-control subset.

## CPU validation and remaining work

```bash
PYTHONPATH="$PWD" "$T3_PY" -m pytest -q -rs \
  --basetemp out/differential-gates/pytest \
  tests/test_differential_experiment.py tests/test_scoring_gate.py \
  tests/test_batch_isolation.py tests/test_malicious_output.py tests/test_run_unit.py

PYTHONPATH="$PWD" "$T3_PY" experiments/differential-gates/replay_reference_controls.py \
  --out out/differential-gates/reference-replay-01
```

The new targeted tests cover positive actual developer gates, nonzero CLI exit
for changed events/row order, wrong SHA, missing ledger, fabricated causal parent,
incorrect latency and a missing batch sub. They also cover batch ledger isolation,
unchanged sanitizer rejection of root profile, identical-but-wrong images,
re-encoded Parquet, schema/metadata changes, exact nullable integers above 2^53,
first-difference context, input isolation, launch failure, incomplete schedules,
AB/BA ordering, exclusion of profile/warmup from medians, bounded logs and explicit
context timeout cleanup. Synthetic negative controls change only temporary fixtures.

The public-reference replay checks all four relevant public units, including
batch isolation. It reuses public reference values as solver-like output solely
to test the checker; it is not a simulator gate result or performance measurement.
All 71 public manifests and firewall checks passed through the shared toolkit.
Raw evidence is in this worktree's ignored `out/differential-gates/` directory.

The initial targeted/related suite had **92 passed, 1 skipped**. The skip is the existing
APFS case/Unicode collision fixture, which requires Linux CI. The new runner has
23 passing cases in that suite. Later actual-output control tests and digest audit
validation are recorded in `result.json`. Ruff and whitespace checks passed.

For a future independent regression run, the unchanged legacy command uses the
external map of the published references. This experiment reused verified #3 evidence:

```bash
DOCKER_CONTEXT=colima-agenthon PYTHONPATH="$PWD" "$T3_PY" regression_suite/run_regression.py \
  --candidate-image orchestration-control:20261005-a5dbe46 \
  --scenarios-dir regression_suite/scenarios/ \
  --reference-dir '/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-05/public-regression-reference-map' \
  --output-dir out/differential-gates/legacy-regression-01 --workers 1
```

For this host-runner-only experiment, the manager also permits reuse of experiment
#3's real regression65 on its final `orchestration-process-batch-final:20261005`
image. Reuse requires a completed successful report bound to that immutable image
ID and confirmation that the regression runner, all 65 scenario configs and public
reference payloads are unchanged. A preflight already verified those source/input
hashes against the base commit and external public map. On 2026-10-06, #3's completed
report and archived image identity were verified against immutable ID
`sha256:9db279bc721ac531b5a51f8dd95f09180011ce9fbc9d5d6d64239705fb893389`
and implementation commit `066bf374d653cf097a3b73be20dd9efc61d9446e`.
All 65 passed: 29 preserved outputs revalidated read-only with their original hashes
unchanged, then 36 actual launches by #3. The source report is
`/Users/iopogiba/.codex/worktrees/d533/Агентон/out/process-batch/validated/regression65/report.json`;
checkpoint/recovery provenance is in the adjacent `regression65-resume/` directory.
Verified evidence fingerprints are saved under this worktree's
`out/differential-gates/regression-reuse-verified.json`. Attribute this regression to #3
and record it as reused evidence, never as a run executed in this worktree. This
avoids repeating the same image regression. It does not replace this runner's own
real representative launch-path checks or actual-output negative controls.

This branch changes the checker/runner only. CLI compatibility was exercised
locally by real subprocess `check` invocations, negative controls, the public
artifact replay, and `run --help`; the real Make launch path also passed on all
four representative units.
The legacy runner selects the explicit context through `DOCKER_CONTEXT`, as
requested by the manager. The new runner always uses `docker --context colima-agenthon`
for run/probe/inspect/kill/remove and does not depend on the global Docker context.

## Actual-output negatives and final instrument criterion

After the manager grants the slot, run the four representative units with a real
optimized queue/pool image as candidate using the same `run` command and its exact
source commit. Preserve the original batch refusal and identify contract-only
control baseline. Then run the negatives against this accepted run without any
new Docker invocation:

```bash
PYTHONPATH="$PWD" "$T3_PY" experiments/differential-gates/negative_actual_outputs.py \
  --source-run out/differential-gates/control-optimized-01 \
  --side candidate --out out/differential-gates/actual-negatives-01
```

The helper requires a complete, accepted image-run report, copies sanitizer-accepted
recorded outputs, and verifies their bindings before and after mutations. It runs
four unchanged positive CLI checks, then 21 negative CLI checks: changed fill price,
row order, delivery sequence, fabricated causal parent and incorrect declared SHA
for every unit, plus missing sub for the batch. Unrelated digest declarations are
repaired for trace mutations so the failure does not merely come from stale hashes.
Every negative must exit 1 with a complete rejected report and an accepted unchanged
baseline; a crashed CLI/parser is not counted as successful rejection. All mutation
copies and CLI logs remain in its fresh output directory. Public references and
the captured source outputs stay unchanged.

Manager evidence already covers real baseline/heap outputs for `s001`: the positive
CLI check passed, and missing ledger, wrong SHA and changed causality each exited 1.
The independently saved reports are in
`/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-05/differential_manager_checks/manager_result.json`;
their checksums and verified outcomes are recorded in this experiment's result.
Do not repeat those negatives. The helper accepts `--units` and `--cases` subsets
and records their exact coverage. For `s001`, run only `--cases event roworder message`.
For the remaining STP/STP/batch units run all default cases; missing-sub is added
automatically for a batch. Merge this coverage with the existing manager evidence
when deciding instrument validation, instead of treating a subset as a full campaign.

The manager's updated instrument criterion requires these real four-unit checks
and unchanged regression65, either executed or explicitly verified/reused from #3.
The `--all-public` selection and 71-unit
corpus preflight are already tested; 71 times warmup/repeats on the identical control
is not required for instrument acceptance. Complete 71-unit simulator campaigns
remain future work and are not claimed as simulator admission here.

The final instrument verdict is `instrument_validation_passed`. The APFS collision
fixture remains a separate Linux CI check. The full 71-unit preflight verifies the
public corpus and selection, and does not establish simulator runtime admission.
`measured_speedup` remains null because this experiment adds a validation tool;
individual local image ratios below do not form a simulator-wide speedup claim.

## Completed evidence, 2026-10-06

The real `make differential-check` runs are retained in this worktree:

- `out/differential-gates/actual-heap-singles-20261006-01/summary.json`: original
  baseline versus heap image on s001, STP newest and STP oldest; 30 accepted records.
- `out/differential-gates/actual-process-batch-20261006-02/summary.json`: serial
  contract-only control versus final process-batch image; 10 accepted records.
- Both launch commands are in the adjacent `<run-directory>.launch.log` files.
  Each unit has one warmup pair, three unprofiled AB/BA/AB pairs and a separate
  profile pair. All 52 pair/stability comparisons passed byte, schema and exact
  ordered-value equality for event and delivery traces; every invocation passed
  unchanged C3, g0–g3 and the additional digest declaration audit.

The final batch candidate is immutable image
`sha256:9db279bc721ac531b5a51f8dd95f09180011ce9fbc9d5d6d64239705fb893389`,
implementation `066bf374d653cf097a3b73be20dd9efc61d9446e`. These match reused #3
regression65 evidence; the source runner, all scenario/config/reference fingerprints
and recovery report hashes are in `out/differential-gates/regression-reuse-verified.json`.
All five candidate batch diagnostics show requested/selected workers **2/2**, with
PIDs `[9,12]` except timing repeat 1, `[8,11]`. Each raw diagnostic JSON and SHA is
recorded under its run's `diagnostics_retained/batch.json`. These participant
component/memory aggregates remain self-reported and may overlap between workers.

The first batch attempt, `actual-process-batch-20261006-01`, passed core trace/gate
checks but lost diagnostics through `/dev/stdout`; `diagnostic-invalid.json` excludes
it from instrument validation. All original artifacts remain. Its timing correction
and the accepted singles correction are recorded in each `timing-correction.json`;
`timing-correction-original/` preserves the previous summary and records. The old
CLI elapsed values are retained as `raw_cli_elapsed_sec`/`host_launch_sec`, while
`container_sec` is recomputed from saved Docker State. No singles were resimulated,
and gate/trace evidence is unchanged. The original runner SHA remains in metadata;
the accepted batch rerun used clean implementation commit `abea3c3`.

Container-lifetime medians in seconds, excluding warmup/profile:

| Unit | Baseline | Candidate | Local baseline/candidate ratio |
|---|---:|---:|---:|
| s001 | 1.637344 | 1.678786 | 0.9753 |
| STP newest | 5.414234 | 5.045664 | 1.0730 |
| STP oldest | 5.556525 | 5.004030 | 1.1104 |
| homog-4 batch | 4.869704 | 4.876108 | 0.9987 |

`out/differential-gates/instrument-validation.json` records separate host CLI,
adapter and residual medians, immutable images and full provenance. The residual
is container lifetime minus adapter-reported elapsed, not an isolated startup cost.
Batch diagnostics add aggregation I/O to its measurements. These Mac/Rosetta local
ratios do not support official timing or adoption of a faster simulator.

Final output-only controls are under `out/differential-gates/`:

- `actual-negatives-s001-20261006-01/negative-summary.json`: one positive, three
  new negatives (event, row order, message).
- `actual-negatives-stp-20261006-01/negative-summary.json`: two positives, ten negatives.
- `actual-negatives-batch-20261006-01/negative-summary.json`: one positive, six
  negatives, including missing sub.
- `manager-s001-evidence.json`: three reused actual negatives (missing ledger,
  bad SHA, causality), with independently verified reports and hashes.

All 19 new negatives exit 1 with complete rejection and an accepted unchanged
baseline; all four positives exit 0. Source output bindings are unchanged.
`docker-slot-release.json` records the explicit release with zero active containers.
The completed test-suite result and checks are recorded in `result.json`.
