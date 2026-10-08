Exact pinned correctness passes. Event-engine execution is 7.86% to 9.69% slower on all four timing units. Complete-container reductions range from -0.68% to +5.08%. The 2x engine target was not achieved; this candidate is not adopted.

Measured results
----------------

Positive time reduction means a shorter candidate run; negative means a regression. The primary numbers use the ratio of five-sample median complete-container times. The component reduction is the median of the five paired time reductions. Each series has its own one excluded warmup per side and fixed AB/BA sequence; no sample or outlier is discarded.

| Unit | Container base / candidate (s) | Container reduction | Engine base / candidate median (s) | Engine paired reduction | Engine paired speedup |
|---|---:|---:|---:|---:|---:|
| t3-gb-highfreq-40hz-60s | 0.883589 / 0.838668 | +5.08% | 0.148347 / 0.156478 | -9.39% | 0.914x |
| t3-gb-pop-horizon-scale | 1.068638 / 1.075874 | -0.68% | 0.192497 / 0.213407 | -7.86% | 0.927x |
| t3-mp07-heavy-flow-oldest | 0.352812 / 0.350059 | +0.78% | 0.017875 / 0.019015 | -8.41% | 0.922x |
| t3-coarse-tick-ties | 0.396852 / 0.380233 | +4.19% | 0.022600 / 0.025056 | -9.69% | 0.912x |

The two series measure different boundaries. Complete-container timing is Docker State FinishedAt minus StartedAt and uses the production extension without added counters. The standalone component timer includes initialization, ordering, handlers, RNG, every ledger-column append, lifecycle/quote logging, and simulation-state destruction. It excludes parsing, process startup, trace extraction/sorting, both Parquet writers and destruction of returned columns. Separate diagnostic binaries increment structural counters. Both component sides use identical flags and boundaries.

| Unit | Inline deliveries | Main heap push reduction | Main heap pop reduction | Pool allocation reduction | Typed dispatches |
|---|---:|---:|---:|---:|---:|
| t3-gb-highfreq-40hz-60s | 3.89% | 3.82% | 3.82% | 3.89% | 24753 |
| t3-gb-pop-horizon-scale | 2.40% | 2.35% | 2.35% | 2.40% | 21442 |
| t3-mp07-heavy-flow-oldest | 17.65% | 17.64% | 17.64% | 17.65% | 11318 |
| t3-coarse-tick-ties | 9.16% | 3.53% | 3.53% | 9.16% | 5799 |

The fast path applies to few events on the largest units, and requeue counts remain equal to the base. Receiver binding and inline payload copies also cost work. The experiment therefore does not establish a general radical improvement; the actual four-unit measurements above determine its local outcome.

Implementation and ordering proof
-------------------------------

`baselines/native/engine.cpp` has separate incoming and outgoing message registers and one immutable buffered continuation. Sending assigns the same message ID and takes the same latency draw at the same position in the handler. It captures the payload, send time, original receive time, and causal parent. The handler finishes before another message can execute. An earlier generated event displaces the buffered event into the ordinary pool/heap; later events also enter that heap.

At every runner iteration, the minimum is chosen between the buffered continuation and the heap root. The comparator retains `(time, sender, recipient, message_id)`, including all equal-time ties. A completely identical key selects the heap first; the validated protocol never generates duplicate complete keys, including broadcasts, because their recipients differ. This is a merge of two exact ordered queues, rather than an assumption about which protocol response will arrive next.

A busy recipient consumes the original event at its original time and requeues it with the updated execution time. This preserves even the reference stop-time behavior: the loop checks the previous `current_time` and can pop one event beyond `stop_time`. It also preserves ledger `t_send`, `t_recv`, latency and causal parent across every requeue. The exchange's mutable compute delay remains in the original position: a receive adds the previous delay to availability before the handler updates that delay. Wakeups add the resulting delay after their handler.

