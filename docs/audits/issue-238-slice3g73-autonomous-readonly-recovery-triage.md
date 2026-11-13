# Core #238 — Slice 3G73: independent checkpoint inference, non-authorizing

## Exact baseline and acceptance

- Baseline: `d34052750364f1b0d54ce092c510a149202fc706` (3G72), draft PR #247.
- 3G72 workflow `43137660940` passed 15/15 jobs on Windows and Ubuntu; the installed-wheel fresh-process checker independently reopened the canonical pending-journal states.
- This slice does **not** trust a supplied `prepared`/`registry`/`both` state in the restart reader. It asks the existing strict 3G72 reader to validate **each candidate** from actual synthetic bytes, exact namespace, native file identities and preserved pending journal; a unique success is a bounded *HOLD* classification, never replay authority.

## Scope and test matrix

Four files only: new `scripts/verify_issue238_installed_recovery_triage.py`, focused `tests/test_teacher_private_installed_recovery_triage_3g73.py`, this audit, and one #238 installed-wheel CI step and sanitized artifact. Existing production modules and test skips are unchanged.

Within the isolated installed candidate wheel and fresh scratch roots, generate three canonical `FORK_COPY` states with actual one/two native replacements. A separately launched Python interpreter (`-I`) infers each checkpoint without a claimed phase:

1. `prepared_hold`: pending journal, both original documents and stages.
2. `registry_after_descriptor_pending_hold`: registry replaced; descriptor stage remains; journal pending.
3. `both_after_journal_pending_hold`: both documents replaced; journal remains pending.

Three more independent scratch roots inject **only** (a) an invalid journal, (b) an unexpected namespace entry, or (c) a mutated descriptor. The fresh reader must return `conflict_preserve` and must not modify or retire anything. All controls must preserve exact synthetic bytes and refuse ambiguous matches.

The child accepts no caller-supplied state. It can only read its designated new `core238_3g73_` scratch root, load canonical fixed synthetic fixtures, verify installed-wheel provenance, and check the permanent production barrier. The entire report contains only enum labels, platform, candidate-wheel hash, and false security/commit claims; no paths, principal data, journal bytes or native identifiers.

## Qualification

Guard exact baseline HEAD, remote and CI blob, plus a clean worktree. Run focused tests, Ruff, both strict mypy platforms, build isolated wheel from a tracked checkout archive, re-run all four prior installed verifiers, then new six-interpreter recovery triage. Compare bounded evidence before committing exactly four files and pushing. Windows and Ubuntu CI must pass independently.

## Explicit limits and continuation

`conflict_preserve` is a refusal, **not** automatic rollback or replay. This remains an advisory read-only scratch classifier: no real protected private-root execution, OS-owner/ACL admission for production, multi-file atomicity, power-loss durability, journal-retirement protocol, READY storage handle, or Notes capability is established. Keep the PR draft and the production barrier in force. The next stage must establish a complete *operation-owned native recovery scope*, with retained locks, exact intent, persistence-order and collision refusal, before considering any production mutation.
