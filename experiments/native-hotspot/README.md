Executive summary: A small C function removes slow pandas row wrapping from a final order-book calculation while preserving its exact answers. Actual simulator validation confirms unchanged trades and messages. The primary full-container test misses the required 5% improvement: C is 2.84% slower than baseline and 5.40% slower than direct Python. The experiment is retained with verdict do_not_promote_native; the final public-regression status is recorded in result.json and REPORT.md.

# Native liquidity-gap experiment

Base commit `a5dbe466f038389e96f44d6f71f1258e2eddcbb5`, immutable baseline
`sha256:0bd010981f4f4a8aa8bdd074e5342a56bfe91daf25e5c5d7e04c075d082c99e2`.
Pinned upstream ABIDES: `f9cbe51342b7dedd9587e4e069040d68a5c6477f`.
This base already includes the four official upstream patches, buffered traces
and optimized message ledger. The experiment overlay changes one termination
bookkeeping method. Scorer, cards, configs, references and event processing are
unchanged. No sealed data is used. Available project instructions apply;
`../../AGENTS.md` is absent.

## Implementation

`dropout.patch` replaces the `get_time_dropout` iterrows loop with a call to
`dropout.c`. Original empty-book behavior, DataFrame construction, horizon and
final metrics remain. Exact Python integer arithmetic preserves nanosecond
intervals, NumPy integer timestamps and values beyond int64. Histories remain
ordered; duplicate/negative intervals, initial gaps and unclosed trailing gaps
follow original behavior. It neither draws RNG values nor changes events.

One C crossing occurs per nonempty symbol book, with constant native workspace
and the GIL retained. Borrowed references do not escape the call. Errors
propagate without fallback. `apply_patch.py` refuses a changed source hunk.
`dropout-python-control.patch` uses the same hunk with a direct Python helper,
separating savings from removal of row wrappers from compilation itself.

The current oracle baseline diagnostic places this section at 10.56% of total
cProfile time; the instrumentation-dependent ideal Amdahl ceiling is about
1.118×. It is separate from the already optimized message ledger and C-backed
heapq. A narrow CPython extension supplies the needed traversal without a new
runtime dependency or JIT, but adds compiler/ABI maintenance. REPORT.md compares
that cost with the Python control and full-container results.

## Runtime and builds

The Linux/amd64 overlays inherit Python 3.11.17, NumPy 1.26.4, pandas 1.5.3 and
PyArrow 15.0.2. A compact compiler stage inherits baseline and pins
`gcc-14=14.2.0-19`, `libc6-dev=2.41-12+deb13u4` from signed Debian trixie snapshot
`https://snapshot.debian.org/archive/debian/20261004T000000Z/`.
`evidence/compact-compiler.json` records snapshot/index verification. No pip
packages are installed. Only the extension binary is copied into the final
stage; dependencies are available offline. The control image needs no compiler.

`build_manager.py` checks an idle exclusive Docker slot, existing baseline and
at least 1 GiB free on both host and the existing Colima VM before each build.
It uses explicit `--context colima-agenthon`, does not start a VM or remove
foreign images/caches, and logs compiler versions, elapsed time and image size.
The build context whitelist excludes units/references. The reserve is a
conservative preflight threshold, not a build capacity guarantee.

First builds with baseline cached took C 19.754737 s and Python 2.075951 s;
cached builds took 0.440551 / 0.365196 s. Cached rebuild changed image IDs even
though stages reported CACHED. The cold ID stopped resolving. Installed-method
parity was rechecked on the active image, with the same binary SHA-256; no
RootFS equality is asserted. Validated active identities:

- Native: `sha256:ff5f54c5119fed7f38897239e5f2a1f373fb5731b4160c88926d7cf9f7840a83`
- Python: `sha256:ed70986ba62d4feb87c9c26c7929e4b0e10a8c4af59e2e55ae2e0e8d9a839f61`

## Reproduction

Run Docker commands only while holding the manager-assigned exclusive slot.
The checker below is a host Python 3.13 environment; it validates files and
orchestrates containers, and does not replace simulator Python 3.11.

