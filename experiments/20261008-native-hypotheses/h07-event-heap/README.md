Executive summary: The four-ary event queue preserved both journals exactly in all 48 scheduled runs. Full-container median time changed by +2.22% (heavy flow), +15.26% (momentum), -6.42% (latency jitter), and -1.54% (Pareto tail). This mixed five-pair developer result does not establish a general speed improvement.

The candidate stays on `codex/exp-20261008-h07-event-heap`, based on `ebb266470bee09a426df85d0b2c342b4854b7082`. The frozen implementation commit is `3c3964f5bf40cd8b3ea30deb9b786f48bd716e1d`, also recorded in the orchestration directory's `READY-h07-event-heap.json`. No production adoption, push or full-suite regression is part of this experiment.

## Implementation

Only `baselines/native/engine.cpp` and the new `baselines/native/event_heap.hpp` change production sources. `QEntry` moves unchanged to the header so the focused test exercises the actual entry and operations. The simulator retains its existing contiguous `std::vector<QEntry>`; insertion sifts toward `(index - 1) / 4`, and removal selects the smallest of up to four children before sifting down. Entire entries move together.

The comparator still orders `(time, sender, recipient, msg_id)`. Send-time ledger fields, message slots and delayed requeue logic are unchanged. A delayed requeue still modifies only `time`; it leaves `t_send`, `t_recv` and `causal` intact. The production tuple uniquely identifies pending deliveries. Neither the old heap nor this candidate promises stable ordering of comparator-equivalent entries.

## Phase 1 checks

`queue_test.cpp` compares production operations against `std::push_heap`/`std::pop_heap` after every mutation, including every entry field. It covers independently checked tuple ordering, integer extremes, ties, identical duplicates, empty/singleton transitions, sizes 0–129, partial child groups, reverse insertion, a 4,096-entry heap and 32 seeded random interleaving streams. Random streams simulate delayed requeue by removing and reinserting the same entry after changing only its time.

Optimized and AddressSanitizer/UndefinedBehaviorSanitizer builds both passed 767,512 differential operations, including 204,808 delayed requeues. The engine passed host syntax compilation. The original `QEntry` definition and comparator were verified unchanged. Imported shared manifest/firewall checks passed for all four assigned units. See `host_checks.json` for details. These are correctness checks on Apple Clang 17/arm64, with no performance claim and no Docker invocation.

From this worktree, reproduce the standalone checks:

```sh
mkdir -p out/h07-event-heap
clang++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic \
  -I baselines/native expirements/20261008-native-hypotheses/h07-event-heap/queue_test.cpp \
  -o out/h07-event-heap/queue-test
out/h07-event-heap/queue-test
clang++ -std=c++17 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
  -Wall -Wextra -Werror -pedantic -I baselines/native \
  expirements/20261008-native-hypotheses/h07-event-heap/queue_test.cpp \
  -o out/h07-event-heap/queue-test-sanitized
out/h07-event-heap/queue-test-sanitized
clang++ -std=c++17 -fsyntax-only -Wall -Wextra -fno-fast-math \
  -ffp-contract=off -fno-strict-aliasing baselines/native/engine.cpp
git diff --check
```

## Executed Phase 2 recipe

Only these scenarios may be timed:

- `t3-mp07-heavy-flow-oldest`
- `t3-momentum-mix-priority`
- `t3-s019-latency-jitter-kendall`
- `t3-eq001-pareto-latency-tail`

`phase2_run.py` executes the whole build/check/timing sequence under one shared slot. It uses the shared Dockerfile and focused runner without modification. The Dockerfile uses the local `track3-native:20261008` tag as `FROM`; the driver checks that tag against immutable production ID `sha256:e7f01b18f284f8ff9a5e0fb5591a80dfdaa9e051f76e7076e07ae82293aedd89` before and after both builds. Bare image IDs cannot be used as this Dockerfile's `FROM` argument. All runtime probes, focused checks and scenario runs use immutable image IDs.

The builder-stage image supplies the pinned Linux amd64 compiler for the exact production queue differential test. This test runs before any timing. The final candidate replaces only the native extension. Runtime probes assert Python 3.11.17 and Arrow 15.0.2, import the real extension and compare hashes of the unchanged Python adapter. The driver checks frozen candidate sources and shared-tool hashes before starting and native sources again after completion. New tooling is separate from the frozen production sources.

Executed recipe, after the explicit phase-2 grant:

