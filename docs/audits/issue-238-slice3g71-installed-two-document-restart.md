# Core #238 — Slice 3G71: installed-wheel canonical two-document restart checkpoint

## Baseline and decision

- Base: `5038217f1641cd65eb7775818f9f8788639137cd` (3G70), PR #247 draft.
- 3G70 CI run `43123607334` passed **15/15** including installed wheel one-file replacement on Windows and Ubuntu.
- **Decision:** progress from one-file installed-native replacement to an **independent, fresh installed-wheel, real native two-document synthetic checkpoint** on both operating systems. Do not conflate scratch with private production storage or power-loss durability.

## Exact implementation and scope

- Add `scripts/verify_issue238_installed_two_document_restart.py`, `tests/test_teacher_private_installed_two_document_restart_3g71.py`, this audit, and a new step/artifact in the existing #238 installed-native CI job. **No existing production source modules are modified.**
- The verifier runs with `python -I`, verifies the wheel originates from the isolated installed `site-packages` (not checkout), and confirms Core still denies production writes. It accepts only a wheel, source checkout used for provenance exclusion, isolated scratch root, output path, and fixed version.
- Construct a genuine canonical `FORK_COPY` synthetic intent with different descriptor and registry before/after images. Write one pending journal and two exact stages under a freshly owned temporary directory, with exclusive file creation and per-file flush. Keep all five native file identities retained while performing at most **one registry and one descriptor rename** in their own parent directories, using the corrected `FileRenameInfoEx` Core helper on Windows and `os.replace` on Linux.
- In three separate fresh scratch roots, observe (1) prepared both-stages-pending, (2) registry-after with descriptor-before and descriptor-stage-pending, and (3) registry-after + descriptor-after with **journal still pending**. Close all native handles before a separate name/identity/byte/namespace inspection. Every mismatch fails the gate; **no retry or cleanup of production data**.
- Report only fixed classification labels, platform, wheel SHA and boolean limits; do not serialize paths, principals, raw metadata, native IDs or teacher/student content.
- The existing installed no-write and one-file scratch CI gates remain enabled. All new positive observations are **synthetic only** and **non-authorizing**.

## Qualification/decision gate

The guarded runner must verify exact branch, local/remote head, clean worktree and original workflow blob before any write; apply four-file scope; run focused native tests, Ruff, strict mypy on Linux+Windows targets, install candidate wheel in a fresh venv, then run existing no-write, one-file scratch and new two-document restart verifiers; compare fixed sanitized evidence and conditionally commit/push. The post-push PR CI must pass on Windows and Ubuntu independently.

## Explicit unqualified properties

No real owner/DACL binding or production path is qualified by the synthetic fixture. Neither Windows filesystem persistence nor Linux directory/file flush calls alone prove crash/power-loss durability. Two separate native renames are **not an atomic two-document transaction**. No replay/retry, journal retirement, READY private-store handle, Notes CRUD/menu/CLI or released artifact is authorized. Keep Core #238 open and PR #247 draft.

## Slice 3G71 Repair 1 — narrow static typing correction

- The initial 3G71 local run passed 94 focused tests (1 skipped), Ruff, and patch scope, but stopped before commit on strict mypy `redundant-cast` for the nonoptional `registry_after` and `descriptor_after` fields.
- Drop only those two redundant casts in the installed-wheel synthetic verifier. Preserve casts for the optional `registry_before` and `descriptor_before` fields and leave the runtime operation, CI workflow, and native postconditions intact.
- Re-run original 3G71 focused pytest, Ruff, both mypy platform targets, isolated wheel provenance, existing no-write and single-file scratch gates, and the new two-document scratch verifier. Commit/push only after all gates pass.
- No production write, replay, journal retirement, crash durability, transaction commit or Notes authorization is enabled by this repair.
