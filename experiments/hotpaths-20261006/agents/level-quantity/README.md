Executive summary. The tested simulator preserves the trading results: all
60 developer-gate runs, exact event and message traces, seven pinned-runtime
source tests and 65 public regressions pass. This change is not supported
for adoption: median full-run time increased by 10.24% on deep-book and
8.08% on cancellation churn, failing the agreed 5% improvement and regression
guardrails. The local ranges overlap on both primary loads, so this does
not establish the cause of slower measurements. All evidence is local and
non-rankable; the isolated read microbenchmark remains separate.

# Experiment 3: visible quantity per price level

Common base: `0af6939d8815b9e39376e5c6f7fef3538cec06f1`.
The base already contains the direct-row Python liquidity-gap reducer. This
experiment adds no indexes, L2 snapshot cache, logging or copying optimization.

`baselines/patches/visible_quantity.patch` changes only `PriceLevel` and two
partial-fill mutation sites in `OrderBook`. `total_quantity` reads the maintained
aggregate. The ordinary Dockerfile applies the patch after the common baseline
patches. The lightweight overlay instead uses `apply_overlay.py`, which refuses
any unexpected baseline module hash; it applies the same transformations tested
on the manager's immutable `baseline-source` snapshot. No scorer, card, reference,
trace formatter, event order or RNG changes are included.

## Mutation audit

| Mutation | Aggregate maintenance |
| --- | --- |
| Constructor, normal add, insert-by-ID | Visible additions increase the aggregate; hidden additions leave it unchanged. |
| Quantity decrease/increase, modify, partial cancel | `update_order_quantity` adjusts the first matching visible order's difference; hidden changes leave the aggregate unchanged. Existing FIFO reordering rules remain. |
| Full fill, head pop, final level removal | `pop` subtracts the visible head quantity. Hidden removal leaves visible volume unchanged. |
| Cancel, STP cancel-oldest, replace | Existing `remove_order`, cancel and add paths maintain the aggregate; cancel-newest never adds its incoming remainder. |
| Partial fill of a resting order | `decrement_quantity` updates the known order reference and visible aggregate without an ID lookup or priority change. |
| Price-to-comply partial fill | The hidden half and linked visible half both use `decrement_quantity`; the visible half is in `book[1]`, the same location already assumed by pinned full-fill removal. |
| Price-to-comply full fill/cancel | Existing pop and linked remove/cancel paths maintain each level. |

The pinned unusual price-to-comply modify/partial-cancel behavior is retained:
these operations do not synchronize the counterpart. The aggregate reflects the
actual visible queue rather than introducing a semantic correction.

The scope is the audited pinned simulator mutation paths. `PriceLevel` exposes
mutable lists and order objects; arbitrary external direct list mutations,
`order.quantity` assignments, changing a resting order's `is_hidden` flag or
inserting the identical object more than once bypass the aggregate and can make
it stale. No new general-purpose public API compatibility is claimed. Exact
large-integer tests use Python integers above both 2^53 and 2^63; numeric precision
for arbitrary foreign/custom quantity types is outside this validation.

## Completed source checks

`check_quantity.py` imports real pinned order, price-level, order-book and message
modules under independent package names. The owning agent is a deterministic
recording stand-in. The host uses checker Python 3.13; this is a source test, not
a pinned runtime simulation. Message counters are restored separately for each
book operation so independent logical runs receive identical IDs.

Seven tests compare levels, exact visible totals, queue order and metadata,
L2/L3, outgoing message type and payload, history, transactions, owner events and
book logs after every public mutation. Nine seeded streams contain 300 operations
each. Explicit cases cover duplicates with distinct objects, hidden-only depth,
post-only behavior, insert-by-ID, partial/full fills, decrease/increase priority,
missing/wrong-price cancellations, modify, partial cancel, replace, both sides of
price-to-comply, and both STP policies for limit and market orders. A separate
large-integer test checks decrement and hidden head removal.

`evidence/host-tests.json` and its log preserve the successful result.
`evidence/host-microbench.json` contains one warmup and three AB/BA/AB pairs for
20,000 volume reads at 1, 10, 100 and 1,000 orders per level. These are isolated
read timings and exclude mutation overhead, process startup and the rest of the
simulation; they cannot decide adoption.

