# Core #238 Slice 3E8: Triple-native-image recovery review

## Boundary

This slice combines the existing protected native journal, registry and workspace-descriptor **exact-byte** readers within a single triple-retained read-only observation. It does not accept user-supplied metadata bytes or reuse a digest as an exact-byte provenance assertion.

The ordered local coordination, journal directory, registry and workspace descriptor anchors remain retained across the sequence: journal, registry, descriptor, descriptor, registry, journal. Each internal native reader independently verifies its handle, current path, backing and canonical encoding; the outer guard rechecks retained identities on exit. The effective OS owner is checked at both ends. Nested public readers (which would reacquire locks) are not called.

## Outcomes and refusals

When both observations of all three byte images agree, the existing crash-checkpoint classifier identifies journaled before, registry-only after, descriptor-only after and both-after states. Missing, unqualified, noncanonical, mismatched or changing images are refused; entry and exit failures in the retained guard override an otherwise successful advisory result. Initialization remains outside this scope because it requires qualified absence handling.

Results contain no private image, principal, transaction ID, path, handle or write token. Cases where a valid proposal matches an image remain **review required**, never READY.

## Non-goals and remaining risks

Two independently verified exact-byte reads do not prove an atomic cross-tree snapshot, uninterrupted journal-file handle lifetime, local or remote durability, exclusive distributed synchronization, or an exact-before CAS reservation. The workspace descriptor may be synced or supplied by another user. No file is created, modified, renamed, replayed, retired, or deleted here. No Notes record service or binding capability is enabled.

The subsequent gated work requires durable journal admission, write-target handle retention, exact-before CAS, protected ordered commits, recovery execution, native crash injection and installed-artifact qualification. A journal completion review alone is insufficient to retire the journal.
