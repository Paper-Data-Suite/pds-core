# Core #238 — Slice 3G89: native Linux postcheck-to-replace race, scratch only

## Purpose and exact boundary

The accepted 3G88 native Linux `dirfd` replacement pins the **parent directory**,
compares current entry metadata and exact bytes, then calls handle-relative
`os.replace`. The kernel does not condition that replacement on the previously
observed destination/stage inode or content. 3G89 exercises that distinction on
new disposable files; no real teacher-private root or workspace is accessed.

## Demonstration

Under the existing cooperative OS-user lock and one retained Linux parent FD,
create synthetic registry before-image, stage after-image and a pending journal.
Perform the final native `dirfd` precheck of all three. Then, without releasing
the lock or FD, start an *independent Python interpreter* which intentionally
ignores the lock and atomically replaces one of the entries with a distinct
inode containing exactly the same bytes. The writer subsequently performs
`os.replace(..., src_dir_fd=fd, dst_dir_fd=fd)` **without another check**.
The postimage is correct, and the pending journal is preserved, despite the
unobserved entry change. The exercise covers both the live-registry target and
the staged-registry source. A normal no-rival case is a baseline.

The implementation *deliberately proceeds after observing the injected race* in
an internal scratch-only experiment to establish why a successful postimage
is insufficient evidence of atomic preimage conditionality. It is **not** a
recovery writer implementation, a recommended strategy, or an authorization
for production replacement. No caller paths, file bytes, child scripts,
transaction IDs, owner identities, or callbacks are accepted. All child
operations are confined to the invocation's freshly created scratch directory.

## Refusal/limitations

- Invalid scenarios and drifted requirement taxonomy refuse before setup.
- Native Linux runs only as an ordinary non-root local user with a protected
  disposable directory. Windows refuses this Linux-only protocol immediately.
- This demonstrates a **TOCTOU non-guarantee**, not a security breach or a
  claim that Linux can exclude hostile code running as the same OS user.
- No atomic content CAS, Windows native replacement, multi-document atomicity,
  power-failure durability, automatic recovery, journal retirement, Notes
  records, initial binding, or production write admission is qualified.
- Existing production barriers and nine requirements remain unchanged.

## Verification and next design gate

New deterministic source tests cover the no-rival baseline, two independent
postcheck races, invalid request types, requirement drift and the negative
capability boundary. The 21st installed-wheel gate checks native Linux outcomes
and explicit Windows refusal from an isolated interpreter; reports contain only
fixed enumerations and wheel hashes. The runner preserves the 20 previous
native gates and strict Linux/Windows typing on the exact frozen branch head.

**Next:** Design a reviewed conditional mutation/recovery policy appropriate to
each operating system. Compare native Linux `renameat2` availability and limits
without calling exchange/replace an atomic content CAS, and evaluate Windows
handle/sharing semantics separately. Maintain fail-closed production operation
barriers until real owner/binding, atomicity, native recovery, and durability
requirements are independently qualified.
