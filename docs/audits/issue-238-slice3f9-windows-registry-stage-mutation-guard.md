# Core #238 — Slice 3F9: Windows registry-stage mutation guard

**Baseline:** qualified 3F8 `60d02d53bacad0123c82ef1e196f90ce02242781`.
**Scope:** one new internal production module, one regression suite, one audit. Existing read-only/native guards and public capabilities unchanged.

## Purpose and operation

The internal Windows-only context `hold_expected_windows_private_registry_stage_creation` provides an expected-namespace-mutation boundary around the **existing independent create-only registry-stage provisioner**. It does not create, modify, replace or retire any file itself.

- Validates the canonical non-initialization intent and exact transaction-specific stage name prior to native access.
- Holds ordered local locks, existing registry file identity, workspace association descriptor, native transaction directory and a separate native private-root directory HANDLE through the scope. The private-root handle is checked against an independently opened current path using native volume/file identity, restrictive DACL, non-reparse status, and known fixed local backing, before and after the operation.
- Requires an empty stage namespace before entering; verifies the transactions directory contains **only** the intended journal, with two native reads yielding exact canonical intent bytes.
- Verifies canonical live registry and descriptor match the proposed before images via symmetric native reads before allowing the caller to create a stage.
- Compares complete private-root directory-name sets before and after; the **only** permitted addition is `.<uuid>.registry-stage` for the intent. It also requires the native stage inventory to recognize a stage, validates two native stage byte images against the exact registry after image, and revalidates journal, before-images, directory listing and effective owner.
- On any refusal, all observed files remain intact for independent recovery analysis; no cleanup, rollback, stage deletion, retry, or write token is provided.

## Deliberate limits

This is a *precondition/inspection scope*, not admission, durable transaction, exact-before CAS, authority to replace `registry.json`, or a Notes store. Windows HANDLE continuity and `FILE_FLAG_WRITE_THROUGH` in the separate staging primitive are not proof of directory-entry durability or atomic cross-file commit. The guard does not exclude same-owner malicious writers, cloud/network sync, or ABA replacement with identical bytes. A successful scope is advisory even where exact native observations agree. Existing immutable read-only guard contracts are unchanged.

The Linux equivalent for private-root registry-stage mutation and both platforms' resumable metadata replacement must be implemented before a transaction coordinator can claim write authority. First-time binding initialization needs its own absence/creation protocol. No READY state, public storage handle, or Notes write is introduced.

## Qualification

Synthetic Windows-path tests cover correct stage addition, pre-existing stages, unrelated entries, missing stage, pending journals, exact-byte failures, owner drift, guard refusal and unsupported platform. The source-only archive is SHA-256 pinned with a closed manifest. The runner pins the complete branch and source baseline, runs the targeted tests, Ruff, strict mypy and **one full Core pytest checkpoint** before a conditional commit/push. This audit does not assert those Windows gates passed until the user executes the runner.
