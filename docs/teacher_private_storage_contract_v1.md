# Core teacher-private workspace association and storage contract v1

**Issue / design owner:** Core [#238](https://github.com/Paper-Data-Suite/pds-core/issues/238); [#235](https://github.com/Paper-Data-Suite/pds-core/issues/235) umbrella.
**Contract status:** **D0 design-freeze candidate**, submitted for explicit owner acceptance after Slice 1; these are **planned types and services, not importable APIs**.
**Baseline:** Core branch `238-establish-private-teacher-workspace-storage` started at `a0d5e1a50580bbe025f0cad23c7e8524203a52ec`; published Core 0.6.6 remains unchanged.
**Authority:** `teacher_experience_contract_v1.md` §4.5, ADR 0005, accepted Suite specification §§8.3–8.5, security threat model in `security/teacher-private-storage-threat-model.md`.

## 1. Purpose, ownership and capability policy

A Core Notes & Tasks collection must be bound to **(verified local OS owner, stable logical workspace association)**, not to a workspace directory string, a display name or a transferable UUID alone. The first implementation establishes the association and private metadata infrastructure only. **It creates no Notes records** and does not introduce the future `pds-core notes` CLI or any `:notes` dispatch. There are no new tokens in `get_teacher_experience_capabilities()` under #238: the #237 tokens stay exactly `terminal.header.v1` and `terminal.notes_command.v1`. `notes.records.v1` is reserved for #239's qualified full record service, not private-folder existence.

Core remains authoritative. A caller-provided `TeacherContextHint.workspace_root` is an untrusted hint; `caller_application`, `actor_reference`, class/work metadata and Note text never establish an owner. Consumer code must not open filesystem paths directly under this service, reinterpret an association ID as authorization, or persist a supposedly secure handle beyond its verified lifetime.

## 2. On-disk schema (proposed freeze)

The schema is independent from the `pds_core.teacher_experience/1` Python interface version and Core package version.

### 2.1 Non-secret workspace sidecar

Target **only** after explicit binding: `<workspace>/.pds/teacher-private-association.json`. Do not read or reinterpret `.pds/workspace.json` as a stable ID; `ensure_workspace_root(create=True)` currently rewrites that generic marker.

Illustrative exact v1 instance (synthetic UUID):

```json
{
  "schema": "pds.teacher-private-association",
  "version": 1,
  "association_id": "6fb32a62-83e2-43f6-9823-687801593c8b"
}
```

- Exact `schema` and integer `version`; exact allowed keys (no silent future extension), strict UTF-8, canonical JSON output with trailing newline, and a bounded maximum file size (4 KiB). Unknown/new versions are **not** auto-downgraded or overwritten.
- `association_id` must be a canonical lowercase UUIDv4 created from an OS-grade random source; never inferred from a directory name, old generic marker, student data, actor label, credential, raw path or network identity. UUID is **not secret** and grants no private access.
- No timestamps, owner SID/UID, path, teacher name, work title, student/class ID or Notes bodies are written to the sidecar.
- Missing descriptor does not prove absence of private records; registry recovery logic and explicit review handle ambiguous states.

### 2.2 Qualified local private root

Preferred account-local locations (must be verified, not assumed):

```text
Windows  %LOCALAPPDATA%\Paper Data Suite\private\notes\v1
macOS    ~/Library/Application Support/Paper Data Suite/private/notes/v1
Linux    ${XDG_DATA_HOME:-~/.local/share}/paper-data-suite/private/notes/v1
```

`APPDATA` (roaming config) is **not** interchangeable with `%LOCALAPPDATA%`. The Linux XDG setting must be absolute and independently verified. A data-root environment string is untrusted until native process ownership, parent-directory/reparse/symlink and effective permissions are qualified. Windows current process **token SID**, not username; POSIX **effective UID** and filesystem owner. The root must be locally backed with known security semantics, not an unverified synced, remote or removable tree. Required modes on POSIX: 0700 for directories, 0600 for files, plus effective ACL review. Windows requires native effective DACL verification; `os.access()` is not sufficient. Unsupported platforms fail closed.

Layout within the verified owner-local root:

```text
v1/
  registry.json                # private; qualified principal, revision, bindings
  .registry.lock               # owner-private cross-process coordination
  transactions/               # narrowly scoped recoverable intents, no bodies
  collections/
    <association-uuid>/        # private metadata scope; no Note body in #238
```

A UUID appearing under two different OS users refers to **distinct** protected local collections. Never search or read another OS user's private root even if its association UUID is known.

### 2.3 Protected registry and binding entries

Illustrative schema (synthetic identifiers/paths only; actual private path is omitted from public diagnostics):

```json
{
  "schema": "pds.teacher-private-registry",
  "version": 1,
  "owner": {"kind": "posix_euid", "value": "1000"},
  "revision": 1,
  "bindings": [
    {
      "association_id": "6fb32a62-83e2-43f6-9823-687801593c8b",
      "binding_revision": 1,
      "accepted_root": "/synthetic_workspace_a",
      "root_fingerprint": null,
      "state": "active"
    }
  ]
}
```

- Owner kind is one of `windows_token_sid`, `posix_euid`; owner value is the **native verified** SID/UID in the *private* registry only. Reject unknown kinds, coercion, caller-provided identity and mismatch with current execution context. No attempt to interpret a display/actor label as identity.
- `accepted_root` is private canonical location/binding evidence, **not** durable logical identity. `root_fingerprint` may contain verified filesystem object/volume identity; `null` is allowed when not safely knowable. Such evidence helps detect moves and duplicates but does not auto-authorize one. Do not log full private path/SID/UID in routine diagnostics.
- `revision` and `binding_revision` are positive monotonic integers, checked before mutations under locks; future-version/oversized/invalid/corrupted documents are refused, never repaired silently. Duplicate association IDs in one owner registry are corruption, not duplicate Notes collections.
- Collection directory creation is separate from record persistence; a newly bound empty directory **does not imply #239's Notes service is installed or that a past collection was empty**.

## 3. Typed #239 handoff and planned public API

The **public service candidate** is `pds_core.teacher_private_storage`. Internal OS, codec, locks and association helpers may live in private modules. Do not publish empty importable placeholders in Slice 1. During subsequent implementation, additions must be reviewed against these frozen targets *before* marking them public.

```python
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

class TeacherPrivateScopeState(str, Enum):
    UNBOUND = "unbound"
    READY = "ready"
    REVIEW_REQUIRED = "review_required"
    CONFLICT = "conflict"
    RECOVERY_REQUIRED = "recovery_required"
    UNSUPPORTED_PROTECTION = "unsupported_protection"
    ACCESS_DENIED = "access_denied"
    CORRUPT_METADATA = "corrupt_metadata"
    STALE_STATE = "stale_state"

class TeacherPrivateBindingAction(str, Enum):
    INITIALIZE = "initialize"
    REBIND_MOVE = "rebind_move"
    FORK_COPY = "fork_copy"

@dataclass(frozen=True, slots=True)
class TeacherPrivateScopeInspection:
    state: TeacherPrivateScopeState
    association_id: str | None       # informational UUID, never credential
    revision_token: str | None       # opaque currentness guard, not credential
    message: str                     # sanitized; no raw path/SID/private text

@dataclass(frozen=True, slots=True)
class TeacherPrivateBindingPlan:
    action: TeacherPrivateBindingAction
    association_id: str | None
    expected_revision_token: str
    plan_token: str                   # opaque operation guard, not credential
    message: str                     # human-safe requested change and risks

# Importable only after the corresponding later slice is implemented/tested.
def inspect_teacher_private_scope(
    workspace_root: Path | None = None,
) -> TeacherPrivateScopeInspection: ...

def plan_teacher_private_binding(
    workspace_root: Path | None = None,
    *,
    action: TeacherPrivateBindingAction,
    expected_revision_token: str | None,
) -> TeacherPrivateBindingPlan: ...

def commit_teacher_private_binding(
    plan: TeacherPrivateBindingPlan,
    *,
    confirmed: bool,
) -> TeacherPrivateScopeInspection: ...
```

All constructors reject invalid types and controls rather than coercing arbitrary objects. `plan_token`/`revision_token` bind the state and intent; they are **not** security tokens, session identities, or authorization. An explicit `confirmed is True` is necessary but **never sufficient** without verified native owner/security/currentness. No method auto-prompts; menus/CLI in #240 decide interaction.

**#239's private service seam** is an **opaque, Core-issued short-lived qualified scope** created only after a fresh `READY` verification. #239 must call the Core owner/path/registry verifier again **under the record-operation lock**, not use a forged or stale `TeacherPrivateScopeInspection` or a raw `Path` supplied by a consumer. The eventual record service must own its own currentness and atomicity rules and must not publish owner SID/private root in return values. It cannot rely on the UUID as a bearer token. Exact record-facing operations and signatures are #239's separate contract, not a premature #238 record schema.

### Error and failure semantics

- `UNBOUND`: no private binding; inspection **does not** create or imply an empty collection.
- `READY`: native owner, protection, sidecar, private registry, location continuity and binding revision have all been verified.
- `REVIEW_REQUIRED`: plausible move/restored descriptor/foreign-device metadata; offer explicit review, no implicit reuse.
- `CONFLICT`: association appears at a distinct still-live root, or the registry cannot distinguish duplicate claims; no aliasing. A fork-copy is a separately confirmed operation.
- `RECOVERY_REQUIRED`: known interrupted transaction, missing sidecar paired to registry, or another recoverable inconsistent sequence; preserve existing files and require qualified recovery.
- `UNSUPPORTED_PROTECTION`: system cannot verify its native owner/ACL/link/local-filesystem requirements; no weaker fallback.
- `ACCESS_DENIED`: native checks reject this effective owner or deny required read/write access.
- `CORRUPT_METADATA`: invalid, oversized, unknown-version or ambiguous metadata; do not silently normalize/replace.
- `STALE_STATE`: comparison token/revision/lock/state changed between plan and guarded commit; must re-inspect and replan.

The inspection result represents a **state**, not an exception with raw secrets. I/O and malformed caller arguments may raise structured Core exceptions with bounded safe messages; never leak note text or private OS identity into routine CLI output.

## 4. Decision table for move, copy, restore and crash

| Observed situation | Read-only inspection | Qualified, explicitly authorized next step |
| --- | --- | --- |
| No descriptor, no matching owner-private binding | UNBOUND | Review and commit INITIALIZE; generate fresh UUID, no record |
| Descriptor+binding match, root and owner/security current | READY | Read-only reopen; do not write a new ID/record |
| Workspace same root moved or renamed; old accepted location absent | REVIEW_REQUIRED | Explicit REBIND_MOVE after collision checks; preserve UUID/collection |
| Original root still present; copied root has same descriptor | CONFLICT | Explicit FORK_COPY on copy, replace copy's sidecar with new UUID; original unaffected |
| Original root vanished, continuity cannot be proven | REVIEW_REQUIRED | Explicit rebind/fork choice, with warning that OS proof is unavailable |
| Descriptor exists on other OS account/device but local registry absent | REVIEW_REQUIRED | Explicit new owner-local binding after owner checks; no old private data imported |
| Descriptor missing, but owner registry retains accepted binding | RECOVERY_REQUIRED | Review recovery, never blindly create a new collection |
| Malformed/duplicate/unknown schema in either metadata | CORRUPT_METADATA | Safe inspection/recovery path; preserve bytes; no auto-reset |
| Concurrent plan stale at commit | STALE_STATE | Abort before overwrite and request new review |
| Private location is unsafe/unverifiable | UNSUPPORTED_PROTECTION or ACCESS_DENIED | Refuse writes; native remediation outside this service |
| Crash after sidecar but before registry finalization | RECOVERY_REQUIRED or replayable explicit transaction | Under locks revalidate exact journal and originals; complete or refuse; never auto-alias another owner |

A copied descriptor is *intentionally not* an authentication token. A new OS user may accept the same workspace association as a separate local owner scope **only after explicit review**; no local notes from other owners are transferred. A new cloned workspace under the same OS user must fork. If the origin is missing and the teacher elects a fork, the original binding and local records remain in place for possible later recovery; no destructive cleanup is implicit.

## 5. Atomic commit, locking and crash recovery protocol

1. **Inspect** without creating even a lock file. Normalize the workspace via Core's non-mutating resolution/inspection; never call `ensure_workspace_root(create=True)` for a private binding check. Verify directory and descriptor protection before reporting READY.
2. **Plan** reads the descriptor and owner-private registry, computes bounded expected metadata revisions and filesystem identity evidence; carries a proposed action with no durable write. A rejected/unknown action is a no-op.
3. **Commit** reacquires actual OS effective principal and native directory/ACL protection; opens the qualified owner-private registry lock and workspace-descriptor coordination guard in a documented global order. Use OS-managed locks (Windows byte-range/natively backed and POSIX `flock`/equivalent on supported local filesystems), not blind stale-lock deletion. If cross-owner/cross-process descriptor coordination is not available, **refuse** instead of claiming serialized safety.
4. With guards held, re-read owner scope, schema, descriptor, registry, accepted-root/fingerprint and all expected revisions/plan facts. Reject changed conditions as STALE_STATE; never quietly rebase the teacher's decision.
5. Write a minimal owner-private **intent journal** with expected before/after descriptors and registry revisions; fsync according to supported platform. Create/update sidecar and registry using no-follow/atomic/exclusive, protected temporary writes with expected revision checks. Only `FORK_COPY` may allocate a new association for a copied workspace.
6. Finalize the registry and mark/remove the journal only after the binding outcome is known. If interrupted, the journal describes a bounded pending operation and the next inspection returns RECOVERY_REQUIRED (or a safely replayable operation after revalidation); do not mask a partial commit as UNBOUND/READY. Only this operation's own temporary files may be cleaned.
7. For completed `INITIALIZE`, a new local association exists but **no Notes entry**. For `REBIND_MOVE`, the existing collection ID remains. For `FORK_COPY`, a new ID and **empty new scope** are allocated, with the original registry/collection untouched.
8. Never chmod/chown recursively, delete unknown data, reuse an association ID as a credential, or overwrite unknown metadata versions. Return a sanitized outcome and revision for future guarded record operations.

Sidecar and registry live in different trees: filesystem atomic rename does **not** make them a single transaction. The recoverable journal and confirmed teacher conflict choice are part of the contract. Native handle checks and locking details must be proven in Slices 3–6; this document is not such proof.

## 6. Validation and migration discipline

- **S1 D0/D1:** freeze/review the sidecar, owner/local-root, states and #239 handoff; test existing generic marker and capability boundaries. No new file writes.
- **S2:** read-only owner/native private-root inspection; no default creation or capability advertisement.
- **S3:** protected creation and v1 codecs/journal/locks; reject unsupported security; no Note records.
- **S4:** explicit initial binding/reopen; strict owner/registry qualification.
- **S5:** explicit rebind/fork, copy/restore ambiguity and crash recovery.
- **S6:** adversarial symlink, ACL, owner spoof, lock, revision and privacy tests.
- **S7:** isolated installed wheel and actual Windows/Linux security probes, native macOS if available, full CI/installed evidence; tag unqualified gates honestly.

**Migration:** existing workspaces have no private association sidecar and must remain unchanged until the owner explicitly binds them. No upgrade of `.pds/workspace.json`, no automatically invented UUID derived from paths, and no copying old project/producer Notes. Unknown private schema versions must be preserved and refused. Ordinary workspace export/backups **exclude** local Notes. #243 alone owns explicit owner-reviewed portability, provenance and restore conflicts.

## 7. Deferred behavior and open D0 approval

The proposed types/metadata are **not** claimed implemented by their appearance here. D0 approval before Slice 2/3 must confirm exact native lock/descriptor coordination feasibility and whether the documented sidecar can be safely written on the intended district cloud-synced workspace without creating false identity/authorization claims. If not, revise this design deliberately, with a new reviewed decision; never silently weaken collision handling.

Full Notes record semantics are #239, Notes menu/direct CLI #240, portability #243, and final Core/Suite/producer installed qualification #244 and downstream issues. No advertised `notes.records.v1` or runtime Notes feature is permitted from this Slice 1.