```sh
export CHECKER_PYTHON='/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python'
export PYTHONPATH="$PWD"
export RUN_OUT='out/native-hotspot/runtime-20261006'

"$CHECKER_PYTHON" experiments/native-hotspot/build_manager.py \
  --check-only --out "$RUN_OUT/build-preflight"
"$CHECKER_PYTHON" experiments/native-hotspot/build_manager.py \
  --out "$RUN_OUT/build-cold"
# Use a separate build-cached output to preserve the first-build evidence.
# Rebuilds can change IDs; inspect and pin resulting IDs before validation.

"$CHECKER_PYTHON" experiments/native-hotspot/validate.py \
  --baseline sha256:0bd010981f4f4a8aa8bdd074e5342a56bfe91daf25e5c5d7e04c075d082c99e2 \
  --python-control sha256:ed70986ba62d4feb87c9c26c7929e4b0e10a8c4af59e2e55ae2e0e8d9a839f61 \
  --candidate sha256:ff5f54c5119fed7f38897239e5f2a1f373fb5731b4160c88926d7cf9f7840a83 \
  --repeats 3 --out "$RUN_OUT/paired"
"$CHECKER_PYTHON" experiments/native-hotspot/full_gates.py \
  --out "$RUN_OUT/sanitized-gates"
"$CHECKER_PYTHON" experiments/native-hotspot/run_public_regression.py \
  --candidate-image sha256:ff5f54c5119fed7f38897239e5f2a1f373fb5731b4160c88926d7cf9f7840a83 \
  --reference-dir '/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-05/public-regression-reference-map' \
  --workers 3 --out "$RUN_OUT/public-regression"
```

The source cached at `out/native-hotspot/source/exchange_agent.py` is pinned by
SHA-256 `e0c7941b8782f5ebe17e1b9f01c36f9e7ba5796caf9911d213d6e10e76b23615`.
`runtime_checks.py` runs inside the native image with experiment scripts mounted
read-only, source supplied via `--source` and a writable diagnostic `--out`.
It tests 109 original/Python/actual-installed-method histories and asserts the
compiled builtin, interpreter/library versions, binary hash and zero JIT.
Historical host differential checks use `build_local.py`, then pytest with
`QFB2_ABIDES_EXCHANGE_SOURCE` pointing to that source. Host component evidence
is retained separately from actual Linux-image `runtime-component.json`.

## Validation and interpretation

`validate.py` checks the slot before serial runs: one warm-up per image/unit,
three reversed unprofiled variant sets and separate diagnostics (45 containers).
Network none, four CPUs, 16 GiB, identical inputs/seeds and buffered trace mode
apply to each image. Full developer gates, frozen reference hashes and exact
schema/ordered values/bytes of both trace files are required for all variants.
Nine cProfiles enrich the already planned diagnostics via a separate mount;
raw profile files and effective commands stay outside participant output.
Diagnostics never enter speed medians.

`full_gates.py` adds nine serial checks through the existing bounded developer
harness and shared C3 no-follow retention, including both retained traces and
local host metrics. These checks are excluded from timing. The raw paired
runner's logs are retained diagnostic evidence, without a C3 sanitation claim.
All developer results are `rankable=false`.

The primary threshold is at least 5% median full-container reduction on
`t3-as05-oracle-variant`. s001 and churn remain correctness/performance controls;
`strict_each_unit` is an additional all-units timing flag. Equal/better Python
meeting the target would favor Python; mixed incremental native pairs do not
justify C. Compiler/build costs, control behavior and memory are reported
separately. Current primary threshold fails, so native is not recommended.

Container time includes startup/imports and Docker transport. Outside-adapter
time is a residual, not an isolated import measurement. Peak process RSS is
self-reported, not official cgroup memory. Synthetic Python-heap measurement
excludes the input book. Mac-host emulated timings do not extrapolate to
production Linux CPU or official Final scoring.

The native-only public regression uses the unchanged standard runner/semantics
and external frozen public reference map. It binds actual image, config/ref
hashes, runner hashes and worker caps. At most three correctness-only containers
receive 3 GiB memory/swap each. It runs after all serial measurements, and its
events/sec is not performance evidence. No second Python-control regression is
required without an identified risk.

Recovery: repeat the same regression command/output directory. Cached regular
trace/events files are rechecked serially through the standard checks before
any new launches; cached PASS labels are not trusted. Only missing/partial
scenarios launch. Changed identities or unsafe links refuse reuse. The parent
atomically writes each checkpoint and partial report; require `complete=true`,
all 65 results and no errors/failures before closure.

Compact evidence lives in `evidence/runtime-20261006/`, raw outputs/logs/profiles
in ignored `out/native-hotspot/runtime-20261006/`. REPORT.md explains the result;
result.json supplies machine-readable numbers and exact commands.
