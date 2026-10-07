# Numeric price keys under cancellation churn

## Executive summary

The numeric-key implementation is now selected for develop. Its saved full-run
cancel-churn median is about 12.9% slower in the simulation phase, but its isolated
1,024-level insert/delete workload is about 38.8% faster. These measurements come
from separate schedules, so neither establishes the cause of the full-run change.
The next hypothesis is to reduce key-array maintenance for repeated changes at
the best price, using a logical start offset with occasional compaction.
This document is a proposed experiment; no offset implementation or new timing
run is included in the integration.

## Experiment follow-up — 2026-10-07

The offset was implemented and measured separately in
[price-offset](../price-offset/README.md). All targeted semantic checks passed.
Historical full-simulation medians decreased on the three requested units, but
most comparable synthetic operation medians increased. Diagnostics show that
only 14.7% of level-removing cancellations delete the head, and search usually
sees five or six live prices on a side. The observations do not establish a
repeatable gain from the mechanism alone. The user subsequently selected the
measured source for develop; see the
[integration record](../price-offset/integration.json).

## Hypothesis

After removal of the last order at the best price, the current engine deletes
position zero in both the level list and its numeric-key list. Both list deletions
shift the remaining elements. Keep an active start position in the key list so
that removing its first active key increments that position instead of shifting
the entire remaining key array. If a new best level is inserted while unused
prefix slots exist, reuse the slot immediately before the active start.

This rule applies to every book and STP policy. It depends only on the mutated
position, never a scenario name, team configuration or expected trace.
Cancellation that leaves a nonempty level must not change the price index.

## Proposed mechanics

- Store the numeric keys and a private `prices_start` offset.
- Active key at logical level position i is `prices[prices_start + i]`.
- Read the best price from the active start; preserve the current best-price path.
- Binary search only the active range. Convert the absolute result back to a
  level-list position by subtracting `prices_start`.
- Removing logical level zero advances the key offset; it does not defer removal
  of the actual level or any callback, notification or history update.
- Reuse unused prefix slots for a new best level. Appending a worst level retains
  ordinary append behavior. Middle changes retain ordinary list insertion/deletion.
- Compact discarded prefix keys occasionally, based on the amount of unused space
  relative to live keys. Freeze and justify the memory bound before measurement.
- Public reorderings, unsupported levels, price edits and pickle/deepcopy retain
  the current invalidation/fallback policy. A full rebuild resets the offset.

The actual level list still shifts on deletion. This hypothesis removes only the
second shift in the auxiliary price index; it is not constant-time cancellation
for the complete engine. Compaction has occasional linear cost, additional offset
arithmetic adds overhead to searches, and middle deletions may receive no benefit.

## Diagnostics before attributing the regression

Collect diagnostics in a separate, untimed candidate run:

- distribution of live price-level counts and orders per level;
- cancel requests that remove a level versus those leaving it nonempty;
- removed/inserted levels at head, middle and tail;
- price-index rebuild count and reasons;
- time in price search/index maintenance, per-level order-ID search and callbacks.

If head changes are rare, this hypothesis is unlikely to address the observed
workload. Investigate order-ID lookup or callback/snapshot work instead. A fast
synthetic price-index workload does not imply a fast full simulator.

## Focused verification and measurement

First preserve FIFO, duplicate-ID and duplicate-level traversal, all public list
mutations, negative indices/slices, price/side edits, clones and callback changes.
Check that the active key slice equals the ordered level prices after every
operation. Exercise repeated head removal/reinsertion, middle removal with a
nonzero offset, empty-book reset and compaction boundaries. Verify that discarded
keys do not retain removed PriceLevel objects and that retained key memory is
bounded under sustained churn.

Then measure only the new candidate in the serial colima-agenthon slot, following
the user's candidate-only timing preference. Reuse the currently recorded
numeric-vector samples as the baseline; do not substitute the earlier direct-key
bisect image. Keep the comparison explicitly historical/unpaired.

Use the same three public units: cancel churn as the target, STP oldest and
state-size/deep-book as guards. Reuse five measured repetitions plus one excluded
warmup, exact event/message journals and actual developer gates. Include synthetic
head and middle churn, existing-level cancellation, add and modify at small and
large depths. For newly introduced diagnostic workloads with no saved baseline,
report candidate-only values without an invented speedup.

Keep every sample and report both Docker State lifetime and simulation time.
A useful outcome reduces target cost without losing the observed gains on the
other two units. No overall or causal speedup is established by comparing
separate measurement schedules.
