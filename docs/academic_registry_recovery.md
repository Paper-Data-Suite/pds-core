# Academic Registry Recovery Guide

This guide covers conservative recovery for the Core v0.6 Academic Period and
reportable-data registry. Read the [integration guide](academic_registry_integration.md)
and accepted [ADRs](decisions/README.md) before acting.

```text
Diagnose before repairing.
Preserve immutable history.
Do not edit Publication Records or revision files in place.
Do not patch SQLite rows manually.
Do not infer current state from filenames.
Do not remove a lock merely because it is old.
Do not alter a manifest to force a digest match.
```

Use `pds-core academic registry status`, targeted `show` commands, and
`pds-core academic registry validate --format json` to record the initial
state. Add `--verify-manifests` when exact producer bytes are relevant. Use
`--strict` when warnings must fail the procedure. Preserve command output and
the installed Core and producer package versions with the incident record.

## Missing, stale, corrupt, or incompatible catalog

The SQLite catalog is disposable. A catalog failure does not invalidate valid
canonical JSON or producer records.

1. Validate canonical Academic Period, registration, publication, and
   withdrawal state.
2. Run `pds-core academic registry rebuild-catalog --dry-run` and review every
   finding.
3. Rebuild the complete catalog with `pds-core academic registry rebuild-catalog`.
4. Validate and show the installed replacement.
5. Never repair individual SQLite rows.

The rebuild is atomic and complete; it is not an incremental repair. It does
not inspect manifest bodies. If a catalog is missing, read-only catalog queries
must fail rather than create it implicitly.

## Missing or altered manifest

1. Show the exact Publication Record and record its publication ID, manifest
   path, digest algorithm, and expected digest.
2. Inspect the exact workspace-relative path. Do not follow a mutable alias.
3. Restore only trusted bytes that reproduce the recorded SHA-256 digest.
4. If those exact bytes are unavailable, produce a new immutable manifest
   revision and publish it by explicit supersession.
5. Never edit the historical publication envelope, path, or digest.

Core binds bytes; it does not parse producer educational meaning. Restoring
different valid JSON is still corruption when the bytes do not match.

## Registration or calendar pointer problems

Validate the complete history, list exact revisions, and inspect the canonical
`current.json` pointer. Preserve orphan revisions. Never select the highest
revision automatically and never promote or delete an orphan automatically.
Opening/closing a school year or comparing timestamps does not determine the
right pointer.

Supported writers deliberately stop when orphan history makes intent
ambiguous. Pointer repair then requires a separately reviewed, evidence-backed
procedure; do not improvise an edit because a higher-numbered file exists.

## Publication-series corruption

Validation may report missing or cross-series predecessors, branches, cycles,
competing heads, disconnected chains, decreasing record-set revisions, or
contradictory reuse of one logical revision. Catalog rebuild cannot repair any
of these canonical problems. Preserve all Publication Records and withdrawals,
stop publication in the affected series, and escalate for a separately
reviewed recovery/migration. Do not edit or delete immutable envelopes.

Core defines a series as `ModuleWorkRef + publication_kind + record_set_id`.
The logical revision adds `record_set_revision`; neither timestamps nor
filenames repair a broken chain.

## Withdrawal and partial success

A withdrawal is a separate immutable record. It does not mutate, restore, or
delete its Publication Record. Exact replay returns existing state; replay
with a different reason conflicts. Continued publication after a withdrawn
head requires explicit supersession of that head.

`RegistryServicePartialSuccessError` means durable state may already exist even
though final verification failed. Record its structured `.state`, reload the
canonical registration/publication/withdrawal, verify current selection and
manifest bytes, and reconcile. Do not delete verified state and retry blindly.

## Locks

Known lock IDs are:

```text
catalog
period:<school_year>
registration:<class_id>/<module_id>/<work_id>
publication:<class_id>/<module_id>/<work_id>/<publication_kind>/<record_set_id>
```

Lock age alone does not prove staleness.

Safe procedure:

1. List locks, then show the exact lock ID.
2. Record its identity and SHA-256 fingerprint.
3. Confirm through process/deployment evidence that no active writer uses it.
4. Run `pds-core academic registry clear-lock <lock-id> --expected-sha256 <digest> --dry-run`.
5. Clear only that fingerprinted lock with the same digest and `--force`.
6. Rerun validation and the interrupted operation if appropriate.

If identity or bytes change between observation and clearing, stop and audit
again. Never use age, filename resemblance, or a wildcard as authority.

## Changed during audit and missing profiles

A `changed_during_audit` finding invalidates that observation. Do not combine
its partial results with an earlier or later scan; allow the writer to finish
and rerun the complete relevant audit.

Missing producer profiles are informational unless the command or deployment
explicitly requires them. Shared-envelope, series, storage, and digest checks
may still run without a profile. Installing or enabling a profile changes
compatibility evaluation only; it does not modify canonical records or grant
authorization.

## Recovery boundaries and backups

Core does not define institutional backup policy, legal retention, cloud sync,
credential recovery, authorization restoration, or complete operating-system
disaster recovery. Deployment owners must design and test those controls.

Back up canonical Core JSON, producer-native records and history, exact
immutable manifest bytes, class metadata, standards, and relevant Core and
producer package versions. The derived SQLite catalog need not be backed up
when all canonical sources are preserved and verified because it can be
rebuilt.

Never place real student, roster, manifest, scan, credential, or other
sensitive educational data in a public issue or recovery transcript.
