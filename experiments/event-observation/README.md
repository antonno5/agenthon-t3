# Compact events and cached observations

Executive summary: native order events can be captured without building a full
order dictionary just for the trace. Visible volume and L2 reads can also be
reused until state changes. Trading order and independent intermediate snapshots
must stay identical. This experiment checks seven focused public workloads and
does not run the full public corpus. Local timings are not official results.
The candidate is **not adopted**: all seven final historical medians were slower.
Only this report and its result data remain; engine code, tests and build wiring
have been restored to the pre-experiment version at `6ac9e99`.

The base is `6ac9e99` on `codex/develop`, using the adopted offset image
`sha256:4a54f2c8a59d8f7bd7d23373bf96e54025d01a7560289fdcf1a0f3d0a56fdfbe`.
The measured final and intermediate policies are retained in
[result.json](result.json). Every measured container used the explicit
`colima-agenthon` context, linux/amd64, four CPUs, 16 GiB and no network. Containers
run sequentially. Each workload has one excluded warmup and five measured repeats.

## Tested candidate implementation

1. `install_event_capture.py` checks exact producer-source hashes and routes only
   the 16 native `logEvent(..., order.to_dict(), ...)` sites. The active collector
   copies trace fields directly into typed columns. It keeps the original fill
   tie-breaking and event order. `Order.to_dict()` is unchanged. Legacy/verify
   logging, custom orders/callbacks/dictionaries, mutable tags, summary logging
   and unusual timestamps retain the original dictionary path. Context-local
   routing is restored on exit, including exceptions and nested captures.
2. Visible queues remain list-compatible. Ordinary queue edits invalidate lazy
   volume totals, and native `order.quantity` writes invalidate quantity epochs.
   Public plain replacement lists and unusual entries/types use live sums.
   L2 first checks observation/price epochs and a side's structural revision in
   O(1). After a change it compares the selected side's fingerprint, allowing
   unchanged-side values to survive changes elsewhere. It holds at most four depths per
   side and returns a fresh list. Logging still creates fresh NumPy arrays for
   every snapshot. Cache state is discarded when a book is cloned.

The epochs conservatively cover all books in the process. Quantity writes can
invalidate unrelated cached reads; there is no order ownership registry or new
per-order domain field. Direct edits through `order.__dict__`, explicit base-list
methods, or overriding the tracking hooks are outside the supported cache
mutation contract, as with the existing price certificate. Normal public writes,
queue/list methods, replacement containers and subclasses are tested.

The previously recorded [hidden-level L1 bid defect](../../known_bugs/l1_bid_hidden_level.md)
is preserved for its separate correctness task.

## Checks and measurement

Tests cover partial fills and callbacks between fills, price-to-comply/hidden
orders, equal-time fills, independent event and book snapshots, every ordinary
queue mutation, direct quantity writes, public replacements, mutable entries,
subclasses, cloning/memo substitution, bounded caches, disabled/custom logging,
mutable tags and capture cleanup. The source installer still checks public
signatures and unchanged method bodies.

Every simulator output passes the existing shared developer verifier, digest
checks, and exact ordered Parquet schema/value comparison for both `trace.parquet`
and `message_trace.parquet`. A real `verify` run checks the retained legacy log;
a four-market serial batch checks process-level isolation. These extra runs are
excluded from timing samples.

The first candidate used an O(depth) cache stamp. Its initial runtime checks
caught reuse of deleted object IDs; queue tokens fixed that correctness issue.
The stamp still scanned every selected level on each read. Comparable simulation
medians were 2–4% lower on the three historical workloads; that unpaired result
does not prove a causal gain. A second revision used only a global stamp; its
interrupted schedule showed large time variance, and diagnostic counts showed
that it invalidated unchanged sides too often. The final candidate combines a
cheap global check with a side fingerprint, clears clone cache state, and updates
volume-cache metadata through a private native list. A final follow-up invalidates
after iterator/sort callbacks and pending slice replacements, protecting reads
made during public mutations. All attempts remain separate.

Baseline samples for STP oldest, deep book and cancel churn come from the saved
offset experiment. Four additional baseline workloads are measured once during
the first-candidate comparison in alternating pairs. The final revised candidate
reuses all those baseline samples. Final differences are **unpaired**, so they do
not isolate causal speedup. There is no per-optimization ablation or full-corpus
performance claim.

## Evidence and historical reproduction

Candidate sources, tests, policies and measurement tools remain available in
historical commit `d7eb90a`. They are excluded from the active branch files.
Reproducing that candidate requires a separate checkout of that commit; the
current production Dockerfile builds the pre-experiment engine.

Raw logs, exact journals and installed-source inventories are retained locally
under `out/event-observation-20261007/`. The committed [result.json](result.json)
contains every timing sample, image ID, source hash, policy and evidence hash.
Validation counts below describe the tested candidate, not new tests of the
restored engine. No additional timing runs were made for this report-only change.

## Results

Final runtime tests: **194 passed**; host adapter/installer checks: **41 passed**.
All seven focused workloads, legacy verification and serial batch isolation passed exact journal and developer checks.
The final historical medians are slower on every workload. The candidate was rejected and removed from the active engine; these results do **not** establish an overall speedup.

| Workload | Simulation before, s | Simulation after, s | Change | Container change |
|---|---:|---:|---:|---:|
| STP oldest | 2.508 | 2.536 | +1.1% | +3.6% |
| Deep book | 14.039 | 17.064 | +21.6% | +21.7% |
| Cancel churn | 8.196 | 10.138 | +23.7% | +28.5% |
| Price-time priority | 0.058 | 0.082 | +41.1% | +28.8% |
| Partial fill/cancel | 6.976 | 8.788 | +26.0% | +24.3% |
| Cancel/modify | 6.032 | 6.782 | +12.4% | +11.6% |
| Heavy flow oldest | 2.592 | 3.622 | +39.7% | +46.2% |

Negative means less time. Each value is the median of five measured runs; warmups, verify, batch and diagnostic runs are excluded. These are unpaired observations, not a universal or causal speedup claim.

See [result.json](result.json) for every sample, all three clocks, first-candidate results, image IDs, diagnostics and evidence hashes.

## Mechanism diagnostics

An excluded cProfile run on STP oldest passed exact journal and developer checks.
It recorded 57,282 native scalar events and no `Order.to_dict()` calls. The saved
base audit recorded 57,282 `to_dict()` calls. Volume recalculation visited 34,889
queue entries versus 321,666 in the saved base audit; total quantity getter calls
fell from 241,569 to 137,669. These counts show avoided work, not an end-to-end
speedup. Epoch tracking, compatibility checks and cache maintenance also cost CPU
time. Profiled times are excluded from the performance table.
