Executive summary: the indexed FIFO is correct on all checked outputs, but the four assigned units show mixed complete-container timing changes (+2.25%, +6.34%, -3.06%, -5.64%). There is no consistent measured improvement. The implementation remains experimental, with no production adoption. All five pairs, warmups, outliers and secondary diagnostics are retained.

## Completed paired comparison

Positive change means slower complete Docker time; negative means faster. Times are medians of five retained samples, excluding one warmup per side. “Wins” counts the candidate beating the fresh baseline within a pair.

| Public unit | Baseline seconds | Candidate seconds | Time change | Candidate wins | Outcome |
| --- | ---: | ---: | ---: | ---: | --- |
| `t3-mp05-cancel-churn-newest` | 0.547049363 | 0.559365662 | +2.25% | 2/5 | Correct, slower median |
| `t3-s012-partial-fill-cancel-race` | 0.458291811 | 0.487354082 | +6.34% | 2/5 | Correct, slower median |
| `t3-mp02-stp-oldest-baseline` | 0.340825041 | 0.330397936 | -3.06% | 2/5 | Correct, faster median |
| `t3-partialfill-atomicity` | 0.388270332 | 0.366358153 | -5.64% | 3/5 | Correct, faster median |

The first two units are correct-but-slower. The other two have lower candidate medians, with only 2/5 and 3/5 paired wins respectively. These mixed results do not support a general performance win. No threshold tuning, extra repeats or selective reruns followed timing.

## Secondary phase medians

The native phase is `simulation_and_trace_finalize`; it includes trace finalization and is not matcher-only time. Each cell shows baseline → candidate seconds. Complete Docker time above remains the primary outcome.

| Public unit | Simulation + trace finalize | Parquet write | Hashing |
| --- | ---: | ---: | ---: |
| `t3-mp05-cancel-churn-newest` | 0.087930844 → 0.093922819 | 0.177370541 → 0.184612021 | 0.030790682 → 0.031037243 |
| `t3-s012-partial-fill-cancel-race` | 0.070761508 → 0.065974196 | 0.147777955 → 0.151401283 | 0.023299879 → 0.025342905 |
| `t3-mp02-stp-oldest-baseline` | 0.025487356 → 0.028557535 | 0.086537769 → 0.084705248 | 0.011537890 → 0.011448828 |
| `t3-partialfill-atomicity` | 0.034698571 → 0.029681619 | 0.084364260 → 0.103823824 | 0.009646619 → 0.009934339 |

The full result preserves every phase sample, including configuration, all five complete-container samples per side, paired differences, wins and reported process peak values. Reported process peaks are secondary diagnostics, not per-price-level allocator measurements.

## Pinned correctness and provenance

The pinned Linux builder passes the existing 80,000-mutation reference test and the focused FIFO test. Both production and candidate images assert Python 3.11.17, Arrow 15.0.2, native extension loading and native configuration eligibility for all four units. All 48 retained outputs ran the actual native engine. All 192 imported developer-gate results pass; all 96 digest declarations match. The 64 baseline/candidate and repeat-stability comparisons are exact in bytes, schema and ordered values for both journals. Each retained output also passes exact comparison with its public unit data. There were no failed attempts.

Frozen implementation commit: `923a4cd7a3a53f442296efbbfaddb1e6508d01e6`. Only `baselines/native/book.hpp` changes production sources.

Baseline runtime image: `sha256:e7f01b18f284f8ff9a5e0fb5591a80dfdaa9e051f76e7076e07ae82293aedd89`. Candidate runtime image: `sha256:c9cb8f1411f4f0e4e15f7a94a681cd9b82dfb3d8a24e5859d26d37946c5e5a3d`. Builder/checks image: `sha256:130e522a3a0b4c8aeb4bfa5a8d7530e639e1d8f4033e143706fd8f556261bf93`.

Build FROM uses the local `track3-native:20261008` tag. Its identity was checked before build, after the checks-image build and after the runtime-image build against the immutable baseline ID. All probes, standalone tests and paired runs execute by immutable image IDs.

The complete phase ran sequentially under the unchanged shared `docker_slot.py`, `Dockerfile` and `run_focused.py`. It used `colima-agenthon`, Linux amd64, 4 CPUs, 16g memory, 16g memory-swap and no network for test/run containers. Per unit: one excluded warmup per side, then AB/BA/AB/BA/AB with a fresh current-native baseline in each pair. No other unit or full71 suite was timed. Docker State `FinishedAt - StartedAt` is the primary clock. This ARM64 Mac emulates Linux amd64; the results are local developer evidence with `rankable: false`. Historical Python experiments are motivation only.

## Evidence and execution record

