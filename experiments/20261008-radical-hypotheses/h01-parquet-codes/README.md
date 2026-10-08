Executive summary: the direct code-to-Parquet writer preserves both journals exactly and passes all selected developer gates. Full-container median time reductions are t3-gb-mega-throughput: +5.34%, t3-gb-pop-horizon-scale: -1.45%, t3-mr-deep-book-state-size: -26.07%, t3-s001-price-time-priority: -0.49%. One improvement and three regressions do not establish a general writer speedup. These are local emulated measurements with five retained pairs per unit, not official timing. No production adoption occurred.

# H01 — direct code-to-Parquet writer

Only `baselines/native/pqwrite.cpp` changes in simulation sources. The base is
`a7fb6c36d88395e49d40bc3b71e6dc79b2099bc9`; the isolated branch is
`codex/exp-20261008-radical-h01-parquet-codes`. All experiment artifacts reside
in this `expirements/20261008-radical-hypotheses/h01-parquet-codes` directory.

Trace `msg_type`, trace `side` and ledger `msg_type` uint8 codes now select borrowed
`parquet::ByteArray` views into static vocabulary strings. The writer holds only
1024 views at a time and never builds per-row UTF8 offsets or repeated string data.
Parquet still performs dictionary insertion in original encounter order; this
retains evolving page bit widths, dictionary order and page-limit decisions.
Numeric arrays retain the original buffers and validity bitmaps and use typed
`WriteBatch` / `WriteBatchSpaced`, matching Arrow's numeric write path. One reusable
row-group definition-level buffer supplies optional-column validity. Row groups
stay at 1,048,576 rows; writer batches stay at 1024. Empty journals take the original
Arrow table path, preserving empty-array validation behavior as well as bytes.

The final fields remain plain Arrow `string`. Schema conversion delegates to
`ToParquetSchema`; schema metadata uses the same IPC serialization, base64 and
append order as Arrow 15's `GetSchemaMetadata`. Pandas metadata literals,
statistics, Snappy, Parquet 2.6, data pages V1 and all numeric flags remain pinned.
Existing concurrent journal writing in `module.cpp` is untouched; no column
parallelism or pipeline is added.

## Why the first dictionary-array approach was discarded

Opening an Arrow writer with a plain string schema and then passing internal
dictionary arrays preserved schema metadata. It did not preserve all file bytes:
in the host diagnostic with 65,535 rows and late vocabulary expansion, the first
data page contained bit width 3 rather than baseline bit width 1. All values and
column metadata matched, but one byte differed. The final direct `ByteArrayWriter`
path lets the dictionary grow progressively and passed this adversarial case.
This was corrected before any Docker measurement.

