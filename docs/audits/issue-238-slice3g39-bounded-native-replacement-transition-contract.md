# Core #238 · Slice 3G39 · Bounded native replacement transition contract

## Scope and decision

**Status:** Pending native Windows qualification. **Decision:** Add one bounded
synthetic transition classifier using the already-qualified 3G34 canonical
scratch replacement. Do **not** enable any production operation, grant, replay,
journal retirement, durable commit, or Notes access. The 3G38 operation-owned
four-frame boundary remains a no-op; its after-release result is never accepted
as an input to this slice.

The public entry point `rehearse_synthetic_native_replace_transition` accepts
exactly two optional enum arguments: the fixed stage-to-registry step and an
existing 3G34 in-process interruption point. No caller-owned paths, byte images,
intent, filesystem handles, object capabilities, prior reviews or callbacks are
accepted. The only possible replacement is 3G34's internally generated canonical
transaction in its own disposable temporary directory. The wrapper does not
itself call any production filesystem write API.

## Transition classification

- Refuse all other step and interruption types before running an experiment.
- On Windows first conduct a **separate, disposable** 3G24
  `NO_DELETE_SHARE` probe. Its required outcome is a blocked replacement.
  Any refusal, exception, malformed result or unsupported mode fails closed
  **before** calling the canonical scratch replacement.
- On Linux do not claim a Windows sharing proof. Reuse only 3G34's canonical,
  disposable replacement experiment and qualified native parent observations.
- A scheduled interruption **strictly before** the replacement call can be
  classified as pre-attempt. An interruption after the call, an unscheduled
  interruption, or unknown I/O must be treated as **potentially post-attempt**:
  never blind retry, assume rollback, clean up, or retire evidence.
- A successful disposable replacement is classified as
  `SCRATCH_REPLACEMENT_OBSERVED_UNQUALIFIED`, **not** a commit or admission.
  Success with an armed but untriggered injection is a protocol conflict.
- Windows native refusal identifiers 5 (access denied), 32 (sharing violation)
  and 33 (lock violation) are classified *descriptively*; POSIX EACCES/EPERM
  are also recognized. Unknown errno or winerror is not treated as retryable.

Every returned review is frozen, sanitized and includes
`pending_evidence_must_remain=True` and the full 3G35 production write
requirement taxonomy. `replacement_may_have_occurred` is deliberately
conservative, not proof of a successful replacement or an operation token.

## Explicitly unqualified production gates

The independent Windows sharing experiment does not hold a destination HANDLE
for 3G34's subsequent replacement, much less a production registry HANDLE.
3G37's retained stage and registry observations and 3G38's four no-op frames
cannot safely be spliced into a production writer by reusing a returned review.
A future writer needs a **single** operation-owned native scope with verified
ACL, effective owner, path/volume custody, exact preimages and revision,
explicit Windows sharing, truly bounded native replacement, postimage proof,
filesystem-specific directory-entry durability, and crash/restart reconciliation.
A local advisory lock does not exclude an uncooperative same-user writer or
provide cross-machine/OneDrive coordination.

No persistence, stage deletion, journal retirement, automatic replay,
production initialization or Notes activation is introduced in this slice.

## Qualification gates

- Isolated Linux dependency-stub suite: 109 passed; does not substitute for
  Windows-native qualification or full repository type checking.
- Native Windows regression file, then expanded 91-file Core #238 focused suite.
- Repository Ruff lint, Ruff format-check of both Python files, strict mypy.
- Full Core checkpoint deferred (last completed 3G30: 6,191 passed,
  176 skipped), consistent with incremental testing policy.
- Exact 3G38 feature and main refs, all 220 inherited Git blobs, unexpected
  checkout changes, exact three-file additive scope, conditional commit/push.

## Next boundary

3G40 should establish **one bounded operation-owned integration** of native
share-safe replacement with uninterrupted retained custody in *disposable*
storage, before considering any production metadata mutation. Distinguish
observed replacement, ambiguous completion, persistence request, crash replay
and journal retirement as separate qualifications.
