# Teacher-private Notes storage — threat model and supported-security boundary

**Authority:** Core #238 / parent #235; accepted teacher-experience contract v1 and Suite decisions D-02/D-03.
**Lifecycle:** Slice 1 design candidate, to be approved at D0 **before** any real private-store creation.
**Data:** future personal Idea / Task / Reflection bodies and any associated optional non-student context. #238 itself does **not** persist Note records.

## Security goal and actual trust boundary

A Notes collection is **one logical workspace association under one qualified local operating-system account**, stored in OS-user-protected local application data. An application label, `TeacherContextHint`, self-declared `actor_reference`, note author string, process working directory or sidecar UUID **is not authentication**. A sidecar is public, copyable association metadata; the private registry and eventual records are never automatically shared with it.

The store protects against accidental cross-workspace disclosure and unauthorized ordinary *other-OS-user* access on local filesystems for which the implementation has verified OS protections. It cannot isolate two teachers who share a single OS login; it does not protect against malware running as the same account or against OS administrators/root. It is not end-to-end encrypted, cloud-synced, a secret vault, a tamperproof audit service, or a cross-device backup mechanism.

## Assets, surfaces and actors

- **Assets:** future note text, category and private Task state; non-secret association descriptor; private owner/binding registry; any future private metadata or index; diagnosis/restore receipts.
- **Entry points:** explicit workspace paths/config/env; OS-user-local data path derivation; workspace sidecar and private registry JSON; filesystem rename/move/copy/sync/restore; multiple Core processes; future Core Notes menus/CLI; future #239 record service.
- **Trusted authority (only when verified):** operating-system effective process security context; filesystem ownership, effective discretionary ACL/mode/ACL entries; qualified native locks and checked file handles; Core-owned guarded service code.
- **Untrusted inputs:** producer/Suite hints; actor/display labels; class/work names; user-edited JSON; arbitrary paths and env vars; cloud-synced sidecar; prior path/object IDs; serialized data from an earlier machine or OS principal; caller-confirmation text.

## Threats, required controls, refusal behavior

| Threat / case | Required mitigation | Fail-closed / residual limitation |
| --- | --- | --- |
| Actor-label spoofing under one OS account (P01) | Scope is derived from effective OS principal and verified private root, never actor label | Same OS login remains **one** security principal, not two isolated teachers |
| Different OS users or inherited world-readable data (P02) | Check native process identity and effective private-directory/file protections, not merely pathname or home-directory ownership | Deny access if effective ACL/UID checks cannot establish protection; administrators/root remain trusted OS exceptions |
| Windows copied folder, unsafe inherited DACL, reparse point | Use token SID and native ACL/security descriptor/ancestor/reparse inspection; refuse cross-account allowances | Python `os.access` or `Path.resolve` alone is insufficient; do not silently fix arbitrary ACLs |
| POSIX permissive mode, foreign UID, ACL grant, symlink in ancestry | Native effective UID, owner, mode 0700 directories / 0600 files, ACL-aware checks as available, no traversal on untrusted link | Deny when ACL/mount semantics cannot be verified; do not recurse through/chmod unrelated user files |
| Cloud/network-backed **private** root | Validate actual backing/security assumptions, not only `%LOCALAPPDATA%`/XDG variable text | Refuse unsupported remote, removable or cloud-protected private storage without qualified guarantee |
| Cloud-synced **workspace** and copied sidecar (P03) | Sidecar ID needs owner-private registry confirmation and explicit move/fork decision; notes bytes stay local | Synced workspace alone cannot restore, import or authorize local Notes; second device needs explicit review |
| Same association ID appears at second live root | Registry detects conflict; no auto-share or implicit move | Report `CONFLICT`; explicit fork creates new UUID and new empty local scope; never copies records |
| Original path missing, clone vs move ambiguous | Require explicit rebind review and fresh-state verification; treat file IDs as supplemental | Cannot cryptographically prove a move on cloud/network/restore; decision is teacher-reviewed |
| Registry missing while descriptor exists, or partial transaction | Recoverable journal/intention markers with exact operation/revision; never silently initialize a new ID | `RECOVERY_REQUIRED`/`CORRUPT_METADATA` until approved recovery; retain evidence and existing data |
| Competing processes or stale selection | Owner-private registry lock plus independently guarded descriptor commit, expected revision and repeated identity/protection check | On unsupported cross-process locking or conflicting states, return `STALE_STATE` or refuse; no optimistic overwrite |
| Path traversal, link/junction swap, hardlink alias | Reject bad components; use native handle-/descriptor-based checking and no-follow/exclusive operations where supported | TOCTOU cannot be dismissed by one `Path.resolve()`; refuse if adequate primitives unavailable |
| Malformed/oversized/unexpected-schema JSON | Bounded UTF-8 parsing, exact schema keys and types, size limits, UUID format, rejects invalid controls and future versions | `CORRUPT_METADATA`; do not overwrite future schema data or mask it as empty |
| Sensitive bodies, student references, secret exception text in logs (P05) | Minimal non-sensitive sidecar and private binding data; structured sanitized error codes; no note text or raw user paths in default logs/CI | Free text under #239 may contain sensitive data even without structured student links |
| Workspace backup/export (P08–P09) | Document private app-data exclusion; #243 defines explicit reviewed export, integrity and conflicts | Whole-workspace backups **do not** include Notes; no portability/synchronization promised |
| Import-time implicit creation or unreviewed menu opening | Side-effect-free imports, pure read-only inspection, explicit confirmed operations | No Note record or capability advertised from #238 alone |

