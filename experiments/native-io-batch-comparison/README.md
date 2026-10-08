# Native I/O and batch experiment comparison

Executive summary: both experiments preserve the canonical journals, but neither
establishes a general end-to-end speedup on this local emulated host. Streaming
hashes show small, inconsistent single-market changes. The combined batch and
the independent-market worker pool regress. Production code is unchanged; only reports and measurement data are archived in develop.

Results are medians of five measured repeats per mode, after one excluded warmup.
Each experiment uses fresh baseline runs and alternating baseline/candidate pairs.
The primary clock is the complete Docker container lifetime. All outliers are
retained. These are local non-rankable ARM64-host / linux-amd64-container results.

## A: streaming hashes plus the shared batch worker implementation

The single-market cases exercise hashing; the heterogeneous batch also uses two
workers. The batch implementation is the exact commit transferred from B.

| Unit | Baseline seconds | Candidate seconds | Time change |
|---|---:|---:|---:|
| t3-s001-price-time-priority | 0.326660 | 0.324441 | -0.7% |
| t3-mr-deep-book-state-size | 0.552394 | 0.544645 | -1.4% |
| t3-mp05-cancel-churn-newest | 0.447200 | 0.460976 | +3.1% |
| t3-gbatch-hetero-mix | 0.361630 | 0.484835 | +34.1% |

## B: bounded native batch workers

| Unit | Baseline seconds | Workers 1 seconds | Workers 2 seconds | Workers 2 time change |
|---|---:|---:|---:|---:|
| t3-gbatch-homog-4 | 0.325511 | 0.370446 | 0.496246 | +52.5% |
| t3-gbatch-homog-8 | 0.414842 | 0.478139 | 0.535289 | +29.0% |
| t3-gbatch-hetero-mix | 0.358755 | 0.428321 | 0.439508 | +22.5% |
| t3-gbatch-varsize | 0.341878 | 0.367066 | 0.407545 | +19.2% |

The worker1 control adds 7.4–19.4% to the full container median; the overhead
includes the changed wrapper, startup and publication, and cannot be attributed
solely to pool scheduling. The additional worker2 regression has no component
profile sufficient to establish one specific cause.

## Correctness and retained evidence

All 152 scheduled records were accepted, including 100 timed samples and 20
excluded warmups; A also ran four separate untimed memory diagnostics. B checked
all six public batches in three modes and native repeated-seed, reordered and
isolated outputs, plus fallback and error handling. A checked complete Parquet
footers, independent stream contexts, write/close failures and read-only execution.

The orchestration audit independently rehashed 1,254 retained journals and
confirmed the unchanged book, simulation, RNG, agent and mapping source hashes.
Only reports and measurement data are archived in the development branch. Neither implementation is adopted. JSON records are preserved byte-for-byte as completion snapshots; their development-state fields describe the state before this report-only archive.

[Comparison data](comparison.json) retains the samples and fixed identities.
[Independent audit](orchestration-audit.json) retains source and journal checks.
[Experiment A report](../stream-hash/README.md)
and [experiment B report](../native-batch/README.md)
retain individual build, validation, memory and timing evidence.

The two experiments ran separate paired series. Direct subtraction of their
heterogeneous-batch candidate medians does not isolate the effect of hashing.
Streaming SHA256 still performs hash computation; write-plus-hash is the correct
secondary phase. Concurrent per-market phase sums are not batch wall time.

Final experiment commits: A `a56a293f949c0d12fbbb6475ec1de0a1e7a2deac`; B `546d7f0e9ceba4e17a39a9891d7e2be72f85d294`. At experiment completion, both worktrees were clean and development was at `7a5abca889c1fdd77e01edfa9f85762becc1f17b`. The subsequent archive commit changes only `experiments/` documentation and data.
