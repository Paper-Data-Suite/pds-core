# Core #238 — Slice 3G26: restrictive registry-image HANDLE release boundary

## Scope and concrete result

The existing Windows private registry image reader (`_teacher_private_registry_image_snapshot._read_windows`) opens `registry.json` with `GENERIC_READ | READ_CONTROL` and **FILE_SHARE_READ only** (share mask `0x1`). Conversely, retained registry, transaction-directory, and workspace-descriptor *observation* handles use read/write/delete sharing (`0x7`). An operating-system HANDLE opened without `FILE_SHARE_DELETE` may block native replace/rename; holding a read-only registry image HANDLE throughout a future native registry replacement is not a correct writer protocol.

3G26 adds `rehearse_synthetic_registry_reader_release()` with **no caller path, bytes, handle, callback, or permit parameters**. Its only native writes are to the module's internally allocated `TemporaryDirectory`, containing synthetic bytes and a scratch advisory lock. The sequence observes an existing registry preimage and native IDs; opens a Windows scratch reader with exactly the restrictive image-reader access/share masks; attempts replacement and expects it to be refused; rechecks the retained handle and all synthetic images; closes the restrictive handle; rechecks identities; attempts replacement again; and checks byte images, stage disappearance, registry identity transfer, and unchanged descriptor/journal/lockfile identities. Separate state codes preserve unexpected pre-release replacement, post-release refusal, drift, I/O failures, and interruption. A successful synthetic result remains explicitly **unqualified for production**.

## Windows correctness considerations

- The first replacement's sharing refusal is an *observation* (WinError 5, 32, or 33, or PermissionError), not proof of its underlying cause. It cannot substitute for native owner/DACL/backing validation.
- Read and metadata HANDLEs can differ in their sharing contracts. Existing reader access/share masks are source-inspected in regression tests, in addition to the native Windows scratch experiment.
- Handles are released using the CRT ownership/close model. Failure or interruption does not lead to a production write or fallback authority.
- No `os.replace` occurs on the real teacher-private path. No network-backed filesystem, cloud sync, hostile same-user actor, power loss, or cross-process crash is exercised.
- Neither an observed rename nor a successful file-id comparison proves file/directory durability, content CAS, exact owner binding, filesystem namespace safety against all races, or atomic multi-file journal/descriptor/registry commit.

## Tests and future boundary

The isolated Linux surrogate suite exercises normal ordering, intentional sharing errors, unexpected early success, post-release refusal, preimage tampering, postimage corruption, identity drift, interruption points, guard refusal, invalid API arguments, stable result redaction, and source-interface masks. On Windows, an additional test exercises real `CreateFileW` behavior on synthetic scratch. The guarded Windows runner also executes the focused Core #238 suite, Ruff and strict mypy, with a fail-closed exact Git baseline and three-file commit scope.

**Blocked:** no production registry mutation, journal replay or retirement, Notes read/write, writer token, or durable commit authority. A later production writer would require an independent protected native operation protocol with held ordered guards, fresh exact CAS/currentness evidence, secure writer-owned HANDLE custody, explicit persistence boundaries, and crash recovery qualification. This slice only clarifies why a restrictive reader HANDLE must not span the prospective replace boundary.