Deferred single-recipient payloads acquire a stable pool slot only when needed. Close-price broadcasts explicitly allocate a shared message, increment references per recipient, and recycle the slot after the last delivery. Single-message inline payloads never enter the free-slot list. Incoming and outgoing registers cannot overwrite one another, including a spread response that sends many orders or cancellation messages.

Buffered requests, responses and acknowledgements bind a typed receiver. Template specialization removes the generic message-type switch for common protocol deliveries; deferred events retain the generic receiver. There remains a member-function indirect call and the kernel's wakeup/message distinction. No query, acknowledgement, ledger row or order bookkeeping is omitted.

Scope and host evidence
-----------------------

The base is `33027d74553e9a318d66557fe0f7b7bed84cfa38`. Only `engine.cpp` and `engine.hpp` change in production sources. Scenario configuration, native mapping, floating-point flags, RNG implementation, dependencies, trace extraction, Parquet writing and scoring are unchanged. This is an isolated local experiment and has no production adoption, merge or push.

The frozen plan declares four timing units and six correctness-only units. The heterogeneous batch contributes five markets, for fourteen mapped inputs. `run_checks.py` imports the unchanged scenario mapper and serializes all parameters losslessly. When no extension exists, the test harness takes the mapper's existing NumPy fallback for logarithms. Host Python/NumPy versions differ from the pinned runtime; these checks establish local base/candidate equality, not pinned numeric or Parquet correctness.

`host-correctness.json` records exact binary comparisons of all nineteen output columns (both journals), vector lengths, message counts and SHA-256 digests. The base full-output executable uses the original, unmodified base engine source. All fourteen inputs also pass combined ASan/UBSan and reproduce the same bytes. Apple ASan does not support leak detection, so the host disables that feature only; the Linux recipe enables it. `queue_test.cpp` separately exercises each field of the full key, exact duplicates, immutable payload lifetimes, delayed send-time fields, shared reference counts, slot reuse, a 5,000-turn differential queue model, mutable send delay, causal IDs, and the one-pop stop boundary without simulating an additional scenario.

`host-structural.json` records diagnostic counters, with no host performance conclusions. On the four timing units the inline-delivery fractions are 3.89%, 2.40%, 17.65%, and 9.16%; main-heap push reductions are 3.82%, 2.35%, 17.64%, and 3.53%. Requeue counts remain exactly equal. The coarse-tick input has many requeues, so inline fraction and heap reduction have different denominators.

Pinned validation, provenance and reproduction
----------------------------------------------

Phase 2a passed both journals’ bytes, schema and ordered values, shared developer gates, and actual native execution on all ten units: twenty complete baseline/candidate launches and twenty-eight market executions. All fourteen mapped C++ inputs and isolated queue probes passed ASan/UBSan and Linux leak detection. The initial missing-libasan failure is retained in `pinned-controls.json`; test-only sanitizer binaries then linked ASan/UBSan statically. Production sources/runtime never changed.

The frozen timing HEAD was `38db7d34e69e6d7b12b28c33dcac19a935e74c29`; candidate image was `sha256:2fffed1588f4b614f524d927e3a5fbb83073d55ac810c10d4e663f874cf943cb`. `performance-execution.json` records the source/input/binary hashes before and after both campaigns under a single shared exclusive lock. Reports added later do not change native sources. `phase2b.py` and `recipe.json` reproduce the commands; repeating viewed samples is outside this campaign policy.

`primary-summary.json` preserves the complete primary run records and checks in a compact committed snapshot. `result.json` retains all forty primary samples and forty component samples, warmups, per-unit counters and evidence hashes. Raw primary checks, records and retained journals are in `focused-pinned/`; raw component pairs are in `component-pinned.json`. No production change followed timing, no second campaign was run, and no merge/push/adoption occurred.

The numbers are local and non-rankable on Linux amd64 emulation on a Mac ARM64 host. They apply only to the four frozen timing units. Correctness-only units provide no speed evidence; five pairs cannot justify a general corpus-wide conclusion. All primary medians are under 1.08 seconds, which limits interpretation of small complete-run changes. The component binaries are separate standalone builds; their common boundaries do not isolate per-event costs within the production extension layout.
