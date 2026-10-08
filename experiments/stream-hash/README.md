Executive summary: streaming checksums preserve both complete journals and
avoid reopening them on the native path. All correctness checks passed, but the
three single-market measurements are mixed and noisy. The combined heterogeneous
batch took 34.1% longer in median and was slower in all five paired samples.
These local results do not justify adopting the combined change.

Archive scope: this directory contains reports and measured data only. Implementation, runners, tests and Docker recipes remain on `codex/exp-20261008-stream-hash-batch` at `a56a293f949c0d12fbbb6475ec1de0a1e7a2deac`. Commands below are historical recipes for that experimental checkout; the referenced scripts are not included in this archive. Production code is unchanged. JSON records are preserved byte-for-byte as experiment-completion snapshots.

Experiment A combines OpenSSL streaming SHA256 with the exact shared native
batch implementation from `11a9a6c77184d3335932a026c1dee93bea8e3ad6`. Single
markets exercise hashing alone; the batch combines hashing, workers 2 and the
shared publication behavior. No workers-1 timing control was scheduled, so the
batch result cannot separate those contributions.

The fixed policy ran four requested public cases, each with one excluded warmup
per mode followed by five paired repeats in AB, BA, AB, BA, AB order. Every
baseline sample was launched afresh. All 48 scheduled runs (8 warmups and 40
timed samples) passed developer gates, actual-native audits, schemas, ordered
values, direct byte comparisons and independent hashes of both journals. There
were 96 market outputs and 192 complete-journal digest audits. No samples were
added or discarded beyond the predeclared warmups, and code was not tuned after
timing. Four further memory diagnostics were excluded from timing.

The primary metric is Docker `FinishedAt - StartedAt`, with one median per mode.
A positive candidate time change means a slower candidate. Individual pairs on
the single markets vary in both directions, so these small median changes do not
establish a consistent gain.

| Case | Baseline median (s) | Candidate median (s) | Candidate time change |
|---|---:|---:|---:|
| Price/time priority | 0.326660 | 0.324441 | -0.68% |
| Deep book | 0.552394 | 0.544645 | -1.40% |
| Cancel churn | 0.447200 | 0.460976 | +3.08% |
| Hetero batch, workers 2 | 0.361630 | 0.484835 | +34.07% |

Secondary adapter data uses `parquet_write + hashing`, including the native
hashing work now inside the write phase. The following values are medians of
the sum across markets. Baseline hashing includes small metadata work, and
parallel market phases overlap. The batch sum is therefore not a whole-batch
elapsed-time metric and cannot replace the primary Docker clock.

| Case | Baseline write + hash (s) | Candidate write + hash (s) |
|---|---:|---:|
| Price/time priority | 0.084705 | 0.088588 |
| Deep book | 0.207085 | 0.192408 |
| Cancel churn | 0.171424 | 0.178513 |
| Hetero batch, workers 2 | 0.129188 | 0.422261 |

One untimed diagnostic per mode measured the cgroup high-water mark for deep
book and hetero. The same small parent probe remains alive after the simulator
exits and is included in each reading. Cgroup file cache is included; child RSS
is separately retained and must not be added to these peaks.

| Diagnostic | Baseline cgroup peak (MiB) | Candidate cgroup peak (MiB) |
|---|---:|---:|
| Deep book | 191.14 | 191.91 |
| Hetero batch, workers 2 | 52.28 | 61.55 |

These are non-rankable local host measurements: macOS 15.7.4 arm64, an aarch64
Docker server in `colima-agenthon`, and `linux/amd64` workload images. All
containers ran sequentially with four CPUs, 16 GiB memory, 16 GiB memory-swap
and no network. Five paired samples on this host do not represent official
Final hardware or timing. No historical measurements or experiment-B samples
were used to select or change this policy.

`result.json` contains all five samples, paired ratios, per-market phase samples,
immutable image IDs, source hashes and memory readings. Complete evidence lives
under `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-native-io-batch/worktrees/stream-hash-batch/out/stream-hash-batch-timing-20261008`; `evidence-sha256.json` inventories
1,069 retained files including raw and retained journals, every run record,
stdout/stderr, inputs and the frozen memory probe. Docker State timestamps and
all checks remain available for each warmup and repeat.

The base source is `7a5abca889c1fdd77e01edfa9f85762becc1f17b`; its immutable
runtime image is
`sha256:e7f01b18f284f8ff9a5e0fb5591a80dfdaa9e051f76e7076e07ae82293aedd89`.
The source checksums and implementation commits are recorded in `result.json`
and the orchestration READY/DONE files. The measured combined image is
`sha256:5692ca0d3619cc5ad71f9e932d31410f5ddafbb84f48543621287f78e4a9d4c9`.
Host tests use Arrow 25.0.1 and OpenSSL 3.6.4; they verify correctness,
not evaluation-runtime equivalence. The container recipe retains Arrow 15.0.2
and links OpenSSL through libcrypto. Docker checks confirmed CPython 3.11.17,
Arrow 15.0.2 and OpenSSL 3.5.7, with no compiler or OpenSSL headers in the final
image. The native binary is identical in the hash-only and combined images; all
native build layers were cache hits for the second build.

