# Core #238 Slice 3G48 — Native two-document durability ordering, disposable only

**Baseline:** `992386b6932f9cc4e71a8663def186d905e91e67` (qualified 3G47 feature commit)
**Main observed:** `a0d5e1a50580bbe025f0cad23c7e8524203a52ec`
**Scope:** one additive private implementation, one test module, this audit.

## Specific gap addressed

The existing Windows registry `FlushFileBuffers` checkpoint (3G7) explicitly does not prove that the *registry directory entry* is durable, or coordinate the workspace descriptor's independent replacement. 3G46 performed one replacement on disposable native files; 3G47 independently classified an unknown outcome after interruption. Neither established a flush-ordering sequence for **both** metadata files and the pending journal.

This slice runs a **real OS flush-request rehearsal on internally owned temporary files**, never teacher-private metadata. It makes unsupported directory flushes an observable **refusal** rather than treating successful file flushes as a durable multi-file commit. No root, content, record, native handle, lock, or callback may be supplied by a consumer.

## Modeled write-and-recovery ordering

1. Generate fixed synthetic registry/descriptor before- and after-images, plus a pending journal, in a freshly owned temporary layout. Acquire the scratch-only local lock.
2. Verify the five synthetic files before work. Flush the pending journal file and both staged after-image files; request directory-entry flush of the transaction, private registry, and workspace association parent directories **before** replacing anything.
3. Verify the live registry and journal again. Attempt **one** stage-to-registry replacement; verify the exact registry after-image and absence of the registry stage. Flush the registry file and private registry parent directory.
4. Revalidate the pending journal and original descriptor. Attempt **one** descriptor-stage-to-descriptor replacement; verify the after-image and absent descriptor stage. Flush the descriptor file and workspace association parent directory.
5. Confirm both exact after-images, both removed stages, and the still-present exact pending journal. **Do not retire the pending journal.** On any interruption or uncertain native result, preserve pending recovery evidence in the *production protocol*; the disposable test fixture itself is cleaned up normally.

On Linux, directory fsync is attempted using `O_DIRECTORY|O_NOFOLLOW` with held native identity checks. On Windows, a native directory handle is opened with `FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT`, and `FlushFileBuffers` is attempted. Windows may reject such a directory flush: the result is `DIRECTORY_FLUSH_UNQUALIFIED_PRESERVE`, **not** a successful persistence claim or a file-flush substitute.

## Negative test matrix

- Invalid fault selector and unsupported OS: no operation.
- Pre-replacement fault: no replacement attempt; pending recovery still required.
- Post-attempt or post-flush fault: replacement might already have occurred; no blind retry.
- Directory flush failure before a replacement: no replacement attempt.
- Directory flush failure after registry replacement: descriptor replacement not attempted.
- Registry file flush failure after replacement: descriptor replacement not attempted.
- `os.replace` refusing or raising after a rename: exactly one attempt; classify unknown.
- Corrupt after-image: preserve rather than claiming a flush sequence.
- Exact successful order: journal and stages flushed before replacements; registry and descriptor file/directory flushes in that order; journal remains pending.
- No raw path, teacher identity or private contents in results or exception messages.

## Explicit non-claims and future release gates

**Not qualified by 3G48:** power-loss persistence of created parent directories, independent hardware storage/cache behavior, Windows directory flush support on the target filesystem, OS-user ACL or fixed-local backing, production canonical transaction bytes, safe writer admission, atomicity between two metadata files, descriptor completion/replay, journal retirement, native protected private-store mutation, Notes CRUD, installed wheel or macOS platform security. Linux temporary-directory fsync success is not a proof of Windows behavior or physical crash durability.

**Required next:** resolve the Windows directory-entry persistence contract with a fail-closed native Windows evidence path or an explicitly designed, verified recovery protocol; then integrate tested persistence barriers, write authorization and crash recovery with the existing Core-owned guarded native scopes. Do not infer that a prior process completed or permit journal retirement from a filesystem snapshot alone. The nine-requirement production write barrier remains intact.

**Qualification:** portable deterministic test suite plus native Windows test, 100-file focused Core #238 suite, Ruff, strict mypy. Full Core checkpoint was green at 3G40 (6,864 passed, 179 skipped) and remains reserved for the next meaningful checkpoint. All fixture data is synthetic.
