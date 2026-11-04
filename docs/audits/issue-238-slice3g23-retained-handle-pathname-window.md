# Core #238 — Slice 3G23: synthetic retained-handle/pathname window

**Status:** candidate for guarded Windows qualification. No production writer or user data.

## Boundaries

This slice adds a narrowly scoped **native scratch-file experiment** for a vital distinction in the eventual recovery writer: an open file handle identifies the opened object, whereas the pathname may refer to a different object after an atomic rename/replacement. The entry point takes **only an exact cooperative interruption enum**. It accepts no filesystem location, private metadata, payload, native handles, writer callback, journal evidence, CAS token, or Notes resource. It allocates a fresh `TemporaryDirectory` with fixed synthetic bytes and removes it on scope exit.

The test holds the existing 3G19 native one-byte synthetic advisory lock during preimage, target-handle-open, replacement attempt, postimage, target-handle-release, and final pathname/identity checks. It uses the 3G20 synthetic native file-ID checks, tests the old handle's preimage through its actual `os.fstat`/read, and rechecks the whole synthetic namespace and stage presence. It distinguishes two platform-dependent results:

1. **Replacement succeeded while old target handle was retained.** The old handle must still identify the old registry bytes and file ID; the pathname must now identify the staged file ID, with descriptor and journal identities unchanged, and the stage absent.
2. **Replacement refused by the open target handle.** Only Windows sharing/access refusal qualifies for this classification. The old handle, registry pathname, staged pathname, descriptor, journal and lockfile must all remain consistent with the original preimage. Unexpected I/O failure does not count as an expected refusal.

After the held target handle closes, still under the scratch lock, the code rechecks exact namespace, bytes and file identity. A replacement, a refusal, or a closed-handle recheck does not establish a durable filesystem transaction or a safe production writer.

## Fail-closed conditions

Corrupt or missing preimage, mismatched handle/file ID, unexpected replacement error, postimage/pathname drift, local advisory guard refusal, or interrupted/unknown execution return a bounded status that never grants authority. Cooperative interruption fault points cover guard acquisition, preimage observation, target-handle open, replacement attempt, postimage check, and handle release. These do **not** model process termination, OS crash, rollback or power loss. The error result omits private paths, raw bytes, file IDs and native handles.

## Limitations and threat boundary

- The scratch advisory lock coordinates only lock-honoring participants. It is neither the production registry/descriptor/journal retained guard nor a defense against a hostile same-user process, reparse races, or cloud-backed storage.
- The outcome on Windows varies with underlying sharing modes and filesystem policies; **both blocked and successfully replaced are admitted as non-authorizing observations**, only if all native file-ID/byte checks agree. Neither outcome can be used as a replacement permission.
- `os.replace` and postimage bytes do not prove durable parent-directory persistence or transaction ordering after power loss. There is no durable commit, expected-revision CAS, initial binding, journal retirement, descriptor update, recovery replay or Notes access.
- No production teacher-private files, modules, or public APIs are modified. This module must **not** be promoted to a production writer; a future implementation needs a separate native guard, mutation and crash-recovery contract.

## Qualification

The guarded runner must verify exact feature/main Git heads, all inherited Git blobs, source SHA-256 manifest, additive three-file scope and clean branch. It runs the new tests and the complete focused Core #238 selection, Ruff and strict mypy, and automatically commits/pushes only on success. The full Core suite was last qualified in 3G19 (5,415 passed), and is deferred on this slice.

## Next

3G24 should characterize Windows native sharing flags and retained HANDLE open policy at the actual *read-only* production guard boundary, without attempting production replacement. A durable writer still requires independent journal/persistence and interruption proofs.
