Executive summary: the stable native price-level pool passed pinned correctness on all four assigned scenarios. Complete Docker median time was 2.33% slower on cancel churn, 1.64% faster on deep book, 1.40% faster on STP oldest and 4.89% slower on cancel/modify lifecycle. The candidate won 8 of 20 pairs, so this experiment does not establish a consistent overall speedup. The experiment is complete, non-rankable and not adopted into production.

The frozen measured candidate is `c0d97e59311b81c8b42959ac8b0999930e744bf0`; its matcher implementation is unchanged from `710b6cfc5b4dd50e27ea474bf1b108704f8519ae`. The intervening commit fixed only the build recipe to use the verified local baseline tag. Source base is `ebb266470bee09a426df85d0b2c342b4854b7082`. Baseline image provenance is `7a5abca889c1fdd77e01edfa9f85762becc1f17b`, recorded separately from the experiment source base.

Primary metric is Docker `State.FinishedAt - State.StartedAt`; positive change means a slower candidate. Medians below use exactly five retained timed samples per side, excluding one warmup per side. Paired wins compare baseline and candidate within the same pair.

| Assigned public unit | Baseline median, s | Candidate median, s | Candidate time change | Faster pairs | Result |
|---|---:|---:|---:|---:|---|
| `t3-mp05-cancel-churn-newest` | 0.489491018 | 0.500883057 | +2.33% | 1/5 | Correct, slower |
| `t3-mr-deep-book-state-size` | 0.581231922 | 0.571694049 | -1.64% | 2/5 | Correct, observed faster |
| `t3-mp02-stp-oldest-baseline` | 0.336064269 | 0.331344145 | -1.40% | 3/5 | Correct, observed faster |
| `t3-cancelmodify-lifecycle` | 0.414584971 | 0.434842413 | +4.89% | 2/5 | Correct, slower |

All raw samples follow in pair-index order. Nothing was removed or rerun selectively.

| Unit | Baseline seconds, pairs 0–4 | Candidate seconds, pairs 0–4 |
|---|---|---|
| `t3-mp05-cancel-churn-newest` | 0.488570370, 0.486101184, 0.489520638, 0.489491018, 0.547655344 | 0.500883057, 0.499163125, 0.539875512, 0.504902170, 0.486134365 |
| `t3-mr-deep-book-state-size` | 0.583915524, 0.565256268, 0.581231922, 0.557533268, 0.633608010 | 0.622175546, 0.571694049, 0.557135849, 0.589610486, 0.570361402 |
| `t3-mp02-stp-oldest-baseline` | 0.364873429, 0.325637695, 0.404873258, 0.323345147, 0.336064269 | 0.331344145, 0.332763665, 0.368187661, 0.326242301, 0.320790292 |
| `t3-cancelmodify-lifecycle` | 0.414584971, 0.406962533, 0.416053596, 0.435146766, 0.413889204 | 0.401953179, 0.429024408, 0.458479233, 0.434842413, 0.450180137 |

Secondary phase medians are milliseconds, shown as baseline → candidate. Core includes simulation **and trace finalization**; it is not a matcher-only timer.

| Unit | Core + trace, ms | Core + trace change | Parquet write, ms | Hashing, ms |
|---|---:|---:|---:|---:|
| `t3-mp05-cancel-churn-newest` | 87.038 → 86.565 | -0.54% | 145.248 → 173.241 | 31.355 → 30.517 |
| `t3-mr-deep-book-state-size` | 143.641 → 146.697 | +2.13% | 191.138 → 164.962 | 32.260 → 32.554 |
| `t3-mp02-stp-oldest-baseline` | 25.639 → 25.598 | -0.16% | 83.984 → 84.221 | 11.129 → 11.368 |
| `t3-cancelmodify-lifecycle` | 59.895 → 55.814 | -6.81% | 127.707 → 124.883 | 19.423 → 20.687 |

Lifecycle core + trace is 6.81% shorter while its complete Docker median is 4.89% longer. Deep-book complete Docker time is 1.64% shorter while core + trace is 2.13% longer. Secondary phase results therefore do not establish a complete-run benefit. The 0.3–0.6 second executions show substantial pair-to-pair variation; these five pairs do not justify a general performance claim.

