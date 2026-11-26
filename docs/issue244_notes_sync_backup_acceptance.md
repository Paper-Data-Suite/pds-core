# Core #244-B — Actual Notes synchronization and backup acceptance

## Safety

Use two actual machines sharing a user-controlled OneDrive (or other
configured file-sync provider) folder. Create a unique disposable
synthetic workspace named PDS-Core244-Sync-<GUID> directly under an
approved sync root, outside the active PDS workspace. Do not copy
real student records or change saved workspace preferences. Use
explicit --workspace for Core; use only process-scoped
PDS_WORKSPACE_ROOT for Suite. Record the exact Core commit, device
architecture, UTC observations, and SHA-256 of synthetic record bytes.
A local mirror/copy is not proof of synchronization.

## B1 — Bidirectional transport and stale revision

1. Device A: exact reconciled #244 source or later qualified candidate.
   Create one synthetic Task via the public CLI:
   pds-core --workspace ROOT notes create --category task
   --text-file FILE --format json. Retain returned note_id, revision,
   body, and file SHA-256 under .pds/notes/v1/. Do not put a handoff
   script or metadata into the Notes collection.
2. Wait for actual provider completion on A and B. On B, resolve the
   corresponding existing synchronized test folder (do not recreate
   it or manually transfer the record); read via notes show NOTE_ID
   --format json. Compare exact identity/revision/body/hash with A.
3. On B use notes edit NOTE_ID --expected-revision 1 --text-file FILE
   --format json with distinct synthetic text. Record revision 2 and
   new file SHA-256. Wait for actual sync completion, then read on A
   and verify byte identity. A's stale expected revision 1 edit must
   return code 4 without changing current bytes. Complete/reopen and
   archive/unarchive can be exercised with current revisions through
   CLI/menu; do not leave the record archived before subsequent gates.
4. Record actual sync transport observation separately from source
   tests; same-location two-machine acceptance proves the transport
   but not network-specific work/home conditions.

## B2 — Conflict evidence and provider limitations

Only within the disposable workspace, use actual offline competing
edits on two machines if feasible, both beginning with the same revision.
Allow normal provider sync to settle; record what really happens
(conflict copy, provider resolution, or another observed outcome).
Core cannot guarantee that a provider creates a conflict copy or
prevents a last-writer-wins overwrite. No forced alteration of the
active workspace or network configuration. Preserve both synthetic
versions outside the Notes directory before reconnecting if needed.

Independently introduce a noncanonical conflicting copy of the synthetic
record in the disposable Notes directory. This is an explicitly injected
conflict witness, not an observed OneDrive conflict. CLI list/show/edit
must refuse with exit 5; compare both original and copy hashes before
and after refusal. Leave the conflict evidence in place for backup.
Do not silently delete either copy. Keep the actual transport result
and injected conflict refusal as distinct evidence.

## B3 — Genuine Suite backup and restore

Use the official Suite v0.1.0 wheel (GitHub release digest
4830a3cbffad7c2a6ad237df8730e8da1acb78c7f462bfef683d8d889ee162b9)
and its bundled exact Core v0.6.3 admission (wheel digest
98d7596ce0eed26e4d56a17bbbbd644db3014259b56a45783a173fe8237af5e5),
in a separate fresh venv. Verify release hashes, installed metadata,
pip check, and source selection before performing backup. Do not
replace the #244 Core environment, edit Suite manifest or bypass
admission. This released composition qualifies opaque custody of
new Notes bytes, not a Suite Notes UI or new Core installation.
If actual compatibility admission fails, stop and report the gap.

With process-local PDS_WORKSPACE_ROOT set to the explicit synthetic
source, use actual installed Suite commands:

    pds backup create --destination EXTERNAL_PARENT --yes
    pds backup verify BACKUP_ROOT
    pds backup restore BACKUP_ROOT --destination NEW_EXTERNAL_ROOT --yes

Use external disposable parents outside both the source and the live
workspace, with a previously nonexistent restore target. Compare
manifest paths and SHA-256, source vs backup/workspace vs restored
file maps under .pds/notes/v1/ including the conflict copy, and a
synthetic unrelated sentinel. Assert exact relative names, sizes, and
hashes; no mutation of source. Use candidate Core against the restored
workspace via explicit --workspace to confirm conflict refusal remains
intact; if separately resolved on a disposable copy, show the original
record is readable. Restore does not select the restored workspace.
If backup rejects provider placeholder/reparse metadata, characterize
the refusal without weakening checks; use supported local hydrated
files or record a release blocker. No claim of encryption, publisher
authentication of backups, or multi-user isolation.

Reference: [Suite backup](https://github.com/Paper-Data-Suite/pds-paper-data-suite/blob/v0.1.0/docs/operations/workspace-backup.md),
[restore](https://github.com/Paper-Data-Suite/pds-paper-data-suite/blob/v0.1.0/docs/operations/workspace-restore.md).
All B gates are pending actual execution; exact commands and evidence
will be supplied per stage. Do not mark complete from this protocol.
