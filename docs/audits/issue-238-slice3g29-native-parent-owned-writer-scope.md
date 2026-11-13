# Core #238 Slice 3G29 — Native parent custody in a synthetic writer-owned scope

## Scope and decision

3G28's protected checkpoint review returns after releasing its native guard and **must never be treated as a transferable write permit**. Slice 3G29 does not bridge that gap by trusting a prior review. Instead, it demonstrates a concrete operation-owned native *directory* handle, held continuously along with an advisory scratch lock across synthetic before-image review, restrictive registry reader release, native stage-to-registry replacement, postimage verification, and file-sync request.

This implementation accepts only exact internal enums and **never accepts a teacher path, a private registry, transaction metadata, arbitrary bytes, callback, native HANDLE, or writer token**. All writes are to fixed-name synthetic fixtures allocated by `tempfile.TemporaryDirectory` within the invocation. No production storage code is called to mutate files.

## Sequence

1. Create fixed synthetic registry, stage, descriptor and journal in one disposable directory.
2. Acquire the existing scratch advisory lock and open that **directory** as a retained native directory FD/HANDLE. On Windows use the existing native directory `CreateFileW` accessor and `FileIdInfo`; on Linux use `O_DIRECTORY | O_NOFOLLOW` and native `fstat`.
3. Verify the retained parent identity independently against a newly opened pathname, and verify the synthetic prepared byte images, file identities and lock identity.
4. Read the existing registry through the restrictive reader, verify exact image and identity, then **release** that reader before mutation.
5. Repeat protected preimage and parent-directory identity observations, including immediately before replacement, while retaining the *same* lock and directory handle.
6. Invoke exactly one `os.replace(stage, registry)` on the disposable filesystem. Preserve/deny on sharing failures or unexpected errors; never fall back to a second operation.
7. While the guard and directory handle remain held, check exact registry-after bytes, stage absence, unchanged descriptor/journal/lock IDs, stage-to-registry ID propagation, parent identity, and a file-sync request. Recheck before release.
8. Close the native directory handle, then release the advisory lock, and return a sanitized, non-authorizing status.

## Explicit limits

- A scratch advisory lock coordinates only cooperative participants. A directory handle opened with delete sharing does not block external replacement by hostile or out-of-band writers.
- Reopened-path identity comparisons do not defeat every adversarial race. This is **not** a durable compare-and-swap or an exclusive production custody protocol.
- NTFS and POSIX may differ in directory-entry persistence after fsync. File sync does not certify power-loss durability, especially journal-retirement durability.
- An in-process interruption is not a process crash or power cut. No actual restart/recovery replay was verified.
- Native guard and parent HANDLE remain private; the result contains no token, identity, path, or bytes.
- Initialization, descriptor completion, journal retirement and Notes activation are excluded.
- **Production recovery mutation remains disabled.** A later qualified writer needs the native protected retention/owner/ACL/backing protocol from existing Core, protected stage and journal custody, independent revalidation, explicit mutation authority, durable directory-entry handling, and tested crash recovery in one operation scope.

## Qualification

The guarded Windows runner pins the exact 3G28 commit, 190 inherited Core #238 blobs, and the 81-module focused suite. It checks the additive archive manifest, syntax, Ruff and strict mypy, the new tests, and the full focused suite before committing exactly three files. Full Core pytest is deferred after 3G24's 5,749 passing checkpoint.