`HashOutputStream` hashes a write only after the underlying stream accepts the
whole chunk. A partial write, flush failure or close failure permanently prevents
digest retrieval. Every stream has its own EVP context, including the two
concurrent Parquet writers. `run_write` appends two digest strings to its previous
three statistics. Output failures raise `OSError`, which propagates in auto and
native modes; engine failures retain the existing fallback behavior. The Python
fallback and its file-reading checksums are unchanged. The profile reports zero
standalone hashing time because hashing now belongs to `parquet_write`, and
records subsequent metadata work as `metadata_finalize`.

The 72 combined host tests passed. Writer checks cover empty streams, SHA256
block boundaries and larger chunks,
independent concurrent streams, injected partial-write/flush/close failures,
abort, file-open failure, complete Parquet footer hashes and byte equality with
direct writes by the same host libparquet. Python adapter checks prohibit journal
rereads and require failures before success metadata is emitted.

## Historical build and execution recipe

In the experimental checkout, after the orchestrator grants the Docker slot, use the repository root as build
context and run the whole Docker phase under the shared `docker_slot.py` wrapper.
The wrapper's Python interpreter is the original repository's `.venv/bin/python`.
Verify that the local build alias resolves to the immutable baseline before
building. Dockerfile `FROM` needs the local tag rather than a daemon image ID.
The combined build command is:

```sh
test "$(docker --context colima-agenthon image inspect --format '{{.Id}}' track3-native:20261008)" = \
  sha256:e7f01b18f284f8ff9a5e0fb5591a80dfdaa9e051f76e7076e07ae82293aedd89 && \
docker --context colima-agenthon build --platform linux/amd64 \
  --build-arg BASE_IMAGE=track3-native:20261008 \
  -f experiments/stream-hash/Dockerfile -t track3-stream-hash-batch:20261008 .
```

Resolve the candidate's image ID before correctness checks or measurement. Run
the small standalone correctness check separately from timed samples, mounting
an evidence directory at `/audit-output`:

```sh
docker --context colima-agenthon run --rm --platform linux/amd64 \
  --cpus 4 --memory 16g --memory-swap 16g --network none \
  -v "$EVIDENCE_DIR:/audit-output" "$CANDIDATE_IMAGE_ID" \
  python /opt/native-tests/check_stream_hash.py \
  /opt/native-tests/hash-stream-test /audit-output
```

The checker saves native stdout/stderr, both synthetic Parquet files and an
independent SHA256 report. Correctness checks on price/time priority, deep book
and cancel churn confirmed both complete journals match the baseline by direct
byte comparison and independent SHA256, with developer gates passing. Hetero
batch workers 1 and 2 also match baseline journals. The shared batch helper
checked 35 market outputs with repeated, reordered and isolated seeds; these
are correctness diagnostics rather than performance repeats. Mixed fallback
runs Python on the caller thread after native workers join. Four real native
writer failures remain `OSError` in auto and strict mode, and preserve previously
published batch files. Single native and workers-2 batch runs passed with
read-only rootfs and uid 65534.

Every measurement independently read complete files after container exit.
Containers ran sequentially with one excluded warmup per mode and five
alternating baseline/candidate repeats.
Docker `FinishedAt - StartedAt` is the primary metric. All host and local Docker
timing is non-rankable. Use the existing differential harness and imported shared
scoring gates. No public unit, reference, sealed data, engine, book or RNG code is
part of this change; merging and pushing are outside this experiment.

`/opt/native-tests/check_module_hash.py PUBLIC_SCENARIO_JSON OUTPUT_DIR` checks
the real extension's two returned
digests and both writers' file-open and `/dev/full` failures. Injected close errors
are covered by the stream test. All checkers are untimed diagnostics.

`verify_docker.py` implements the initial hash correctness phase and
`verify_combined.py` builds and checks the combined stage. Run either complete
script through the shared exclusive slot wrapper. Evidence is retained under
`out/stream-hash-docker-20261008` and `out/stream-hash-combined-docker-20261008`;
`docker-verification.json` records immutable image IDs, source hashes and the
check inventory. The initial hash-only image came from recipe commit
`78a7b42` before the batch cherry-pick; the current recipe includes batch.

The executed timing runner is `run_timing.py` (commit `ccb57b06`). Without
`--execute` it prints the
plan and makes no Docker calls. It reuses the differential harness, adds strict
native launch settings and audits actual engine labels, direct bytes and both
digests. It schedules only the three assigned single markets and hetero batch,
with candidate workers 2 on the batch and no worker option on single commands.
The original immutable baseline is launched afresh for every pair. Warmups are
excluded; five timed pairs alternate AB/BA per unit, without detailed profiling.
Each run retains State timestamps, outputs, checks and per-market write plus
hash phases. Concurrent market phases overlap and are secondary adapter data.
After timing, four untimed memory diagnostics cover deep book and hetero in both
modes. The exact memory probe is saved, and unavailable cgroup readings stay
null. The optional workers-1 timing control is not scheduled.

The recorded execution command used the whole-phase shared slot wrapper:

```sh
"/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python" \
  "/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-native-io-batch/docker_slot.py" -- \
  "/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python" \
  experiments/stream-hash/run_timing.py --execute \
  --out out/stream-hash-batch-timing-20261008 \
  --memory-probe "/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-native-io-batch/memory_probe.py"
```

This command completed once with the fixed policy. `DONE-stream-hash.json`
records the final report commit and evidence. Both features remain in the
experimental branch; no merge or push was performed.
