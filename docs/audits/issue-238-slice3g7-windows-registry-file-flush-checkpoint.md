# Core #238 — Slice 3G7: protected Windows registry file-flush checkpoint

**Baseline:** qualified 3G6 `da688067b9cbd252211d1d203f7e7b1fff9431e5`.

## Scope

Add an **internal**, explicitly invoked, Windows-only checkpoint for an already
replaced registry after-image, while the canonical pending journal remains.
The caller must have separately secured teacher consent and admitted the
transaction; 3G7 is not the transaction coordinator. The operation performs
at most one `FlushFileBuffers` against the *existing* protected live registry;
it does not create, rename, modify bytes, delete, retire or rebind metadata.

The native backend opens `registry.json` with write access **only because
FlushFileBuffers requires it**, using `OPEN_EXISTING`, no reparse traversal and
share read/write/delete. It verifies the existing user's owner-bound effective
DACL, fixed local volume, private-root ancestry, native FILE_ID and size.
It compares the live file's native identity before and after the flush and
reopens the named path to verify that the file still has that exact identity.
Failure is sanitized and requires recovery review, not retry or fallback.

The coordinator retains existing ordered workspace/private locks, protected
journal directory, registry, and descriptor handles through the observation.
It requires one pending canonical journal, no stage-like entries, qualified
empty native stage inventory, and a consistent stage-absent 3G4 **registry
already after** checkpoint. After the flush, it repeats complete native byte
observations, inventory and namespace, and OS owner checks, and refuses any
drift. It does not reacquire nested locks or use the immutable registry guard
around a rename; **the rename must already have taken place**.

## Security and durability limits

A successful `FlushFileBuffers` **only** demonstrates that the OS accepted a
file-buffer flush and that matching metadata was reobserved. It does **not**
establish the parent directory-entry write was persisted across unexpected
power loss, that a previous rename was durably ordered after the journal,
or that two-file updates are atomic or committed. File-system filters, storage
hardware, cloud providers, concurrent same-OS-user actors and network shares
remain outside the guaranteed scope; unsupported private backing is refused.
In particular, Windows lacks a generally portable, established equivalent
of POSIX `fsync(dirfd)` for the exact directory-entry guarantee here.

A result **never** permits descriptor completion, journal retirement, private
collection admission, Notes records, or public capability flags. Preserve
pending evidence on any ambiguity. Linux/macOS remain unsupported by this
Windows-specific primitive; their own native write and fsync protocol must
be qualified independently.

## Verification

- Synthetic adversarial tests: platform, invalid input, unsupported
  checkpoint, unqualified journal/stage namespace, altered owner,
  before/after image drift, native flush failure, retained-guard exit refusal,
  sanitized advisory response and unchanged teacher capabilities.
- Windows scratch test: real kernel32 `FlushFileBuffers` on a synthetic file
  with byte and native FILE_ID continuity. No teacher-private path used.
- Full repository qualification: exact Git baseline and remote, pinned blobs,
  3G7 tests, focused Core #238 pytest, Ruff, strict mypy, full Core pytest,
  exactly three new files, conditional Git commit and push.
- Not qualified: power-loss survival, independent journal admission,
  end-to-end CAS, Linux/macOS, cloud/network durability, Notes services,
  published consumer API, installed-wheel D2.

**Next:** Native crash fault-injection and directory-entry persistence review
must precede any durable binding or journal retirement claim.
