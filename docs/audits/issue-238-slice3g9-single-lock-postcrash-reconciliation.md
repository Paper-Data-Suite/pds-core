# Core #238 — Slice 3G9: single-lock post-crash pending-registry reconciliation

**Baseline:** qualified 3G8 `14cb79835bfe346c2088ab3a8cceb8983ec5a933`.

## Change

A new strictly internal, read-only `reconcile_native_private_pending_registry_after_interruption()` observation combines the previously independent native stage-present 3G2 and stage-absent 3G4 readers. Unlike two consecutive public checkpoints, it uses **one** existing retained descriptor/registry/journal guard, the existing two local ordered locks, and one effective owner throughout the complete review. It first verifies the canonical non-INITIALIZE transaction intent. Under the retained scope it observes both complete transaction/stage namespaces, demands exactly the canonical transaction journal, and permits only zero stage entries or the exact proposed stage entry.

The native inventory must independently agree on whether the stage exists, before and after the byte-image review. For a present stage, the already-qualified 3G2 native `_review_images()` proves matching journal, stage after-image, descriptor and registry before/after metadata; for an absent stage, the existing 3G4 native `_images()` proves the symmetric byte evidence and classifies whether the registry or both metadata files already match the proposed after-image. Neither helper reacquires ordered locks. Finally the entry census, stage inventory, owner and retained handles must still agree, including when a helper reports failure. Any conflict is an explicit sanitized refusal; an ordinary data-race ambiguity cannot authorize a repair.

## Recovery observations / deliberately absent authorities

| Native stage | Metadata checkpoint | 3G9 advisory state | Required treatment |
| --- | --- | --- | --- |
| Exactly one proposed stage | Exact prepared before-images | `STAGED_BEFORE_REVIEW_REQUIRED` | Preserve stage and journal; admission/replay not authorized |
| Exactly one proposed stage | Another internally consistent checkpoint | `STAGE_REMAINS_OTHER_CHECKPOINT_REVIEW_REQUIRED` | Preserve every artifact; resolve competing stage lifecycle |
| No stage | Registry after, descriptor before | `REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED` | Preserve journal; descriptor/durability remain unresolved |
| No stage | Registry and descriptor after | `BOTH_AFTER_JOURNAL_PENDING_REVIEW_REQUIRED` | Preserve journal; **not** permission to retire |
| No stage | Registry before, or descriptor-only | Explicit stage-missing refusal | Preserve evidence; no reconstructed or auto-generated identity |
| Either | Changed/unqualified bytes, foreign stage, inconsistent inventory, owner or guard | Sanitized refusal | No mutation, no silent empty collection, no retry |

**Persistence claims:** File flush observed in 3G7 and directory probe in 3G8 are historical advisory states, not proof of rename ordering, file-system crash durability, successful replay, or multi-file atomicity. 3G9 does not consume or inherit these observations as write authority and cannot infer that an absent stage was consumed by the intended rename rather than removed for another reason.

**No writes:** No registry/descriptor/journal/stage creation, rename, deletion, repair, cleanup, lock creation, Notes record, CLI, capability advertisement, public action or export. This module returns only a frozen enum and sanitized message. Even the most favorable observation is **not** authorization to bind, replay, accept a teacher decision, retire the journal or open Notes.

## Qualification

The synthetic test matrix covers stage-present/absent classification, missing stage, foreign and changed namespace, owner drift, inventory disagreement, invalid input, guard refusal and exit-time drift. The runner demands an exact clean qualified 3G8 checkout, the unchanged GitHub feature/main remote heads and all 130 inherited source blobs. It Ruff-formats and lints both Python files *before* application. It then runs the new tests, focused Core #238 test selection, Ruff lint/format, strict mypy, and full Core pytest before staging exactly three additive files and conditionally committing/pushing.

Tests using mocked native readers verify control flow, not OS access protection. A real Windows/Linux qualified teacher-private fixture and forced process crash/fault-injection acceptance are separate pending gates. macOS remains unsupported, as do network/cloud storage guarantees. The next mutation boundary is an explicitly teacher-approved, crash-recoverable coordinator with a defined write sequence; these read-only results must never be treated as its transaction-commit token.