The complete `result.json` in this directory includes all original common-runner results, samples and policy plus separate host/pinned diagnostics and storage counters. Large retained Parquet, raw outputs, full comparison details, build/test logs and the unmodified runner result remain in ignored `out/h05-order-fifo/phase2/`.

The executed grant-specific driver is `phase2.py`; it validates the baseline tag and invokes the common runner under the exclusive slot. Its timing series is complete and was not repeated. All Docker operations ended before the slot was released; no Docker operation followed release. The final report commit changes only experiment documentation/results. No merge, cherry-pick into develop or push occurred.

## Fixed implementation

`baselines/native/book.hpp` replaces each price level's deque with a vector of reusable slot nodes. Each live node holds an Order value and previous/next slot numbers. Deleted slots form a free list using the same next field. Cancellation unlinks one node; fills continue to use the head and update the same aggregate quantity. Output Orders remain value snapshots, including agent, side, price, fill metadata and the current remaining quantity on cancel.

The fixed threshold is **8 live orders**. For queues of up to 7, a short FIFO scan avoids hash allocation and hash maintenance. Adding the eighth order builds an unordered order-ID-to-slot index. It stays enabled even after the queue becomes small, so alternating insertions and cancellations do not repeatedly build the index. This threshold was selected before any timing, based on the fixed costs of hash allocation and maintenance for tiny queues, and will not be tuned after results. Unique-ID cancellation is expected O(1) once indexed. Duplicate IDs retain the deque's first-occurrence cancellation behavior by disabling the index for that level's lifetime.

All stored links and index values are integers. Moving or copying PriceLevel, reallocating its slot vector, inserting/erasing price levels, and reusing PriceSide's inactive prefix cannot invalidate them. PriceSide's existing lower_bound search, sorted price keys, inactive prefix and compaction policy remain unchanged. No level pool or agent registry is introduced. Slots retain the level's historical peak queue capacity until the level is retired, when the existing PriceSide reset releases them. Hash nodes are still allocated on indexed insertion; that cost and retained slot capacity may outweigh cancellation savings in some units.

### Memory after a sharp queue shrink

The queue's memory is **not bounded by its current live-order count**. Slot count retains the lifetime maximum number of simultaneously live orders; vector capacity can exceed that maximum because of geometric growth. Cancelling/filling returns slots to a free list, rather than shrinking the vector. Index entries shrink with live indexed orders, but the hash bucket array remains allocated after deletions (and after disabling the index for duplicate IDs). There is no slot compaction or hash rehash-down policy. The normal PriceSide path retires a level immediately when its last order disappears, releasing both containers; an active level with one remaining order can still retain its former large allocation.

The focused host test exposes actual counters through `storage_size()`, `storage_capacity()`, `index_size()` and `index_bucket_count()` and prints these checkpoints:

| Checkpoint | Live orders | Slots | Vector capacity | Index entries | Index buckets |
| --- | ---: | ---: | ---: | ---: | ---: |
| Peak before cancellation churn | 4095 | 4095 | 4096 | 4095 | 4096 |
| One live order after shrink of copied/moved level | 1 | 4095 | 4095 | 1 | 4096 |
| Same level empty before retirement | 0 | 4095 | 4095 | 0 | 4096 |
| Refilled with reused slots | 4095 | 4095 | 4095 | 4095 | 4096 |
| Level retirement/reset | 0 | 0 | 0 | 0 | 0 |

The copy used in the move test has capacity 4095, while the original geometrically grown vector has capacity 4096. These are host libc++ container counters, not heap-byte measurements or pinned Linux allocator results. The pinned Linux libstdc++ test measured 7517 buckets at peak, with one live order, after emptying, and after refill; reset reports its empty-container bucket count of 1. Slot counts and capacities matched the host test. These counters do not measure allocator bytes. The tradeoff is fast reuse and no link remapping versus retained high-water storage while a level remains active.

## Host checks

Run from this source worktree:

```sh
python3 expirements/20261008-native-hypotheses/h05-order-fifo/check_host.py
```

This compiles and runs the existing 80,000-mutation book reference test and `fifo_test.cpp`, both with `-O2` and with AddressSanitizer/UndefinedBehaviorSanitizer. The focused test covers the 7/8 threshold, long newest/oldest/middle cancellations, missing IDs, 12,000 churn steps, cancellation after partial fill, every Order snapshot field, free-list reuse, duplicate IDs, copies, moves, and populated indexed price levels moving through PriceSide insertion, erase and prefix compaction. It also syntax-checks the complete native engine with the production floating-point flags. All checks passed with Apple clang 17 on the ARM64 host. Raw logs and binaries are in ignored `out/h05-order-fifo/host/`; these checks are correctness evidence, not performance measurements or a pinned Linux runtime test.
