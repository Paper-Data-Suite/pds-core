# Core #238 — Slice 3G46: one-shot disposable native execution integration

**Feature baseline:** `aa72beecf0a18462d57a1998fbd68d067bb2914c` (3G45).
**Main baseline:** `a0d5e1a50580bbe025f0cad23c7e8524203a52ec`.
**Scope:** additive internal scratch-only implementation, matching tests and this audit.
**Owner:** Core. No Suite, Notes, roster or producer integration changes.

## Gap addressed

3G44 retained protected original registry and staged-file handles with a one-shot
attempt marker. 3G45 combined that custody with canonical *pre-attempt* evidence,
but intentionally kept the attempt marker unset. This slice exercises the actual
`mark_attempt` → **one** native `os.replace` → postimage → guard-release sequence
only on internally generated, canonical, disposable fixture files. Unlike a
pure classifier, the code reaches an actual native replacement system call.

## Bounded execution and expected refusals

* No caller-supplied root, bytes, witness, file name, owner, callback, native
  handle or previously returned review can enter the implementation. A fixed
  canonical synthetic intent is generated in-process by Core.
* A new `TemporaryDirectory` contains the registry, stage, pending journal and
  workspace descriptor. These are not real private user/teacher data, nor is
  the temporary directory claimed to satisfy production root semantics.
* The existing scratch advisory lock is held before the existing 3G44
  `_held_one_shot_transition_pair` native retained-handle scope opens. Both
  old registry and stage identities remain retained over the only attempted
  replacement, and the terminal check occurs before handle release.
* Registry, stage, journal and descriptor exact synthetic images are checked
  before and after. Native identity distinguishes original registry and
  stage-installed registry. Neither ordinary bytes nor the attempt marker
  are a write capability for a real teacher-private root.
* An interruption or I/O error after `mark_attempt` is classified as
  `POST_ATTEMPT_UNKNOWN_PRESERVE`, **including a native refusal**: no automatic
  retry. This is intentionally conservative. A pre-mark interruption cannot
  be mistaken for an attempted rename. A held-scope release failure after a
  replacement also remains ambiguous.
* Scratch cleanup occurs when the disposable context exits. The word
  `PRESERVE` in a state is a policy instruction **for eventual production
  recovery**, not a claim that this temporary test data is retained.
* Windows inherited ACLs on the temporary scratch directory may fail native
  protection verification. `NATIVE_CUSTODY_REFUSED` is a valid fail-closed
  diagnostic; a native Windows success is not assumed merely because isolated
  Python stubs pass. POSIX owner/root limitations can likewise refuse.

## Qualification

The additive test file exercises a real temporary-file rename inside an
**isolated fake native custody** to verify control flow, marker lifetime,
exact images, interrupted attempt classification, no retries, and refusal
paths. A separate platform-native smoke invokes the real 3G44 retained
handle guard; it accepts only explicitly classified observed replacement or
native custody refusal. Native ACL/backing and real handle behavior remain
Windows/installed-artifact qualification gates.

The guarded runner checks exact branch/main refs, all inherited blob SHA-1
identities, the additive three-file scope, Ruff and strict mypy, and the
focused Core #238 suite. It commits/pushes only after all gates pass.

## Non-claims and follow-up

No production association registry is modified. No Notes content is generated.
This slice does **not** qualify actual production write/replace, directory
entry durability, power-failure recovery, journal retirement, initial binding,
installed-wheel D2 evidence, or non-cooperative same-user serialization.

**Engineering follow-up:** demonstrate and repair platform-specific native
post-replacement custody if the scratch smoke reports a refusal, then implement
actual production crash-consistent replacement and restart recovery under an
operation-owned guard. The production barrier remains unchanged and blocked.
