# Shared Python book mutations

## Executive summary

Stage 3 centralizes order removal, quantity changes, queue movement and empty-level
removal without changing the original lists or trading rules. This shared base
is used by two independent price-search experiments. The real-engine suite passed
59 tests against independently loaded original source; the repository suite passed
385 tests. The shared-base image was installed and source-audited; its already
completed public regression passed all 65 scenarios. At the user’s request, full
regressions of the two price-search candidates are skipped. Their order-book tests
and exact journals on the measured scenarios are retained. See the adjacent
`price-search-comparison` report for the comparison.

## Mutation seams

`OrderBookState` owns `_place_order`, `_matching_price_levels`,
`_insert_price_level`, `_remove_empty_level` and `_remove_order_from_level`.
`PriceLevel` owns `_find_order`, `_remove_at`, `_set_order_quantity` and
`_move_to_tail`. Cancel, modify, partial cancel and matching reuse these seams.
Lifecycle history, notifications and snapshots retain their original positions.
PTC paired removals retain their order, and partial execution does not change queue
priority. Duplicate order IDs, duplicate public levels and public list reassignment
are explicitly compared against the original source.

## Installation and provenance

The installer still requires the exact seven-patch upstream SHA-256 files and
unchanged public signatures/decorators. Unchanged method bodies are AST-compared.
Five book methods and three price-level methods are intentionally changed;
`baselines/matching/overlay_manifest.json` records every approved Python overlay
file hash. Refresh that manifest explicitly after a reviewed overlay change.
Behavioral equivalence now depends on real-engine and dual-journal differential
checks, rather than claiming all method bodies remain identical.

The earlier `python-book-layers` report describes the frozen stage-1 extraction;
its image IDs and source hashes are historical evidence, not current stage-3 hashes.
Preexisting batch adapter edits are held equal in every comparison and are not
attributed to this refactor. No sealed data, scorer changes or official rankable
performance claims are involved.

## Shared snapshot

The independent worktrees start from commit
`ac1baaba2c89ce3ac9e5df58be57dab2daf96082` on
`codex/book-mutations-base`. The shared image is
`sha256:a431cf514d40a72c64b5a99c547a573ebfc35d36b8a94096980499afa367c3d8`.
Raw source audit, runtime tests and existing regression evidence are under
`out/python-book-stage3/`. This stage consolidates mutation paths; its standalone
speedup was not measured in the price-index experiment.

On 7 October 2026 the user selected the bisect variant for integration into
`codex/develop`. The current checkout includes this common refactor followed by
the exact measured binary-search implementation. The snapshot commit and image
above remain the historical shared-base identities.
