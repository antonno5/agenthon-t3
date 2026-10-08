Executive summary: the candidate preserves both journals exactly and passes all developer gates on the four assigned units. Full Docker median time improves by 4.84% and 4.81% on two units, but worsens by 0.97% and 0.25% on two others. All five pairs are retained; the mixed results do not establish a uniform benefit. This remains an experimental, non-rankable result with no production adoption.

# H06: allocate Arrow string data once

The only production source change is `baselines/native/pqwrite.cpp`, on
`codex/exp-20261008-h06-arrow-strings`, from base
`ebb266470bee09a426df85d0b2c342b4854b7082`.

Each of the three fixed vocabularies caches its lengths once. `string_array`
validates the row count and vocabulary codes, builds the original signed 32-bit
offsets with checks before addition, then requests one Arrow data buffer of the
exact logical length. Direct copies fill that buffer without vector insertion,
capacity growth, or zero-initializing its contents. Arrow retains ownership until
the table finishes writing. Empty data preserves the original null pointer and
zero size: using `AllocateBuffer(0)` instead changed empty-table behavior in the
host library and was corrected before freezing the candidate.

The columns remain Arrow UTF-8 with no string nulls. Numeric validity bitmaps,
schema and pandas metadata, row-group size, page version, dictionary encoding,
Snappy, writer properties, hashes, threading, batch behavior and dependencies
retain their existing code and settings. The pinned runtime remains Python
3.11.17 and Arrow 15.0.2.

## Host evidence

Run from this source worktree:

```sh
task_python='/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python'
"$task_python" expirements/20261008-native-hypotheses/h06-arrow-strings/run_checks.py
"$task_python" expirements/20261008-native-hypotheses/h06-arrow-strings/run_checks.py --sanitize
git diff --check
```

The actual host is Apple ARM64, Python 3.13.3 / Arrow 25.0.1 / Apple clang 17.
Arrow 25 headers require C++20, so the runner selects C++20 for that host only;
it selects the production C++17 setting for Arrow 15. The initial C++17 host
compile failure was a header-version mismatch, not pinned-runtime evidence.

`check_strings.cpp` includes the real candidate source and the base commit's
writer in separate namespaces. Its message vocabulary is extracted from the
actual engine source, rather than maintained as a second list. The checks cover:

- Empty, one-row, every-code and seeded 16,384-row columns for trace types,
  sides and message types; maximum valid code and first invalid/255 codes.
- Exact offset/data buffers, UTF-8 types, string validity, ordered values and
  identical validation behavior, including the empty buffer's null pointer.
- Negative/mismatched row counts and reaching `INT32_MAX` exactly before
  rejecting an additional byte, without allocating gigabytes in the test.
- Both journal writers at 1 and 16,384 rows, numeric columns with no nulls and
  mixed nulls; complete-file bytes, schemas including metadata, and ordered values.
- Identical empty-table error behavior against the original writer. In host
  Arrow 25, the original null data pointer causes a validation error; this
  experiment preserves it instead of changing empty-table semantics.
- The same checks with AddressSanitizer and UndefinedBehaviorSanitizer enabled.

Evidence is in `out/h06-arrow-strings/host/checks.json` and
`checks-sanitized.json`, with generated sources, binaries, logs and Parquet files
beside them. Large/raw evidence is not committed. These are correctness checks
on a different host runtime, not simulation timing; Arrow 15 validation is recorded separately below.

## Reproduction recipe — completed under the explicit phase-2 grant

The phase-2 driver completed the builds, focused checks and fixed paired series below. Do not rerun the series without a new explicit grant.
Run them sequentially under the orchestration Docker slot grant. Prepare the
source bundle on the host, then build using the shared orchestration Dockerfile
and the verified local baseline tag. BuildKit cannot use a bare image ID as a FROM reference. Verify the tag before and after each build; test/run always uses immutable IDs. Bind mounts keep test artifacts outside
the images and production source read-only during checks.

