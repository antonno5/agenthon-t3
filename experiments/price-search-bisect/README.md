# Bisect price search

## Executive summary

This variant finds an existing price and a new level's insertion position with
binary search over the existing ordered levels. It keeps the original order
queues, trading rules, callbacks and history. It stores no price dictionary or
copied key list. Parent-coordinated validation passed 99 order-book tests and exact journal
checks on six measured public units. On 7 October 2026 the user selected this
exact implementation for the default engine in `codex/develop`. Full candidate
regression was omitted at the user's request. The
[comparison report](../price-search-comparison/README.md) records all measured
results and their limits; no speedup against the original linear-search engine
was measured in that comparison.

## Implementation

The initial bid/ask lists are list subclasses with a small ordering certificate
inside the container, leaving the keys of `vars(book)` and level domain state
unchanged. Only the two initial side-list expressions change to
`_PriceLevels(Side.BID)` and `_PriceLevels(Side.ASK)`; the installer normalizes
exactly these direct assignments for its unchanged-body AST comparison. All
upstream public method signatures and the rest of initialization stay unchanged.
Book-wide attribute interception is absent. The PriceLevel invalidation hooks
use `object.__setattr__` / `object.__delattr__` directly. Empty-book and new-worst-price insertion paths
still run before binary search. Search uses `bisect_left(..., key=...)` with
ascending ask prices and negated bid prices; duplicate levels begin at the first
matching position and retain the original live traversal, including its behavior
when cancellation deletes a yielded level.

Ordinary inserts validate neighboring prices in constant work; deletion retains
an existing ordering certificate. Public list mutations invalidate or update the
certificate. Public assignments of replacement lists retain the supplied list's
identity and use the original traversal. Unsorted containers, custom level
subclasses, wrong-side levels and custom numeric prices also use that fallback.
A class-level epoch records edits or deletion of a native level's public price
or side, and assignment/removal of its instance price comparators. Containers
recheck ordering once after such an edit; missing fields and comparator overrides
use the legacy traversal without raising during the eligibility check. No ordinary lookup builds a
key list or scans all levels. Inserting/deleting in a Python list still moves
array entries and costs linear work.

Lifecycle callbacks can edit the live list between duplicate matches. The
matching generator checks invalidation when resumed and continues the original
scan from its next index if ordering no longer holds. Pickle/deepcopy preserve
the container and do not add service fields to any book or level instance.

## Validation and limits

Host Ruff format/check, Python syntax, unchanged-method AST checks and all 21
installer tests passed, including rejection of wrong sides, alternate call shapes
and unrelated initialization edits. The SHA-256 manifest explicitly covers all eight Python
files in `matching/` and `matching_compat/`. Installer AST normalization is limited to those two exact managed-side
initializers in `OrderBookState.__init__`; upstream source digests, public
signatures, other method bodies and approved overlay digests remain mandatory.

Added runtime tests compare both sides and public mutation methods against the
independently reconstructed original engine. They cover sorted-search operation
counts, insert/remove certificate maintenance, public mutation revalidation,
duplicate levels, callback reordering, instance comparator overrides and removal,
deleted level fields, subclass dispatch, pickle and deepcopy.
The parent executed the runtime suite (99 passed), built and source-audited the
image and completed sequential measurements with exact journals. The six-unit
comparison has 72 accepted scheduled runs across both variants, including
warmups. Full 65-scenario candidate regression was skipped by user instruction.

The optimized container's invalidation hooks apply to normal list methods and
operators. Explicit calls to base-class mutators such as
`list.__setitem__(book.asks, ...)`, or edits through `vars(level)` that bypass
attribute assignment, bypass those hooks; same-length reorderings through those
mechanisms are not certified. Callers requiring such low-level mutation can
supply a plain replacement list, which always follows the legacy scan. This is
an explicit compatibility limit of the adopted implementation. A price/side
edit also invalidates other managed containers through the shared epoch, so that
unusual mutation can cause one extra ordering check per subsequently used side.

`../../AGENTS.md`, referenced by the repository instructions, does not exist in
this checkout's ancestor tree. The repository's own `AGENTS.md` was read. Docker,
benchmarks, runtime tests and full regression were not run in this worktree.