The worktree's `AGENTS.md` was followed; its referenced `../../AGENTS.md` is
absent. The differential-gates README was read. Public references and unit cards
remain untouched.

## Parent-controlled Docker validation

`build-plan.json` declares the Docker overlay, required mounts, pinned-runtime
test and microbenchmark commands. Only the parent owns Docker build/run and the
sequential timing slot. After building, run the seven tests against the installed
candidate modules, verifying their hashes rather than only testing a newly patched
host copy. Preserve the runtime evidence separately from host checks.

The six selected units are s001, cancel/modify lifecycle, deep-book state size,
cancel/replace churn, STP newest and STP oldest. Deep-book and cancellation-churn
are the primary timing units. Each unit requires one warmup pair, three unprofiled
AB/BA/AB pairs and a separate profile pair through the unchanged differential
runner. Both trace schemas, original row/column order, exact values and bytes,
actual developer gates and digest checks must pass. The parent ran the unchanged regression65 separately and independently
verified source, traces and gates.

The preliminary criterion is at least 5% lower median full-run container time on
each primary unit with no material regression on the other selected units.
Warmup and profile timings are excluded. All measurements and required correctness checks are now complete;
`result.json` records verdict `not_supported_regression_guardrail`.

## Completed parent measurements and independent verification

The parent executed all Docker launches in the serial slot. The manager
reconstructed 52 installed Python files from the committed implementation and
common base, checked all 60 runs against actual developer g0–g3 gates, independently
re-read ordered dual traces for all 30 pairs, and performed a fresh output-only
developer-gate recheck. All passed. The unchanged regression65 also completed
with 65 actual passes, zero failures and zero errors on the raw candidate image.

Full-run seconds are recomputed by the manager from Docker State clocks.
One warmup pair and a separate profile pair per unit are excluded; the table uses
three unprofiled AB/BA/AB pairs. Positive reduction means a faster median.

| Unit | Baseline median, s | Candidate median, s | Time reduction | Ranges overlap |
| --- | ---: | ---: | ---: | --- |
| t3-s001-price-time-priority | 1.605856392 | 1.607708321 | -0.12% | True |
| t3-cancelmodify-lifecycle | 9.943202600 | 9.731652086 | +2.13% | True |
| t3-mr-deep-book-state-size | 20.094238200 | 22.152583954 | -10.24% | True |
| t3-mr-cancel-replace-churn | 16.705942599 | 18.055290085 | -8.08% | True |
| t3-mp01-stp-newest-baseline | 4.768185581 | 4.395996507 | +7.81% | True |
| t3-mp02-stp-oldest-baseline | 5.083170311 | 4.842750693 | +4.73% | False |

Both primary units fail the required minimum 5% median reduction and exceed
the maximum 5% slowdown guardrail. No optimization is adopted. Raw pairs and
min/max ranges remain in `result.json`; all ranges except STP oldest overlap.
These three-pair local observations cannot establish a causal performance
regression or official timing. The candidate inherits invalid bytecode caches
for its two changed modules; disposable process timing includes their compilation
and startup. The report does not attribute the observed difference to this or
to cache-update work, and makes no steady-state claim.

No L2 cache until mutation was implemented. Arbitrary external direct
quantity/list/visibility mutation still bypasses the aggregate; the guarantee
remains limited to the audited pinned simulator paths.

Measured baseline control: `sha256:443d01e90bf00ff92f77d71bf672fc2a032b7df401647ac694267e8107da5d40`.
Measured candidate control: `sha256:b834d388cebfbc94ff95e3cf6370708751419b9f11e1788eb7aa3520f9944c1b`.
Raw semantic candidate/regression image: `sha256:a763a898fce586ff4deaf8f9e4e3a2df2aa142f7eed6bb54c92aa8f51b4ffff4`.
Implementation: `972069d6532756a72dde726a422c054619956d12`.
Both controls use the same wrapper that removes only the forbidden root profile
after successful serial batch; the measured units are single scenarios.

Evidence root: `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/level-quantity`. Machine-readable absolute paths and SHA-256
bindings for source reconstruction, exact/gate audits, fresh gates, bytecode
inventory, commands and completed regression report are in `result.json`.
Pinned-runtime test and microbenchmark results are retained under `evidence/`.