```sh
task_area='/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-native-hypotheses'
task_worktree="$task_area/worktrees/h06-arrow-strings"
task_evidence="$task_worktree/out/h06-arrow-strings/pinned"
task_baseline='track3-native:20261008'
task_python='/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python'
"$task_python" "$task_worktree/expirements/20261008-native-hypotheses/h06-arrow-strings/run_checks.py" --out "$task_evidence" --prepare-only

docker --context colima-agenthon build --platform linux/amd64 \
  --build-arg BASE_IMAGE="$task_baseline" --target native_builder \
  --iidfile "$task_evidence/builder-image.iid" \
  -f "$task_area/Dockerfile" "$task_worktree"
task_builder=$(cat "$task_evidence/builder-image.iid")
docker --context colima-agenthon run --rm --platform linux/amd64 \
  --cpus=4 --memory=16g --memory-swap=16g --network=none \
  -v "$task_worktree:/work:ro" -v "$task_evidence:/evidence" \
  "$task_builder" python \
  /work/expirements/20261008-native-hypotheses/h06-arrow-strings/run_checks.py \
  --out /evidence --prepared --require-pinned

docker --context colima-agenthon build --platform linux/amd64 \
  --build-arg BASE_IMAGE="$task_baseline" \
  --iidfile "$task_evidence/candidate-image.iid" \
  -f "$task_area/Dockerfile" "$task_worktree"
task_candidate=$(cat "$task_evidence/candidate-image.iid")
task_commit=$(git -C "$task_worktree" rev-parse HEAD)
"$task_python" "$task_area/run_focused.py" --slug h06-arrow-strings \
  --candidate-image "$task_candidate" --candidate-commit "$task_commit" \
  --out "$task_worktree/out/h06-arrow-strings/paired"
```

Use the frozen implementation commit recorded in `READY-h06-arrow-strings.json`;
verify it matches `task_commit` before any measurements. Do not change or tune
the implementation after seeing timing. Record immutable image IDs, source
hashes and pinned runtime, and require actual native execution without fallback.

Only these four units may be timed:

- `t3-mr-deep-book-state-size`
- `t3-mp05-cancel-churn-newest`
- `t3-s001-price-time-priority`
- `t3-gbatch-hetero-mix`

The shared runner is responsible for one excluded warmup per side followed by
five AB/BA pairs, a fresh baseline per pair, exact bytes/schema/ordered values
for both journals (every market for the batch), and imported shared developer
gates on every retained output. Retain every outlier. Complete Docker elapsed
time is primary; core and journal write/hash phases are secondary. Keep
correctness failure separate from correct-but-slower. These are local,
non-rankable experiments with no production adoption, full-suite run, push,
merge or cherry-pick into develop.

The granted phase-2 entrypoint wraps this sequence with the required exclusive slot, records all commands and logs, verifies the baseline tag before/after both builds, checks both runtime versions/native extensions, and calls the unchanged shared timing runner:

```sh
"$task_python" "$task_area/docker_slot.py" -- "$task_python" "$task_worktree/expirements/20261008-native-hypotheses/h06-arrow-strings/execute_phase2.py"
```

## Phase-2 results

Frozen measured commit: `34ddeca0d64108346c8b697d68ce6694b78deb6d`. Original implementation: `da88b3f3be9ee891c002e56e0b0a4d6a2bce207d`. The production source hash stayed `6d62f6e761735095a9a28d22922468f3a01a9db55be5afd59226f511151bec68` throughout; only phase-2 tooling was added before timing. No implementation changes, tuning, added repeats or selective reruns followed the first timing sample.

Baseline image: `sha256:e7f01b18f284f8ff9a5e0fb5591a80dfdaa9e051f76e7076e07ae82293aedd89`. Candidate image: `sha256:3c88777a2b1fe3596cdf70947ee29ea4b5800619b51a89bba3f1c40f4834f104`. Builder image: `sha256:156f67ebe0ff20109059b3c7c598a9ac664ef19f8f6b63d0f537696053c5be66`. The local baseline tag matched its immutable ID before and after both builds.

Pinned focused checks passed on Python 3.11.17 / Arrow 15.0.2 / C++17, including exact Arrow offsets/data, code/offset boundaries, both complete journal files, schemas/metadata and the original zero-row validation errors. Both runtime probes loaded the actual native extension. The simulation series retained 48 accepted outputs: 8 excluded warmups and 40 timed samples. All outputs passed imported developer gates g0–g3, declared digest checks and actual-native assertions. All 64 baseline/candidate and repeat-stability comparisons passed exact bytes, schemas and ordered values, including both journals of every batch market.

