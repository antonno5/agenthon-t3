Executive summary: bounded parallel Parquet encoding passed pinned byte correctness, but did not deliver a radical gain. Standalone write-plus-close improved by 1.23–1.46×, below the aspirational 2× encoding target. Complete-container median time fell by 14.32%, 5.09%, 0.41% and 7.91% on the four assigned large scenarios. The 0.41% horizon result is small and only three of five pairs were faster. All fixed samples are retained; there were no adaptive repeats, source changes, adoption, merge or push.

The implementation is commit `c9ec65640d6904ab01a26d2369caef5075aca86b` on `codex/exp-20261008-component-h02-parquet-parallel`. Only `baselines/native/pqwrite.cpp` changes production behavior. One process-wide Arrow ThreadPool with two workers encodes both journals; simulation and ledger dispatch remain outside it. Trace uses buffered RecordBatch row groups of 1,048,576 rows; messages retain 65,536-row callbacks. Dense columns retain progressive dictionary growth, default 1,024-row encoder write batches, original page/dictionary thresholds, Snappy, metadata/nulls, 64Mi property maximum and staged ledger publication. Input validation and empty/error behavior are preserved.

Primary complete-container timing (seconds). Positive reduction means faster. All five samples per side, pair ordering and outliers are in [result.json](result.json). The clock is Docker State FinishedAt minus StartedAt. These are local non-rankable measurements.

| Scenario | Baseline median | Candidate median | Time reduction | Faster pairs |
|---|---:|---:|---:|---:|
| t3-gb-mega-throughput | 1.645488 | 1.409881 | 14.32% | 4/5 |
| t3-gb-pop-horizon-scale | 0.930198 | 0.882847 | 5.09% | 4/5 |
| t3-gb-horizon-240s | 0.920293 | 0.916544 | 0.41% | 3/5 |
| t3-mr-deep-book-state-size | 0.663914 | 0.611425 | 7.91% | 4/5 |

Standalone encoding on identical real baseline engine columns (write plus close to an in-memory sink, excluding setup). Output hashes matched the original real Parquet files on every sample. These clocks include Arrow/Parquet encoding, compression, group/file close and memory sink copying. They exclude simulation, vector-to-Arrow construction, input reading, disk output and producer waiting.

| Scenario | Trace baseline → candidate, s | Trace speedup / reduction | Ledger baseline → candidate, s | Ledger speedup / reduction |
|---|---:|---:|---:|---:|
| t3-gb-mega-throughput | 0.204033 → 0.144246 | 1.414× / 29.30% | 0.354844 → 0.257631 | 1.377× / 27.40% |
| t3-gb-pop-horizon-scale | 0.138104 → 0.103190 | 1.338× / 25.28% | 0.257033 → 0.176427 | 1.457× / 31.36% |
| t3-gb-horizon-240s | 0.117624 → 0.094226 | 1.248× / 19.89% | 0.193559 → 0.152842 | 1.266× / 21.04% |
| t3-mr-deep-book-state-size | 0.076985 → 0.062581 | 1.230× / 18.71% | 0.123338 → 0.089300 | 1.381× / 27.60% |

Separate overlap and pipeline diagnostics. Overlap starts two outside writer callers on the same real columns, sharing the two-worker encoder pool. Its wall clock includes writer setup, write, close and join. Pipeline uses disposable instrumented extensions with identical clocks on both sides and the normal simulation/file-output path; its run_write wall excludes imports/config building/hashing. Neither is the primary container clock.

| Scenario | Two-file overlap baseline → candidate, s | Overlap reduction | Instrumented pipeline baseline → candidate, s | Pipeline reduction |
|---|---:|---:|---:|---:|
| t3-gb-mega-throughput | 0.380280 → 0.349103 | 8.20% | 1.134889 → 0.977122 | 13.90% |
| t3-gb-pop-horizon-scale | 0.249029 → 0.248163 | 0.35% | 0.653616 → 0.552261 | 15.51% |
| t3-gb-horizon-240s | 0.216623 → 0.201651 | 6.91% | 0.539979 → 0.416713 | 22.83% |
| t3-mr-deep-book-state-size | 0.139509 → 0.128713 | 7.74% | 0.278360 → 0.242058 | 13.04% |

Median pipeline waits and callbacks, seconds (baseline → candidate). These medians overlap and must not be added into total elapsed time. Engine wall includes producer wait and lifecycle assembly; producer condition-variable wait excludes mutex acquisition. Ledger callbacks include array construction, RecordBatch encoding and row-group flush. Trace wall includes conversion and file finalization. finish_wait is the extra wait after trace writing; ledger close/finish may describe the same work.

| Scenario | Producer wait | Ledger callbacks | Ledger close | Trace writer | finish_wait |
|---|---:|---:|---:|---:|---:|
| t3-gb-mega-throughput | 0.330551 → 0.221666 | 0.639209 → 0.478526 | 0.098434 → 0.098644 | 0.318097 → 0.271230 | 0.099381 → 0.099584 |
| t3-gb-pop-horizon-scale | 0.059445 → 0.015610 | 0.256796 → 0.160622 | 0.111063 → 0.136605 | 0.202193 → 0.143852 | 0.111952 → 0.137732 |
| t3-gb-horizon-240s | 0.076417 → 0.018481 | 0.214967 → 0.124408 | 0.123574 → 0.099190 | 0.147637 → 0.113701 | 0.124962 → 0.100658 |
| t3-mr-deep-book-state-size | 0.018063 → 0.000001 | 0.119952 → 0.086487 | 0.043003 → 0.047636 | 0.088212 → 0.067229 | 0.043930 → 0.049706 |

