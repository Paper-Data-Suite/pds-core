# Core #238 — Slice 3G87: retained-native writer window, disposable only

## Security boundary

3G86 proved a separate-file cooperative lock cannot exclude an uncooperative
writer. 3G87 builds a *disposable* native writer-window demonstration, **not**
a production writer. The only public diagnostic input is one of three fixed
scenario enums. It generates its own random OS temp directory and accepts no
caller paths, transaction bytes, workspace descriptor, registry or callback.

## Operation-owned scratch sequence

Under one held OS coordination lock and retained native parent directory
identity, the diagnostic reads a synthetic journal, live registry and staged
registry. It then rechecks both exact byte images before a single replacement.
The success case verifies exact after-image, disappearance of staged source,
preservation of the pending journal and parent identity while still within the
same held context. In two negative cases it induces live-preimage or stage
drift, observes the discrepancy inside the guard and **refuses without calling
replace**. Synthetic files are only created and cleaned up in the diagnostic's
own temporary directory. The Linux version retains a native directory FD; the
Windows version retains a real directory HANDLE and reopens the current path
for native file identity checks. No source / destination in the live Core
private root or a real teacher workspace is accessible through this interface.

## Nonclaims

The diagnostic uses path-based `os.replace` and has no atomic content compare-
and-swap. It cannot exclude malware or noncooperative same-user replacement;
3G86's counterexample remains valid. A successful synthetic replacement does
not establish real OS owner/ACL protection, current workspace association,
secure parent-to-child handle-relative Windows replacement, two-root transaction
atomicity, power-loss durability, crash recovery, journal retirement, or record
service readiness. All nine production write requirements remain unqualified.
No first-time binding, replay or Notes activation is authorized.

## Qualification

The new source tests cover exact-window success, two drift refusals, invalid
scenario, inventory drift and the negative capability boundary. A nineteenth
independent installed-wheel native gate repeats all three scratch scenarios in
an isolated installed interpreter on Windows and Linux. The report contains only
fixed sanitized predicates, platform, package version and candidate-wheel hash.
The runner preserves all 18 previous gates, validates the clean baseline and
staged five-file scope, and commits/pushes only after full qualification passes.

## Next

Confront the actual TOCTOU gap in path-based replacement: design a dedicated
native handle-relative/conditional replacement protocol and qualified recovery
checkpoint for each supported OS. Do not reclassify this disposable demonstration
as production authorization or imply the OS can defend against hostile code
running as the same owner.

## Slice 3G87 Repair 1 — cross-platform strict mypy of Windows-only loader

Windows local qualification stopped **before wheel gates or commit** after 75
focused tests, Ruff lint and format passed. Linux-targeted strict mypy rejected
`ctypes.WinDLL` as a missing attribute on non-Windows ctypes type stubs. Both
Windows-only loader occurrences now use the dynamically resolved expression
`getattr(ctypes, "WinDLL")` inside the pre-existing `sys.platform == "win32"`
branches. This is a **typing-only name-resolution repair**: on Windows it
retrieves and invokes exactly the same `ctypes.WinDLL` factory, with the same
`kernel32` arguments and native handle lifetime. It adds no Linux invocation,
writer entry point, actor authority, fallback, record service or private write.

Original scenario tests, installed-wheel verifier and all nineteen CI native
gates remain unchanged. The guarded repair verifies the exact stopped five-file
worktree, modifies only this module and this append-only audit, then reruns
original focused tests, Ruff, strict Linux/Windows mypy and all nineteen
installed-wheel checks before an exact-scope conditional commit/push. The nine
production-operation requirements remain unqualified; production binding,
replay, journal retirement and Notes stay blocked.