The primary clock is Docker `FinishedAt - StartedAt`, in seconds. Each row uses five AB/BA pairs with a fresh baseline per pair; negative time change means faster. No outlier is removed.

| Unit | Baseline median (s) | Candidate median (s) | Time change | Faster pairs | Outcome |
|---|---:|---:|---:|---:|---|
| `t3-mr-deep-book-state-size` | 0.658820650 | 0.626916601 | -4.84% | 3/5 | Correct, faster median |
| `t3-mp05-cancel-churn-newest` | 0.503741558 | 0.508624139 | +0.97% | 2/5 | Correct, slower median |
| `t3-s001-price-time-priority` | 0.288067125 | 0.274220913 | -4.81% | 4/5 | Correct, faster median |
| `t3-gbatch-hetero-mix` | 0.393789536 | 0.394783024 | +0.25% | 2/5 | Correct, slower median |

All retained Docker samples, in pair-index order 0–4:

| Unit | Baseline samples (s) | Candidate samples (s) |
|---|---|---|
| `t3-mr-deep-book-state-size` | 0.572812954, 0.636455032, 0.658820650, 0.704396254, 0.721301553 | 0.677795666, 0.697212439, 0.626916601, 0.561440515, 0.537451419 |
| `t3-mp05-cancel-churn-newest` | 0.503741558, 0.714674447, 0.474033472, 0.523606945, 0.466935275 | 0.489565908, 0.508624139, 0.513854708, 0.565390727, 0.490317671 |
| `t3-s001-price-time-priority` | 0.327501020, 0.291120591, 0.288067125, 0.282307091, 0.261105174 | 0.293977523, 0.259321690, 0.289003917, 0.274220913, 0.258656717 |
| `t3-gbatch-hetero-mix` | 0.453867358, 0.393789536, 0.407855323, 0.384489826, 0.376829967 | 0.394783024, 0.379485215, 0.420472429, 0.425289820, 0.392961686 |

Secondary diagnostics below are median phase seconds (baseline → candidate). The core phase includes simulation and trace finalization; batch values are sums across markets. They are separate diagnostics, not the complete-container result. Every phase retains all five raw samples in `result.json`.

| Unit | Core + trace | Parquet write | Hash |
|---|---:|---:|---:|
| `t3-mr-deep-book-state-size` | 0.180056733 → 0.158419113 | 0.183332505 → 0.179685255 | 0.034637101 → 0.032558456 |
| `t3-mp05-cancel-churn-newest` | 0.088425141 → 0.075810753 | 0.148228976 → 0.168355719 | 0.029077537 → 0.032327823 |
| `t3-s001-price-time-priority` | 0.003813197 → 0.004194503 | 0.063841685 → 0.052784574 | 0.002588685 → 0.002083645 |
| `t3-gbatch-hetero-mix` | 0.020727544 → 0.021158769 | 0.130092353 → 0.123156701 | 0.013695262 → 0.013539763 |

Parquet-write time falls on deep-book, price-time and batch, but rises on cancel-churn. The core implementation was unchanged, so its fluctuations cannot be attributed to this writer optimization. Core and container dispersion, and only 2/5 candidate wins on both slower-median units, make the overall evidence mixed. These local ARM64-host / Linux-amd64 emulation measurements are not official timing hardware. There is no full-71 run and no merge, push or adoption.

The entire Docker series ran inside the shared `docker_slot.py` lock. The lock is released and no further Docker operations are scheduled. Commands, build/test/runtime logs, baseline tag checks and immutable IDs are in `out/h06-arrow-strings/phase2/execution.json`. Focused pinned artifacts are in `out/h06-arrow-strings/phase2/pinned`; all raw and retained journals, run records, exact comparisons and gate evidence are in `out/h06-arrow-strings/paired`. Committed `result.json` preserves the full shared-runner results/samples/policy and adds host and pinned diagnostics. Raw Parquet evidence remains uncommitted.
