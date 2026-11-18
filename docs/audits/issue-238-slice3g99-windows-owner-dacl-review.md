# Core #238 — Slice 3G99: Windows process-token SID and native DACL control, scratch only

## Trust boundary and concrete motivation

3G98 qualified synthetic two-root association and POSIX owner/mode refusal, but
correctly left Windows ACL security unqualified. 3G99 inspects a **native
Windows process-token SID**, opened-directory-handle owner SID, Windows DACL
ACE classification and `SE_DACL_PROTECTED` descriptor control on a freshly
created, disposable fixture. Windows security descriptors can have the same
visible owner/allow ACEs but different inheritance-protection flags, so a
simple ACE scan is insufficient evidence even for a deliberately restrictive
scratch fixture. The probe refuses unsupported platforms before creating any
fixture, rejects thread impersonation through Core's existing owner helper,
and does not disclose token SIDs, paths, ACLs, handles or sensitive data.

## Exact fixed Windows cases

| Scenario | Synthetic evidence | Result |
| --- | --- | --- |
| `protected_owner` | Native protected owner/SYSTEM/Administrators DACL; owner matches effective token SID | `protected_dacl_shape_observed_hold` |
| `unprotected_dacl` | Equivalent explicit ACE set without `SE_DACL_PROTECTED` | `unprotected_dacl_refused` |
| `everyone_read_dacl` | Protected owner DACL with extra Everyone READ ACE | `everyone_access_refused` |
| `spoofed_owner` | Real protected fixture, but native DACL classifier receives an intentionally wrong expected owner SID | `owner_mismatch_refused` |
| `missing_child` | Absent disposable child; no ACL creation | `missing_child_refused` |

The diagnostic creates **only** its own temporary test-root children. Native
`CreateDirectoryW` receives explicit security attributes on the first call;
no post-creation permission widening or repairs occur. Parent temp backing is
restricted to supported fixed local NTFS/ReFS, with a bounded fallback to an
already-existing user-local TEMP folder as in 3G81. A native opened directory
handle supplies security descriptor data via `GetSecurityInfo`; the additional
`GetSecurityDescriptorControl` check verifies whether the DACL is protected.
The existing Core `GetAce`-based whitelist classifier is independently applied
and must refuse Everyone and forged-owner cases. Token identity is checked
again while the opened handle is held.

## Explicit limitations

- `protected_dacl_shape_observed_hold` means the **scratch** DACL structure,
  owner and inheritance-control flag met this narrow native check. It is not a
  Windows `AccessCheck`/`AuthzAccessCheck` computation for every possible
  user/group token; rights via arbitrary token groups, mandatory integrity,
  privileges, conditional ACEs and inherited access are not comprehensively
  qualified. `windows_effective_access_qualified` stays false.
- This exercise does not validate the actual `%LOCALAPPDATA%` Notes path,
  parent-handle continuity for the real workspace/private two roots, the
  write-operation's effective token over time, or cross-process kernel-native
  security isolation. A controlled test fixture is not a production root.
- Windows administrators and SYSTEM remain inside the OS trust boundary. The
  same OS-user's hostile processes and crash durability are not covered.
- All nine production readiness requirements, the terminal-only capability set,
  the no-binding/no-Notes barrier, no-auto-replay and no-journal-retirement
  restrictions remain unchanged.

## Qualification and next gate

Thirteen focused source tests cover five native scenarios (Linux refusal),
five malformed requests, requirement drift, unsupported-platform refusal and
narrow API/capability invariants. The **31st** installed-wheel gate verifies
candidate wheel origin, every fixed scenario, sanitized evidence and all
negative production capabilities. The first thirty gates remain unchanged.
Guarded qualification requires the exact accepted 3G98 Repair 1 baseline,
remote SHA, committed CI blob, pristine worktree, Python syntax, Ruff, strict
mypy for both OS targets, focused regressions, full installed-wheel provenance
and conditional exact-scope commit/push.

Next: integrate the native owner/ACL observation with retained two-root
handles and the full explicit binding decision *without* authorizing a real
mutation until security and transaction durability criteria are independently
qualified.

## Slice 3G99 Repair 1 — deterministic unprotected-DACL negative fixture

The first native Windows qualification (against accepted 3G98 baseline) passed
its `protected_owner` test but returned the sanitized
`scratch_custody_refused` state for the `unprotected_dacl` case. Because the
existing result intentionally does not disclose native security metadata, the
specific failing Win32 call or returned protection bit was not proven by that
log. In particular, authoring an unprotected SDDL string at CreateDirectoryW
is not sufficient to prove the resulting on-disk DACL control state.

The negative fixture now creates its target with the existing explicit owner,
SYSTEM and Administrators **protected** DACL at birth, then opens only this
newly allocated disposable child with READ_CONTROL and WRITE_DAC. It reads the
actual DACL via GetSecurityInfo and calls SetSecurityInfo with both
DACL_SECURITY_INFORMATION (0x4) and
UNPROTECTED_DACL_SECURITY_INFORMATION (0x20000000), using the **nonnull**
previously read DACL. It reopens the native security descriptor through the
retained handle and requires both matching process-token owner SID and
SE_DACL_PROTECTED **clear**. Failure to create, query, change or confirm the
native security descriptor remains an explicit scratch custody refusal; no
unqualified Windows ACL is mislabeled a valid negative control.

This is a deliberately less restrictive negative control exclusively under a
TemporaryDirectory that the probe created; it is not used for production
private-root creation, protection repair or writes. No identity, native handle,
actual DACL, temporary path, automatic replay or binding authority escapes.
The 3G99 public scenario names, source test expectations, 31st installed-wheel
verifier and CI insertion are unchanged. The original full qualification
runner must still pass pytest, Ruff, both strict mypy platforms, all 31
installed-wheel gates and conditional exact-scope commit/push. Synthetic
process death and ACL shape are not substitutes for native effective-access
checks or an authorized durable two-root binding. All nine production blockers
remain in force.
