# Core #249 — Exact-owner provider diagnosis (source candidate)

**Scope:** additive public Core API to unblock Suite [#21](https://github.com/Paper-Data-Suite/pds-paper-data-suite/issues/21). **Status: source implemented, focused Windows/source and official wheel qualification pending.** Nothing in Core v0.6.6's existing official release wheel has changed.

## Public entry point

`pds_core.provider_diagnostics.diagnose_selected_core_provider(`, with required keyword arguments:

- `provider_kind: ProviderKind` — one Core public provider kind; Suite uses `"module_operations"`.
- `entry_point_name: str` — lowercase exact Core provider identity, e.g. `"scoreform"`.
- `expected_distribution: str` — exact intended installed distribution name, e.g. `"scoreform"` or `"pds-concord"`.

Returns **one** existing `ProviderDiagnosticResult`, including `validated_profile` only when the Core contract/identity/version checks succeed. Does **not** call `invoke_module_attention`, activate a capability, or evaluate a school workspace.

### Pre-load selection ordering

1. Reject unsupported provider kind, invalid selected identity or malformed expected distribution with a static `ProviderDiagnosticRequestError`. No metadata lookup or producer code execution.
2. Enumerate **metadata only** for that Core provider group through existing `_enumerate_provider_candidates`; metadata enumeration exceptions remain redacted `ProviderEnumerationError`.
3. Compare names **before** loading any candidate, rejecting missing identity or more than one candidate advertised under the selected name (including a foreign duplicate, even if another entry point is valid). A `str` subclass name is not a trusted exact selected identity.
4. On one selected candidate, reject absent/malformed declared owner distribution, wrong distribution (PEP 503 normalization only), absent/oversized/unsafe entry-point target metadata. No candidate is loaded for any refusal.
5. Delegate **only** the one selected candidate to Core's existing `_diagnose_candidate` (as an internal implementation detail **inside Core**). Preserve its profile validation, exact module identity, supported active contract and fixed, privacy-safe exception boundaries.
6. Return one structured diagnostic. Other candidates' `.load()` and profile factories are never invoked, even when their metadata are present. No caching or persistence.

### New bounded diagnostic codes

`provider.entry_point_missing`, `provider.entry_point_ambiguous`, `provider.metadata_invalid`, `provider.distribution_mismatch` supplement existing `provider.valid`, `provider.load_failed`, `provider.call_failed`, `provider.profile_invalid`, `provider.identity_mismatch`, `provider.core_incompatible` and other existing codes.

This is **not** a new registry, loader, profile, provider protocol, wheel-origin attestation or sandbox. An unselected provider with a different advertised entry-point identity might return a conflicting module ID if executed later; that claim is unknowable without running it. It cannot be treated as a validated duplicate and **must not be run merely for conflict discovery**. A different entry point sharing the *selected advertised identity* is rejected before loading.

The existing broad `diagnose_core_providers` and metadata-only `inspect_core_provider_entry_points` remain unchanged and supported.

## Security and consumer separation

A public `ProviderDiagnosticResult(code="provider.valid")` only proves that the **selected loaded profile** passed Core's current contract. It does **not** prove that the installed wheel bytes match a released official artifact, that the publisher is authentic, that the teacher selected the correct workspace/year/class, that callbacks are read-only, or that a module action may execute. Suite must enforce its separate SHA-pinned official-wheel and installed-code evidence, workspace authorization, label privacy and read-only callback gates. **Do not consume source-only Core #249 as an installed release.**

## Focused synthetic acceptance

`tests/test_issue249_scoped_provider_diagnosis.py` covers:

- A selected healthy provider surrounded by three foreign/unselected candidates, including one whose loader would fail with a private secret: only selected factory loads.
- Duplicate selected advertised entry-point names, including mixed owner and `str` subclass duplicate, rejected *before* either candidate loads.
- Missing identity, missing/foreign/malformed owner, malformed/oversized target, bad user-supplied identity/distribution, metadata enumeration exception, and PEP 503 normalized expected owner.
- Selected load crash, noncallable target, factory crash, invalid/wrong-owner/incompatible profile, fixed message redaction.
- Separate attention capability not invoked by diagnosis; it only runs under a later explicit Core `invoke_module_attention`.
- Independent healthy owner still selectable after another explicitly selected owner fails.
- Existing broad diagnostic retains previous multi-candidate semantics.

### Local qualification (Core repository branch)

Use a separate worktree or checked-out clean branch `249-exact-owner-provider-diagnosis`; leave Core #238's active working tree alone.

```powershell
& {
    $ErrorActionPreference = "Stop"
    python -m pytest -q -ra `
        tests/test_issue249_scoped_provider_diagnosis.py `
        tests/test_provider_diagnostics.py `
        tests/test_module_operations.py
    if ($LASTEXITCODE -ne 0) { throw "Focused Core tests failed." }

    python -m ruff check `
        pds_core/provider_diagnostics.py `
        tests/test_issue249_scoped_provider_diagnosis.py
    if ($LASTEXITCODE -ne 0) { throw "Core Ruff failed." }

    python -m mypy pds_core/provider_diagnostics.py
    if ($LASTEXITCODE -ne 0) { throw "Core mypy failed." }
}
```

After source qualification, separately build, hash, test and release a new official Core wheel in accordance with Core's release process. Re-pin Suite #21 official release evidence **only after** publication/installed acceptance. No merge, release, Suite callback or teacher-production integration is authorized by this source branch.