```sh
task_area='/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-native-hypotheses'
task_root="$task_area/worktrees/h07-event-heap"
task_python='/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python'
"$task_python" "$task_area/docker_slot.py" -- \
  "$task_python" "$task_root/expirements/20261008-native-hypotheses/h07-event-heap/phase2_run.py"
```

The evidence directory must be fresh. Completed runs are not repeated or selectively rerun. The shared runner imports the existing differential checker and shared developer gates; no scoring code is copied. The implementation is unchanged after the first timed run.

The prescribed schedule has one excluded warmup per side/unit and five retained AB/BA pairs (`AB BA AB BA AB`), with a freshly executed baseline for each pair. Require actual native execution, exact bytes/schema/ordered values of both journals and imported developer gates on every retained output. Retain every outlier. Primary elapsed time is Docker `FinishedAt - StartedAt`; core/trace, write and hash phases are secondary diagnostics. A candidate that passes correctness but runs slower must be reported as such. A correctness failure cannot support a performance conclusion.

Raw outputs and large journals belong only in `out/h07-event-heap`. Commit compact reports here. This local Mac arm64 host uses Linux amd64 containers and produces non-rankable developer measurements; it does not establish official timing performance.

## Completed paired result

The shared runner completed all 48 scheduled runs: 40 timed samples and eight excluded warmups. No failed attempt, extra repeat or selective rerun occurred. Every output was actually native, passed imported developer gates and matched both journals byte-for-byte, with identical schema and ordered values. The 24 fresh baseline/candidate comparisons and 40 repeat-stability comparisons cover 128 journal comparisons. See `correctness_audit.json`. The pinned queue test is excluded from timing; see `pinned_checks.json`.

Baseline image: `sha256:e7f01b18f284f8ff9a5e0fb5591a80dfdaa9e051f76e7076e07ae82293aedd89`. Candidate image: `sha256:8ba9103877a4abb6bf302446f8e16ff03b8064ef4e183e164b07f985baf9c8a7`. Python 3.11.17 and Arrow 15.0.2 match. Native source hashes remained unchanged; Python adapter hashes match between images.

Full Docker-container medians below include startup, simulation, both journal writes, hashing, metadata and exit. Positive change means slower. Paired wins count the candidate taking less time than the fresh baseline in the same pair. All five samples per side, pairwise changes and ranges are retained in `result.json`.

| Unit | Baseline median, s | Candidate median, s | Time change | Candidate wins |
|---|---:|---:|---:|---:|
| `t3-mp07-heavy-flow-oldest` | 0.409292 | 0.418395 | +2.22% | 3/5 |
| `t3-momentum-mix-priority` | 0.339874 | 0.391728 | +15.26% | 1/5 |
| `t3-s019-latency-jitter-kendall` | 0.322312 | 0.301634 | -6.42% | 4/5 |
| `t3-eq001-pareto-latency-tail` | 0.313916 | 0.309090 | -1.54% | 3/5 |

Secondary phase medians are diagnostic. Core includes trace finalization, so it is not a queue-only measurement. Each cell shows baseline → candidate milliseconds.

| Unit | Core + trace, ms | Parquet write, ms | Hashing, ms |
|---|---:|---:|---:|
| `t3-mp07-heavy-flow-oldest` | 27.766 → 32.360 | 96.734 → 118.900 | 12.786 → 12.762 |
| `t3-momentum-mix-priority` | 31.515 → 39.617 | 84.865 → 91.296 | 11.162 → 10.810 |
| `t3-s019-latency-jitter-kendall` | 10.124 → 8.485 | 66.357 → 70.461 | 4.786 → 5.225 |
| `t3-eq001-pareto-latency-tail` | 11.498 → 10.258 | 76.002 → 72.168 | 5.392 → 5.784 |

The queue passes correctness, but heavy-flow and momentum medians are slower while jitter and Pareto-tail medians are faster. The five-pair samples vary substantially at these short container durations, and the phase measurements do not isolate the causal contribution of the queue. These local emulated measurements provide no basis for claiming a general speedup or adopting the candidate into production. No timing was removed and no tuning followed measurement.

Full raw/sanitized journals, Docker timestamps, build/probe/check/runner logs and complete shared summary remain in `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-native-hypotheses/worktrees/h07-event-heap/out/h07-event-heap/phase2-20261008`. Compact reports are committed here. `result.json` preserves the shared runner's full results, policy, all raw five-sample arrays, pairwise wins and secondary phases, and adds host/pinned diagnostics and log hashes. The slot was released after the single granted sequence; no subsequent Docker operations were performed. No merge, push or source-develop changes occurred.