## Platform protection qualification checklist

| Platform | User-local preference | Native evidence required before D2 qualification |
| --- | --- | --- |
| Windows | `%LOCALAPPDATA%\Paper Data Suite\private\notes\v1` | Actual current process token SID; SID/ACL evaluation for folder and files, inherited ACE checks, reparse traversal protection; native Windows tests (including limited-rights account where feasible). SYSTEM/admin access is normal privileged OS power. |
| macOS | `~/Library/Application Support/Paper Data Suite/private/notes/v1` | Effective UID ownership, restrictive 0700/0600 protections, ACL and symlink checks, local filesystem assumptions and **native macOS evidence**. Until native tests exist, mark unqualified rather than infer from Linux. |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/paper-data-suite/private/notes/v1` | Absolute validated local XDG root; effective UID, 0700/0600, effective ACL, symlink and mount constraints; native Linux tests. |

Environment variables locate candidate data; **they do not confer permission or identity**. If any required native owner/access/mount probe is unavailable or inconclusive, deny private-store mutation rather than fall back to a permissive store.

## Metadata and diagnostic minimization

The workspace sidecar may carry a schema/version and a generated high-entropy association ID, but no person, organization, class, student, note, token or private path. The owner-local registry may contain OS-principal ID and accepted location evidence because its directory is protected. These never appear in normal error strings, CI artifacts or telemetry. Diagnostics use only bounded status codes and generic recovery guidance by default. Do not serialize source exception tracebacks with user paths/identifiers into persistent logs.

Use only synthetic fixtures (`synthetic_workspace_a`, `synthetic_workspace_b`) and fake identity/permission providers **inside deterministic tests**. Native installed-wheel acceptance in Slice 7 must supplement, never substitute with, those fakes.

## Fail-safe lifecycle rules

1. **Inspect:** must neither initialize missing directories/sidecars nor report unbound storage as an empty existing collection.
2. **Plan:** resolves proposed action, checks state and presents a bounded decision without a lasting write; outputs revision guards, not capability to read private records.
3. **Commit:** verifies effective principal and permissions again; holds cross-process locks, checks expected descriptor/registry revisions, creates privately protected metadata with exclusive or atomic operations; partial transactions leave explicit recoverable state. Never recursively delete data on failed recovery.
4. **Reopen:** returns READY only for verified, current association, owner and binding; sidecar alone never suffices.
5. **Move/rebind:** preserves ID after explicit teacher review and collision check; **fork** allocates a new independent ID and creates no copy of prior Notes records.
6. **Corruption/security failure:** no implicit reset, fallback to another teacher's scope, alias by similar path, or blanket ACL repair. Return a reason and controlled next action.

## Separate follow-up ownership

Core #239 implements actual protected Notes records, revision/atomic updates and free-text validation on this qualified foundation; #240 owns menus and CLI; #243 owns explicit private backup/transfer/recovery; #244 and Suite/producer owners qualify integrated/physical experiences. Existing published Core 0.6.6 and actual downstream users gain no Notes capability from a design document or unqualified candidate branch.
