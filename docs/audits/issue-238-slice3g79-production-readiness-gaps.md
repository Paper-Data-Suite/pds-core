# Core #238 — Slice 3G79: production-native readiness blockers

**Baseline:** `7296dfd1acca57548c17f36ad4c570aedc54171c` (3G78 Repair 1), draft PR #247. Previous installed-wheel no-write and nine scratch gates passed locally. 3G78 CI must pass independently before this source is accepted.

## Decision: stop interpreting synthetic coverage as production readiness

Core's `_teacher_private_recovery_production_write_barrier._REQUIRED` has **nine independent requirements**. A successful OS-local *observation* does not discharge any requirement: it is a released snapshot, not a continuously held production writer. Readiness must never be inferred from the cumulative number of passing scratch scenarios. Implement a versioned, fail-closed internal readiness review and an installed-wheel CI sentinel. The sentinel does not create a new API/capability or a write permit.

## Technical gap matrix and implementation sequence

| Barrier requirement | Current relevant evidence | Missing proof before production admission |
| --- | --- | --- |
| `effective_os_owner_and_private_acl` | Read-only OS-token/EUID and native root preflight; protected child primitives exist | A real, qualified owner-private root, stable DACL/ACL validation *inside the mutation guard*, secure creation/verification of complete tree and files |
| `workspace_descriptor_binding` | Validated descriptor codecs, private registry and observation stages | Deliberate first binding/rebind/fork decision committed against actual protected owner and workspace, with safe cross-tree consistency |
| `two_root_native_parent_custody` | Synthetic four-parent and stage handle custody on Windows/Linux | Stable native handles for the actual local registry and the actual workspace's `.pds` descriptor roots, with unsupported cloud/share behavior refused |
| `exclusive_operation_owned_guard` | Synthetic cooperative lock, reacquisition and cross-process contention | Production scoped lock lifetime, replacement-resistant namespace, cross-user and noncooperating interference policy |
| `canonical_intent_recheck_in_guard` | Strict versioned metadata and canonical synthetic FORK_COPY | Actual owner/workspace-bound transaction intent and current revision verified under one operation-owned guard |
| `exact_registry_journal_stage_images` | Exact synthetic journal/stage/native identity checks | Secure first-time journal and stage creation, retained exact bytes, collision handling in the real protected location |
| `native_replace_sharing_and_postimage` | Installed native Windows FileRenameInfoEx and POSIX scratch replacement | Guarded real-path single-attempt write sequence, cross-version/share-denial behavior and unknown-result preservation |
| `directory_durability_and_crash_recovery` | File and parent flush requests; process death without power loss | Platform-supported persistence ordering and a documented power-loss durability boundary; Windows directory flush can refuse |
| `recovery_and_journal_retirement_protocol` | Repeated synthetic interruption/convergence and journal preservation | Production-safe pending-journal triage, human decision boundary, safe recovery/commit marker, independently proven retirement protocol |

**Suggested implementation order:** (1) qualify actual owner/private root custody and workspace descriptor under explicit local-only support; (2) implement production-scoped first binding with exact pre/postimage and journal protocol, while replay remains off; (3) qualify directory persistence, production recovery and retirement separately; (4) expose only the authorized private handle contract after the full barrier can be replaced. Linux and Windows require independent native CI; macOS remains unqualified until tested.

## Changed files and acceptance

- New *internal* `pds_core/_teacher_private_production_readiness.py`: parameterless, sanitized OS-owner and native-root observation, immutable nine-item gap list, no readiness/handle/owner/path export. A change to barrier requirements fails closed pending deliberate review.
- New `scripts/verify_issue238_installed_production_readiness.py`: verifies isolated candidate-wheel provenance, the real canonical synthetic production barrier decision, expected capability set and nine blocked requirements. Emits only controlled enum values/booleans and wheel digest.
- New `tests/test_teacher_private_production_readiness_3g79.py`: real non-authorizing read-only check, positive/negative probe simulations, requirement drift refusal and serialized-owner/path non-disclosure.
- Add an installed-wheel CI step and sanitized artifact to the existing `issue238-installed-native-boundary` Windows/Linux matrix. Existing ten installed gates remain untouched.

**No transition from blocked to ready is implemented.** The script intentionally does not probe a caller-supplied path or create files. Its report supports engineering sequencing, **not** security certification, power-loss durability, Notes service activation, replay, journal retirement or published 0.6.6 behavior. Keep #238 open and PR #247 draft.
