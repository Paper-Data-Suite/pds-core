# Core #238 — Slice 3G21: Read-only native recovery identity bridge

**Status:** guarded Windows qualification candidate; additive and non-authorizing.

## Objective

Extend the protected native recovery inspection established by 3G14 and the synthetic path/open-handle file-ID census from 3G20. The new helper performs two **read-only**, bounded identity observations for the *existing* protected registry, pending journal, workspace descriptor and (when present) registry after-image stage. Each observation runs inside one pre-existing native descriptor/journal/registry retained-guard scope, alongside the existing canonical native byte readers, checkpoint classifier, owner comparison and namespace/inventory checks.

The entry point accepts a canonical `PrivateTransactionIntent`, one proposed **review** step, an exact expected registry revision, and two existing roots. It is not an operation writer and returns only a frozen, sanitized `state` and fixed `message`.

## Exact observation contract

1. Validate platform, enum, integer revision, root form, canonical encoded transaction intent, owner/revision transition and exclusion of `INITIALIZE` before acquiring a lock.
2. Acquire **one** `_hold_existing_retained_descriptor_guard(...)` scope. It retains the existing ordered local coordination, journal anchor, registry and descriptor guards without acquiring a nested review guard.
3. Verify effective owner, pending/stage namespace and registry stage inventory using the 3G14 internal native namespace procedure.
4. On each of two rounds, match `Path.lstat()` → read-only `Path.open("rb")` + `os.fstat(fd)` → `Path.lstat()` for the exact registry, descriptor, journal and, when present, stage names. Require regular files, single hardlinks, nonzero native `st_ino`, stable `(st_dev, st_ino, size, mtime_ns, ctime_ns)` and bounded positive file sizes. Refuse duplicate `(st_dev, st_ino)` across protected entries.
5. In the **same scope**, call the existing 3G9 checkpoint classifier and 3G12 native exact-image reader with no reentrant lock. The identity tuple orders its entries exactly as the native byte images: **journal, registry, descriptor, stage**. Verify canonical expected bytes and file sizes, requested checkpoint, revision, stage presence, repeated namespace/inventory and owner stability.
6. Refuse file-ID, metadata or image drift between rounds, unexpected namespace or checkpoint, owner changes and guard-release errors. Return the fixed advisory state only after successful guard exit. The pending-journal review is *not* a retirement permit.

The path/handle `stat` census supplements, but **does not replace**, the existing more stringent Linux `O_NOFOLLOW`/dirfd and Windows retained `HANDLE`/FileIdInfo, ACL, link, local backing, and ancestry checks enforced by native readers and guards.

## Security exclusions and limitations

- **No filesystem mutation:** no `os.replace`, append, stage removal, journal retirement, descriptor repair, directory creation, recovery replay or Notes service activation. Only read-only file opens and metadata inspections are in this candidate.
- **No portable file-ID reservation:** read-only path/open-handle observations do not keep newly opened file handles across rounds. The enclosing native guard owns its separate retained handles and identity checks, but this helper provides no production write capability, no hostile same-user resistance beyond that guard, and no global transaction CAS.
- **No durability conclusion:** stable images and native identities do not establish file/directory write ordering, post-rename persistence, crash replay, or power-loss safety. No reviewed result may be converted into a commit or journal-retirement token.
- **No cross-device or cloud guarantee:** independent workspace and registry paths may be on different file systems; advisory local locks do not establish remote coordination.
- **No provenance claim:** tests mock the protected native reader/guard where creating a production-grade private ACL fixture would be inappropriate; independent synthetic real-filesystem tests exercise the path/open-handle file-ID helper. A genuine production-protected end-to-end Windows fixture is **not yet qualified**.
- **No privacy leakage:** neither byte images, effective owner, transaction IDs, filesystem paths, raw signatures nor file handles leave this module in its review return. Exceptions return fixed, bounded statuses.

## Regression and qualification expectations

85 isolated fixture-based and synthetic filesystem regression cases cover all three protected review steps; no nested lock; guard release; changed file-ID despite matching bytes; changed bytes despite matching file-ID; wrong revision, image and stage size; checkpoint/owner/namespace drift; malformed requests; initialization refusal; read/lock/interrupt errors; real synthetic path, inode, hardlink and symlink handling. A guarded Windows runner must verify the exact 3G20 feature/main heads, inherited blob pins and clean working tree, then run the 3G21 tests, full focused #238 suite, Ruff and strict mypy before committing exactly three additive files and pushing. The periodic full Core pytest checkpoint may be deferred after the successful 3G19 5,415-test checkpoint.

**Future boundary:** fixture-backed native retained-handle/namespace continuity around a *prospective* writer remains distinct from this read-only inspection. Native writes, descriptor completion, stage retirement, journaling durability and Notes remain gated.
