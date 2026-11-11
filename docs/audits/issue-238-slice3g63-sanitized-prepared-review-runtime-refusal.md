# Core #238 — Slice 3G63: sanitized prepared-intent runtime refusal

## Boundary and exact baseline

- Branch: `238-establish-private-teacher-workspace-storage`
- Baseline: `3dc8581d73658fc2e7525951d461db5591b39bd7` (qualified 3G62)
- Prior integration checkpoint: 7,699 passed / 186 skipped, whole-tree Ruff and strict mypy passed; wheel built and isolated-install barrier smoke passed.
- Runtime change: add `RuntimeError` to the already-bounded exception taxonomy in `review_private_production_write_barrier`. `NotImplementedError` derives from `RuntimeError` and is covered.
- The exception message is discarded and replaced with static `DESCRIPTION_UNQUALIFIED` text. Malformed requests still return `INVALID_REQUEST` before consulting a dependency.
- No production metadata, journal, stage, registry, descriptor, or Notes writer is created or enabled. All nine production-write prerequisites remain explicitly unqualified.

## Gate

The guarded runner validates exact baseline, remote, clean tree and original runtime blob; applies only the bounded one-hunk change and two additive source files; executes focused barrier tests, Ruff check/format, strict mypy and repository hygiene. It commits and pushes only when all checks pass. The full Core regression and installed candidate wheel were executed on 3G62, and are not re-run in this narrow slice.

## Nonclaims

This slice does **not** authorize a production transaction, two-root atomicity, durable directory flush, automatic recovery or replay, journal retirement, private Notes records, or release 0.6.6 support for development code. It does not prove any native Windows/Linux/macOS security qualification beyond the existing evidence.
