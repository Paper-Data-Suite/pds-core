# Core #238 — 3G81: real-token Windows DACL protected fixture qualification

**Baseline:** `7ecede5068da6a8e687ee3b58307827731b37b6a`, draft PR #247. **Core version:** 0.6.6 candidate, not a new release.

## Decision

3G80 qualified read-only retained-root custody but exercised no actual protected Windows directory in its installed gate. 3G81 qualifies the native retention and owner/DACL checks against four disposable *explicitly secured* directories created by the current Windows process-token SID. The fixture is deliberately **outside** the user's actual `%LOCALAPPDATA%/Paper Data Suite/private/notes` tree. Neither this probe nor Core's public read-only review creates any private store, registry, journal, association, or Notes data.

## Windows-native test sequence

1. Confirm the scratch tree is a distinct child of the requested `scratch-root` outside source checkout; verify that its volume is a fixed NTFS or ReFS drive. Never use or repair an existing protected private-data root.
2. Read the **actual effective process-token SID**, rejecting thread impersonation. Create the four disposable nested `owner/private/notes/v1` directories with explicit inheritance-protected owner/SYSTEM/Administrators full-access DACLs supplied in the **initial** `CreateDirectoryW` security attributes (not an insecure create-then-chmod/set-acl sequence).
3. Check native DACL classification and Core 3G80 `_probe_existing()` twice: require `retained_private_root_observed_unqualified` and no exposed handles, paths, SID, owner ID or write authorization. Retained Windows directory handles undergo a second identity/DACL review before release.
4. Refuse a missing leaf, an intentionally invalid owner SID and a different scratch directory created with a deliberately broad Everyone READ ACE; require `missing`, `owner_unavailable`, `native_protection_refused` respectively. The over-permissive fixture is created with its invalid ACL *at creation*; it is never a PDS private store.
5. Close all handles and delete only the owned disposable fixture with the test's `TemporaryDirectory` context. If cleanup is refused, the qualification fails; no recursively broad permission repair occurs.
6. On Linux, do not create the Windows fixture. Verify no scratch writes and the earlier native Linux qualifications continue independently. Both CI matrix legs run the installed-wheel probe.

## Acceptance and refusal

A full local guarded runner must retain the previous twelve installed-wheel gates, strict Linux and Windows mypy, Ruff and focused pytest; the candidate-wheel probe must verify installed Core origin/version and emit a fixed sanitized evidence schema. All live production-write barriers and the nine readiness gaps remain blocked. An unqualified OS token, unsupported filesystem, creation failure, unexpected owner/DACL, changed native identity or nonlocal scratch **fails the qualification**, not an apparent success or READY state.

No production owner/ACL assertion, session-token binding, file handle, transaction capability or cross-machine proof is exported. No Notes record/menu/CLI, production binding, replay, journal retirement or power-loss durability is authorized.

## Next

3G82 should integrate operation-held OS owner and retained native root evidence into a *non-authorizing* production precondition review, guarded by exact descriptor/registry/journal root identities and canonical current intent. Only a distinct, reviewable production operation may ever be considered for write admission; synthetic fixture success cannot bypass the barrier.

## Slice 3G81 Repair 1 — explicit installed module origin refusal

The stopped local qualification passed 152 focused tests (11 skipped) and Ruff, then strict mypy found two optional `ModuleType.__file__` arguments passed to `Path`. The candidate-wheel provenance check now refuses an absent `__file__` before evaluating either path, preserving the requirement that both modules originate from the isolated wheel installation. Only this source expression and this audit note change. Native Windows token-SID/DACL fixture construction, filesystem custody, tests, and the CI workflow remain unchanged. Repeat Linux and Windows mypy, all focused tests, and all existing installed-wheel gates before commit.

Production binding, Notes, replay, journal retirement, and production mutation authority remain disabled.

## Slice 3G81 CI Repair 2 — hosted Windows scratch backing isolation

GitHub Actions run `43616758310` reached 7,803 passing tests in the Python 3.11 Windows validation job but failed the native fixture check because the hosted runner's `D:` temporary volume was not qualified as fixed NTFS/ReFS. The Windows issue-installed gate was blocked at the same check. This was a **correct fail-closed backing refusal**, not evidence that private-root custody or Windows DACL checks passed in CI.

The fixture now chooses its existing scratch root only if Core's strict fixed NTFS/ReFS test succeeds. Otherwise it may use the *existing* `%LOCALAPPDATA%\Temp` directory under the effective user's home after refusing missing paths, relative or out-of-home paths, symlinks/junctions and unsupported backing. It creates only a unique temporary fixture subtree there with explicit protected DACL children; it does not create a parent, weaken `_known_fixed_local_volume`, edit ACLs on existing objects, access live PDS private storage, or promote synthetic evidence into production admission. If neither location qualifies, the gate must still **fail closed**.

Both the full Windows validation matrix and the installed Windows fixture must pass after this repair before proceeding to 3G82. No production binding, transaction replay, journal retirement or Notes activation is admitted.

## Slice 3G81 CI Repair 5 — formatting-agnostic native containment test

After CI Guard Repair 4 correctly verified the committed baseline and applied the fixture-only fixed NTFS/ReFS fallback, the focused pytest run failed because a test compared a single-line source-code string against a Ruff-formatted multi-line containment expression. The native check itself remains a strict `!=` comparison. This repair removes the brittle string-match member and asserts that the parsed Python AST contains exactly the `base.parent.resolve(strict=True) != selected.resolve(strict=True)` comparison. Neither the fixture implementation, the retained custody module, the production preconditions, nor CI is changed. Full original 3G81 qualification and thirteen isolated installed-wheel checks remain mandatory before commit/push.

Production binding, replay, journal retirement, and Notes activation remain disabled.