Structural counters and input identity. Both sides use exactly the same rows, schema, nulls and vocabulary; the IPC input hash and real Parquet digest are stored in [component-results.json](component-results.json). Both writer modes preserve the original 1Mi groups. Callback/submission counts match exactly on every pipeline sample.

| Scenario | Trace rows / groups | Ledger rows / groups | Ledger callbacks / submissions, both sides |
|---|---:|---:|---:|
| t3-gb-mega-throughput | 1,168,360 / 2 | 1,420,862 / 2 | 22 / 22 |
| t3-gb-pop-horizon-scale | 725,591 / 1 | 892,129 / 1 | 14 / 14 |
| t3-gb-horizon-240s | 555,032 / 1 | 692,641 / 1 | 11 / 11 |
| t3-mr-deep-book-state-size | 319,488 / 1 | 269,644 / 1 | 5 / 5 |

The source audit is in [source-audit.json](source-audit.json). Arrow 15.0.2 WriteTable is serial even with use_threads enabled. Buffered WriteRecordBatch creates distinct column contexts and invokes ParallelFor with the configured executor. The two blocking writer callers never run inside that executor, avoiding nested executor deadlock. Row-group close serializes column writers in schema order. Pending column work is bounded by the two synchronous outside writers; the existing three ledger buffers/backpressure remain unchanged.

Pinned correctness passed 80 baseline/candidate journal fixture comparisons in normal and ASan/UBSan builds; original full-table/stream byte equivalence passed on Arrow15. Fixtures cover page/write-batch/block/group boundaries, late vocabulary, high-cardinality UTF8 dictionary fallback, mixed/all/no nulls, concurrent writers, malformed tables and append errors. Binding checks cover the two assigned single-market correctness scenarios and all five hetero-batch markets, including native buffers, empty controls and staged-output cleanup. The shared controls runner accepted 14 runs across all seven allowed units, with exact bytes, schemas, ordered values, actual native execution and unchanged gates. See [pinned-validation.json](pinned-validation.json) and [controls-validation.json](controls-validation.json). Sanitizers instrument our sources, not the prebuilt Arrow libraries.

Measurement contract: context colima-agenthon, Linux amd64 on a Mac ARM64 host, four CPUs, 16GiB memory+swap, network none. The whole build/check/control/diagnostic-build/primary-series/diagnostic-series chain held the shared exclusive slot. Baseline FROM tags were verified before and after build; subsequent runs used immutable IDs. Python 3.11.17, numpy 1.26.4, pandas 1.5.3, Arrow 15.0.2 and scipy 1.17.1 were audited. The candidate image is `sha256:8be4efb0eff25eeb35fb63ea33b370919ca70e55a2494232c005429056429941`; baseline is `sha256:0bace6e254c0ecf48b5a598e6001ff79fda062f1de81bf003d151ae51510b36c`. Exact runtime extension binaries/digests are retained in `evidence/runtime-audit`.

The primary series contains 48 accepted runs: 8 excluded warmups and 40 timed runs (five AB/BA pairs per unit). Separate diagnostics contain exactly 192 samples: 4 units × 4 modes × (2 excluded warmups + 10 timed samples), or 160 timed samples and 32 warmups. Each uses its predeclared AB/BA order. All outputs are byte-equal to the real baseline journals. No extra benchmark was run after viewing results. No production source changed after pinned correctness or during timing.

All diagnostic samples, setup/write/close/CPU clocks, pair identities and hashes are in [component-results.json](component-results.json); engine/idle/callback counters are in [pipeline-medians.json](pipeline-medians.json). Raw logs, commands, binaries, validated journal paths and pinned sources are in `evidence`. The storage manifest records independently checked equal-byte hardlinks. Diagnostic outputs originally compared and hashed after each timed region are retained as hardlinks to those identical validated control bytes; uncompressed IPC input files are preserved with their originally recorded pinned-serializer hashes. This storage-only preservation repeats no simulation or measurement.

Interpretation: reducing producer backpressure and the ledger callback wall is useful, but the measured standalone encoding never reaches 2×. The overlap gain falls to 0.35–8.20% when the two files share their bounded pool. This is consistent with shared-worker contention and serial close/conversion costs limiting parallel benefit; it is an inference from the clocks, not a measured per-column CPU breakdown. Ledger final close/join does not consistently get faster, and the pool does not accelerate serial lifecycle construction, Python/runtime startup or disk publication. Pipeline clocks and the complete-container clock measure different scopes, so the larger instrumented pipeline percentages do not override the primary result.

Limitations: five pairs provide a small local sample, not statistical assurance or official timing hardware. The horizon container result is particularly weak (0.41%, 3/5 faster). One market caller is assumed for the four-active-thread claim; unrelated concurrent callers add outside threads. Buffered trace groups can raise memory use. Pool submission/shutdown infrastructure faults were not injected. The hypothesis gives moderate local improvement on some scenarios and misses the radical-speedup target. This isolated experiment is not adopted.

Reproduction: [recipe.sh](recipe.sh) runs individual authorized steps; [phase2.py](phase2.py) chains them under `CAMPAIGN/docker_slot.py`. It must be dispatched by the coordinator with the frozen assigned scenario plan and audited cached builder. Primary timing uses the unchanged shared run_focused.py and production extension. Instrumentation is confined to disposable diagnostic source copies. [host-validation.json](host-validation.json) remains preliminary host Arrow25 evidence; pinned evidence supersedes its library-specific differences. No sealed data, scorer changes or dependency changes are involved.