The behavior is grounded in the official pinned Arrow sources:
[writer and schema metadata](https://github.com/apache/arrow/blob/apache-arrow-15.0.2/cpp/src/parquet/arrow/writer.cc),
[column writer](https://github.com/apache/arrow/blob/apache-arrow-15.0.2/cpp/src/parquet/column_writer.cc),
[dictionary encoder](https://github.com/apache/arrow/blob/apache-arrow-15.0.2/cpp/src/parquet/encoding.cc).
Downloaded inspection copies are local evidence only, under `evidence/arrow15/`.

## Fixed workload selection

| Role | Unit | Reason |
| --- | --- | --- |
| Timing | t3-gb-mega-throughput | Large journals expose serialization costs. |
| Timing | t3-gb-pop-horizon-scale | Population and horizon scaling creates sustained message output. |
| Timing | t3-mr-deep-book-state-size | Large simulation state tests whether write savings affect the full run. |
| Timing | t3-s001-price-time-priority | Small workload exposes fixed writer overhead or regressions. |
| Correctness only | t3-gbatch-hetero-mix | Independent heterogeneous markets cover varying vocabulary and null usage. |

Only these selected units may run. The materialized source corpus is read-only at
`/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/units`.
No scenario, card, trace or scoring code is modified or copied into production.

## Writer checks

`run_checks.py` retrieves the base writer from Git and includes both real writers
in separate namespaces. Vocabulary names are extracted from the actual engine.
`check_writer.cpp` writes both journals for 17 row counts and three patterns:
0, 1, 2, 13, 1023/1024/1025, 65535/65536/65537, 262143/262144/262145,
1048575/1048576/1048577, and 2097153 rows. Patterns cover seeded mixed codes,
reversed first dictionary insertion with delayed new types, and new vocabulary
appearing near the first row-group boundary. Nullable fields cover mixed, absent
and all-null validity. All six trace types, both sides and 13 ledger types occur.
Candidate guards reject invalid codes 13 and 255 before accessing the writer.

The C++ test checks full-file bytes and equal empty-array exception behavior.
Python additionally compares schema including metadata, ordered values, footer
key/value metadata and plain (non-dictionary) Arrow field types. Normal and
AddressSanitizer/UndefinedBehaviorSanitizer runs use identical fixtures.

```sh
# Run from this worktree; the shared environment is used read-only.
'/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python' \
  expirements/20261008-radical-hypotheses/h01-parquet-codes/run_checks.py \
  --out expirements/20261008-radical-hypotheses/h01-parquet-codes/evidence/host-final
'/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python' \
  expirements/20261008-radical-hypotheses/h01-parquet-codes/run_checks.py --sanitize \
  --out expirements/20261008-radical-hypotheses/h01-parquet-codes/evidence/host-sanitized
```

Host runtime is Python 3.13.3, Arrow 25.0.1, macOS ARM64. Host headers require
C++20; pinned Arrow 15 uses the production C++17 setting. Host results are
correctness diagnostics and do not substitute for pinned validation. Raw binaries,
Parquet files and logs are ignored locally under `evidence/`; readiness links the
compact JSON evidence and hashes.

## Phase 2 recipe

`Dockerfile` mirrors the coordinator's shared overlay: compile the native extension
in a builder derived from the same verified pinned baseline, then copy only that
extension into an image derived from that baseline. Python 3.11, Arrow 15.0.2 and
`baselines/build_native.py` are unchanged. The coordinator supplies the immutable
baseline image and build dispatch. Every Docker operation runs inside the common
`docker_slot.py` lock; context, VM lifecycle and global Docker configuration stay
unchanged.

1. Prepare baseline test sources on the host with `run_checks.py --prepare-only
   --out <this-directory>/evidence/pinned`.
2. Build the builder target and candidate using the shared overlay recipe and
   coordinator's verified baseline tag. Capture both immutable image IDs.
3. Mount this worktree read-only and only `evidence/pinned` writable; run
   `run_checks.py --prepared --require-pinned --out /evidence` in the builder.
4. Use the unchanged coordinator `run_focused.py --controls-only` to verify all
   five units, both journals, actual native provenance and shared developer gates.
5. Run its fixed timing series on the four timing units: fresh baseline and
   candidate, one excluded warmup each, then five AB/BA pairs. Keep every sample.

All runs use linux/amd64, explicit colima-agenthon, 4 CPUs, 16g memory and swap,
network none. Primary time is Docker FinishedAt minus StartedAt. Secondary core,
finalization, write and hash phases are retained. Report
`100*(1-median(candidate)/median(baseline))`: positive is faster. Failed correctness
suppresses any speedup claim. No repeats or tuning after measured results.

| Unit | Full run reduction (%) |
| --- | --- |
| t3-gb-mega-throughput | +5.34 |
| t3-gb-pop-horizon-scale | -1.45 |
| t3-mr-deep-book-state-size | -26.07 |
| t3-s001-price-time-priority | -0.49 |

`result.json` will be created only from actual phase-2 evidence. This experiment is
non-rankable and is neither merged, pushed nor adopted into production.

## Completed phase 2a: pinned correctness

The implementation sources stayed byte-for-byte unchanged from phase 1.
The image build used commit `0ff61563bde3ab0fe8a1392334ec5c3051fa4852` and the
coordinator baseline `sha256:51fcf856e5c5ee4b33a6f43e059bf23035eeba44e2cb2b96692851696179e4c6`.
Candidate: `sha256:7a21a621eb5fa9aa82b03039da00242b9ca1ad6f825a6134f59c4ffb974387c6`.

`phase2a.py` ran as one subprocess under the shared Docker slot. It verified the
baseline tag before and after builds, builder native-source hashes, equality of
the built and installed extension, and identical baseline/candidate dependency
versions. Both use Python 3.11.17, numpy 1.26.4, pandas 1.5.3, Arrow 15.0.2 and
scipy 1.17.1 on linux/amd64. Every runtime probe used the fixed resource limits.

The C++17 pinned writer comparison passed 102 file pairs with exact bytes, plain
string schema, pandas/Arrow metadata and ordered values. No pinned failure or
implementation repair occurred. The five selected unit controls then passed
10 fresh baseline/candidate launches and 18 paired journal-file comparisons.
Native execution was confirmed for all 18 market executions, including five
independent markets on each side of the heterogeneous batch. The unchanged
shared developer gates accepted all runs.

Compact evidence pointers and SHA256 hashes are committed in
[phase2-readiness.json](phase2-readiness.json). All build logs, pinned probe files,
runtime audits and complete controls are retained under
`evidence/phase2a-attempt01/`. The controls' incidental elapsed times are not a
paired timing series and are not used to infer performance. The timing series was still pending at phase-2a completion; its final results are recorded below.

## Completed phase 2b: one fixed timing series

The coordinator runner completed exactly 48 accepted launches: eight excluded warmups and 40 timed samples. Each unit used one fresh baseline and candidate warmup, then five pairs in AB, BA, AB, BA, AB order. A is baseline and B is candidate. Every launch passed both-journal correctness, shared developer gates and actual-native checks. All outliers are retained; no extra repeats, tuning or source edits occurred.

Primary time is Docker FinishedAt minus StartedAt. Positive reduction means a faster full run; negative means slower. Values below are seconds rounded to six decimals; the standard [result.json](result.json) and raw run records preserve full numeric precision. Measurement commit: `faf294fd03ddf89e12bd119955604176eb8a04d6`. Image identities remain those audited in phase 2a.

| Unit | Baseline median (s) | Candidate median (s) | Full run reduction (%) | Candidate faster pairs |
| --- | ---: | ---: | ---: | ---: |
| t3-gb-mega-throughput | 1.666175 | 1.577160 | +5.34 | 3/5 |
| t3-gb-pop-horizon-scale | 1.195908 | 1.213226 | -1.45 | 2/5 |
| t3-mr-deep-book-state-size | 0.731699 | 0.922489 | -26.07 | 0/5 |
| t3-s001-price-time-priority | 0.396766 | 0.398717 | -0.49 | 4/5 |

The targeted writer phase does not show a consistent benefit on the large units. On mega-throughput, its median rises from 0.558895 s to 0.570756 s while simulation plus trace finalization falls from 0.634317 s to 0.561458 s; the full-container improvement cannot be attributed to a faster writer from these measurements. The candidate is slower in all five deep-book pairs. On s001, it wins four pairs but still has a slightly worse ratio of side medians; the prespecified primary metric is retained. These observations support preserving correctness evidence and declining a general performance claim.

### Every primary-clock sample

| Unit | Side | Timed samples in pair-index order (s) |
| --- | --- | --- |
| t3-gb-mega-throughput | baseline | 1.896762, 1.666175, 1.447228, 1.487119, 1.702990 |
| t3-gb-mega-throughput | candidate | 1.625594, 1.641157, 1.539914, 1.500170, 1.577160 |
| t3-gb-pop-horizon-scale | baseline | 1.883874, 1.643193, 1.077299, 1.127359, 1.195908 |
| t3-gb-pop-horizon-scale | candidate | 2.343157, 1.296670, 1.211243, 1.058557, 1.213226 |
| t3-mr-deep-book-state-size | baseline | 0.758996, 0.668743, 0.731699, 0.772604, 0.714444 |
| t3-mr-deep-book-state-size | candidate | 0.793673, 0.922489, 0.971237, 0.786247, 0.995107 |
| t3-s001-price-time-priority | baseline | 0.396766, 0.389231, 0.395592, 0.556023, 0.740956 |
| t3-s001-price-time-priority | candidate | 0.329263, 0.327332, 0.398717, 0.475070, 0.509560 |

### Excluded warmups

| Unit | Baseline (s) | Candidate (s) |
| --- | ---: | ---: |
| t3-gb-mega-throughput | 1.505943 | 1.708177 |
| t3-gb-pop-horizon-scale | 1.323189 | 1.117591 |
| t3-mr-deep-book-state-size | 0.884438 | 0.782067 |
| t3-s001-price-time-priority | 0.654439 | 0.581262 |

### Phase medians and every phase sample

These adapter-reported phases are secondary diagnostics. `simulation_and_trace_finalize` includes both native simulation and trace finalization; the runtime does not expose an independent finalization duration. `parquet_write` is concurrent writing of the two journals, and `hashing` measures subsequent hashing. Phases exclude container startup and do not sum to the primary Docker lifetime. No matcher-only or independent-finalization improvement is inferred.

| Unit | Side | Phase | Median (s) | All five samples (s) |
| --- | --- | --- | ---: | --- |
| t3-gb-mega-throughput | baseline | configuration | 0.002604 | 0.002604, 0.003275, 0.002387, 0.002254, 0.003571 |
| t3-gb-mega-throughput | baseline | hashing | 0.143986 | 0.277205, 0.137101, 0.139428, 0.163515, 0.143986 |
| t3-gb-mega-throughput | baseline | parquet_write | 0.558895 | 0.585736, 0.589672, 0.513682, 0.478596, 0.558895 |
| t3-gb-mega-throughput | baseline | simulation_and_trace_finalize | 0.634317 | 0.737784, 0.634317, 0.528176, 0.559011, 0.650532 |
| t3-gb-mega-throughput | candidate | configuration | 0.002431 | 0.002695, 0.002431, 0.002331, 0.003085, 0.002254 |
| t3-gb-mega-throughput | candidate | hashing | 0.151224 | 0.151224, 0.155455, 0.162714, 0.141735, 0.144492 |
| t3-gb-mega-throughput | candidate | parquet_write | 0.570756 | 0.522015, 0.632479, 0.570756, 0.506416, 0.591563 |
| t3-gb-mega-throughput | candidate | simulation_and_trace_finalize | 0.561458 | 0.671843, 0.567453, 0.530390, 0.538978, 0.561458 |
| t3-gb-pop-horizon-scale | baseline | configuration | 0.003448 | 0.007035, 0.003448, 0.003923, 0.002397, 0.002946 |
| t3-gb-pop-horizon-scale | baseline | hashing | 0.105867 | 0.106218, 0.087184, 0.105867, 0.111344, 0.098256 |
| t3-gb-pop-horizon-scale | baseline | parquet_write | 0.439883 | 0.453738, 0.392517, 0.391777, 0.439883, 0.467016 |
| t3-gb-pop-horizon-scale | baseline | simulation_and_trace_finalize | 0.340490 | 0.576748, 0.497849, 0.293284, 0.298556, 0.340490 |
| t3-gb-pop-horizon-scale | candidate | configuration | 0.002691 | 0.005503, 0.010192, 0.002305, 0.002691, 0.002550 |
| t3-gb-pop-horizon-scale | candidate | hashing | 0.111374 | 0.145329, 0.111374, 0.148894, 0.096409, 0.108711 |
| t3-gb-pop-horizon-scale | candidate | parquet_write | 0.446398 | 0.587375, 0.446398, 0.492906, 0.377292, 0.436008 |
| t3-gb-pop-horizon-scale | candidate | simulation_and_trace_finalize | 0.388525 | 0.650535, 0.640329, 0.310967, 0.303419, 0.388525 |
| t3-mr-deep-book-state-size | baseline | configuration | 0.003007 | 0.003007, 0.002410, 0.003374, 0.002338, 0.003219 |
| t3-mr-deep-book-state-size | baseline | hashing | 0.046677 | 0.041606, 0.039610, 0.052010, 0.052294, 0.046677 |
| t3-mr-deep-book-state-size | baseline | parquet_write | 0.263162 | 0.265182, 0.213518, 0.263162, 0.297833, 0.237627 |
| t3-mr-deep-book-state-size | baseline | simulation_and_trace_finalize | 0.152265 | 0.161530, 0.142378, 0.138945, 0.152265, 0.164900 |
| t3-mr-deep-book-state-size | candidate | configuration | 0.003719 | 0.002816, 0.003719, 0.005381, 0.004547, 0.003635 |
| t3-mr-deep-book-state-size | candidate | hashing | 0.041710 | 0.038898, 0.041710, 0.045928, 0.034284, 0.058334 |
| t3-mr-deep-book-state-size | candidate | parquet_write | 0.285520 | 0.210933, 0.324029, 0.285520, 0.256302, 0.433104 |
| t3-mr-deep-book-state-size | candidate | simulation_and_trace_finalize | 0.180832 | 0.224531, 0.178803, 0.293330, 0.180832, 0.179045 |
| t3-s001-price-time-priority | baseline | configuration | 0.003113 | 0.002935, 0.002738, 0.003483, 0.003113, 0.004699 |
| t3-s001-price-time-priority | baseline | hashing | 0.003382 | 0.004311, 0.003375, 0.003294, 0.003382, 0.010053 |
| t3-s001-price-time-priority | baseline | parquet_write | 0.127734 | 0.127734, 0.087295, 0.102909, 0.207041, 0.260256 |
| t3-s001-price-time-priority | baseline | simulation_and_trace_finalize | 0.004110 | 0.003504, 0.004110, 0.003555, 0.005068, 0.005085 |
| t3-s001-price-time-priority | candidate | configuration | 0.003277 | 0.002180, 0.003365, 0.003277, 0.003253, 0.005178 |
| t3-s001-price-time-priority | candidate | hashing | 0.003483 | 0.003217, 0.003396, 0.003665, 0.005781, 0.003483 |
| t3-s001-price-time-priority | candidate | parquet_write | 0.084053 | 0.069686, 0.084053, 0.097423, 0.072307, 0.136062 |
| t3-s001-price-time-priority | candidate | simulation_and_trace_finalize | 0.003837 | 0.003444, 0.003837, 0.003667, 0.006604, 0.003923 |

### Evidence and practical limits

Pinned Arrow 15 writer probes and all five pre-timing controls remain linked by [phase2-readiness.json](phase2-readiness.json). [completion.json](completion.json) links and hashes the final series; [result.json](result.json) is an exact copy of the standard coordinator output. The complete timing summary, all warmup/timing records, phase profiles, raw and retained journals, declarations and checker outputs are retained under `evidence/phase2b-timing/`; large evidence remains ignored by Git.

Runs were serialized under the shared Docker slot using explicit colima-agenthon, linux/amd64, 4 CPUs, 16g memory and swap, and network none. The host is Mac ARM64 with emulated Linux amd64 containers. These local `rankable:false` measurements are not official timing hardware and do not establish performance on the official fleet. Five pairs and a small selected workload set limit generalization; all observations are preserved for review. The candidate is not merged, pushed or adopted into production.