Correctness evidence covers 48 accepted native outputs: 8 excluded warmups and 40 timed runs. Both `trace.parquet` and `message_trace.parquet` passed exact bytes, schema and ordered values against public unit journals in every retained output. All imported shared developer gates passed. There are 24 baseline/candidate comparisons and 40 repeat-stability comparisons, all exact. Actual native provenance and declared journal hashes were checked on every output. Original and focused book tests passed under Linux amd64 optimized compilation and AddressSanitizer/UndefinedBehaviorSanitizer before timing. Python 3.11.17, Arrow 15.0.2 and native extension imports were confirmed in both immutable runtime images.

The only changed production source is `baselines/native/book.hpp`, SHA256 `d3ae721ac4dc178c6a289aa25fba2429f4f8ad7ed90da33782a5d35dad98d096`. Numeric keys, lower_bound, best-price shortcut, tail append and reusable inactive prefix remain. Integer handles index stable owning slots; retiring a level resets its deque, price and total, then invalidates the handle. Free slots are reused. At 64 or more slots with at least half free, reclamation retains live owning pointers and rewrites their handles, preserving level addresses. Index and pool counts are each bounded by `2 * live_levels + 63`; vector capacity retains its usual high-water behavior. Empty sides reset index and pool storage. No order lookup index or FIFO redesign was introduced.

The original 80,000-mutation differential test is unchanged. Focused checks cover stable addresses across insertion and reclamation, stale requests after same-price slot reuse, middle retirement, 4,096 reuse cycles, prefix reuse and the 63/64 compaction threshold, empty reset, aggregate totals, full order fields, FIFO, partial fills and retirement of a 4,096-order queue. Host checks also passed optimized and sanitizer builds plus engine syntax compilation. Host Python was 3.13.3 and was used only to orchestrate standalone host C++ checks; the actual Docker engine used the pinned 3.11.17 runtime.

All builds, pinned checks and timings ran under the campaign `docker_slot.py` exclusive lock. Builds used local tag `track3-native:20261008`; its ID was verified before and after each build. Runs used immutable IDs. Runtime context was `colima-agenthon`, platform Linux amd64, 4 CPUs, 16g memory, 16g swap and network none. Timing order was AB, BA, AB, BA, AB with a fresh baseline per pair. Every outlier is retained. There was no post-timing tuning, extra repeat or scope expansion. The slot is released and no subsequent Docker operation was performed.

Baseline: `sha256:e7f01b18f284f8ff9a5e0fb5591a80dfdaa9e051f76e7076e07ae82293aedd89`.

Candidate: `sha256:e14b6a4d90904db245e7bb787296e15855e263c2522c9d5229b3a2834d3a8a5c`.

The initial phase-2 preflight failed on a mistyped commit argument before any Docker operation. Its record is retained in `out/h03-level-pool/preflight-attempt-01.json`; the retry read the commit directly from Git. No build, correctness or timing attempt failed. The recipe and READY were corrected before timing. Shared Dockerfile and runner were not edited.

`result.json` preserves the full shared runner result, all five samples, per-pair changes/wins, secondary phase samples, self-reported process peak samples, 48 output audits and separate host/pinned diagnostics. `host-result.json` archives the original phase-1 evidence. Complete raw evidence is untracked at `out/h03-level-pool/docker`, with build/check logs and immutable image IDs at `out/h03-level-pool`. No Parquet output is committed. The report uses local emulated amd64 timing on an ARM64 Mac; it is not official hardware or an official ranked result. Historical Python experiments are motivation only; controls here are fresh current-native runs.

Host reproduction uses the frozen measured checkout in a separate directory, because the phase-1 host runner writes its own `result.json`:

```sh
'/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python' \
  expirements/20261008-native-hypotheses/h03-level-pool/run_host_checks.py
```

The executed pinned recipe is `run_granted_docker.py`, invoked under `docker_slot.py` against the measured frozen commit above. Reproduction requires that frozen checkout and a new explicit Docker grant; the final report commit is intentionally later than the measured commit. The shared `run_focused.py` imports the existing checker and shared scoring package. No merge, push, production adoption or full-public regression was performed.
