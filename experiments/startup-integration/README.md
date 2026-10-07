# Startup integration with DEBUG guards

## Executive summary

The user selected the tested lazy SciPy import for develop in addition to the
already integrated DEBUG guards. The standard build and local installation recipe
now apply this change seventh. All five original experiment reports are preserved
in the [campaign archive](../hotpaths-20261006/ARCHIVE.md). Their isolated checks
completed; the new combined public regression was explicitly stopped by the user.
No completed combined 65/65 regression or combined speedup is claimed. Checks were
not resumed when the user subsequently requested committing the changes.

## Integrated change

`baselines/patches/lazy_distance_import.patch` changes only the upstream
`abides_markets/utils/__init__.py`. SciPy distance routines load when the optional
line-distance latency path needs them. Lazy explicit `pdist`/`squareform` exports
keep the original function identities; `__all__` preserves the original 25 wildcard
names. The optional path preserves arithmetic and RNG progress. The patch applies
with ordinary `git apply` after `debug_logging.patch`.

## Evidence already collected before the stop

`source-check.json` reconstructs the original engine, applies all seven production
patches and compares 42 core/markets files with the measured DEBUG source and startup
utility. The overlay validation image's 52 installed engine/adapter files matched
these sources and the committed develop adapter. The image excludes the existing
uncommitted batch edit and is not a new full production Dockerfile build.

Four startup host tests, five README command tests, twelve DEBUG runtime cases and
the pinned Python 3.11 startup check had passed. The public s001 event and message
traces matched bytes, schemas and ordered values, and actual developer gates passed.
The subsequent regression65 was interrupted on the user's instruction. Its partial
log, stopped pipeline record, commands and earlier successful checks are retained
under `evidence/`, with SHA bindings in `result.json`. The first regression launch
failed at import before simulation because repository `PYTHONPATH` was absent; that
failure and the corrected launch are both retained.

The original isolated startup experiment passed 65/65 and had local median full-run
reductions of 20.23% on s001 and 10.69% on s012. These are Mac/Rosetta observations
(`rankable=false`) with noisy pairs; they do not measure the combined change.
Raw public Parquet outputs remain in the original campaign recorded in the archive.
Preexisting batch-output edits and their untracked test are outside this commit.
