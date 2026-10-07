# Dictionary and binary price search

## Executive summary

This variant keeps a reusable price dictionary inside each default public side
list. Existing prices use that dictionary; new prices use binary search over the
levels themselves, while a new worst-price level appends in O(1). Trading rules, order queues, callbacks and history remain in
the shared stage-3 implementation. Public edits remain visible, and external
lists keep their identity through a compatible linear fallback. The parent completed the controlled comparison and 101 order-book tests.
The user selected the bisect variant for `codex/develop` on 7 October 2026;
this report archives the hybrid implementation. See the
[comparison report](../price-search-comparison/README.md) for measured results,
including existing-price lookup wins and new-level churn costs.

## Implementation

`_PriceLevels` is a private `list` subclass used for the initial bids and asks.
Its dictionary maps each unique price to its current position. Engine insertions
and empty-level deletions update that same dictionary. The position shifts cost
O(P), like the underlying list mutation; ordinary existing-price searches cost
O(1), and insertion-position searches cost O(log P) except for empty/worst-price
append positions, which cost O(1). Tail insertion/deletion touch only their own
dictionary entry and skip all position-shift loops. Binary search uses a key
function directly, with no O(P) temporary price list.

Public append, insert, assignment, slice edits, deletion, extend, pop, remove,
clear, reverse, sort, addition and repetition invalidate the cache. The next
search rebuilds it once. Exact standard levels with unique ordered integer
prices share the fast path. Duplicate prices, mixed sides, unsorted contents,
custom level classes, custom comparators and unusual price values retain the
original traversal and side validation. Publicly assigned external lists are
never wrapped or replaced. List subclasses supplied by callers likewise retain
their original method dispatch.

Public changes to a standard level's price, side or instance price comparators
invalidate containing lists through weak identity-based observers. Observers add
no attributes to books or levels. Pickle/deepcopy reconstruct the list from its
domain contents and rebuild disposable indexes on demand. A suspended price-level
iterator resumes the original traversal if a lifecycle callback changes the list.
The usual supported list methods perform invalidation; explicitly calling a
base-class mutator such as `list.__setitem__(indexed_list, ...)` bypasses subclass
hooks, as do direct writes to `level.__dict__`. Those low-level bypasses are not
observed by this container; callers requiring those operations can supply an
ordinary list for the compatible fallback.

## Provenance and verification

The upstream source SHA-256 constants and public signature/decorator checks are
unchanged. Installer AST normalization permits only the two annotated empty side
lists to use `_PriceLevels()`; all other constructor statements still must match
upstream. Every matching and compatibility Python file is explicitly hashed in
the overlay manifest, including the new private module.

Host validation uses the existing main checkout's Python/Ruff executables and
this worktree's PYTHONPATH. Installer unit tests, strict constructor-normalization
tests, exact-source installer validation, compilation and Ruff checks are run
locally. Runtime differential tests are extended but their execution, container
admission, developer gates, the 65-scenario regression and sequential measurements
are owned by the parent task. No Docker or benchmark is run in this worktree.

The parent built and source-audited the image and completed exact-journal checks
on six measured public units. Full candidate regression was skipped by user
instruction. The hybrid source is retained on `codex/book-dict-bisect` at commit
`924b5c2b2bf7186d70d2efdc067cf472e806aff8`; the default engine does not install
its private `_price_levels.py` module.
