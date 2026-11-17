# Core #238 — Slice 3G90: Linux renameat2 filename guarantees (scratch only)

## Purpose and exact scope

Slice 3G89 proved a native Linux `dirfd` replacement is not a kernel conditional
check of the *previously observed* registry or staged file. Slice 3G90 reviews
the closest Linux native alternatives without presenting them as a secure
production transaction. Only constant synthetic filenames/bytes inside a new
OS-user-owned temporary directory are touched; public entrypoint accepts
exactly one scenario enum, no workspace, path, owner, intent, callback or handle.
The current protected Core registry/Notes service remains untouched.

## Kernel contract and native observations

Linux `renameat2` supports `RENAME_NOREPLACE` (flag 1), which refuses if the
destination name already exists, and `RENAME_EXCHANGE` (flag 2), which exchanges
two existing names atomically. These are **filename** conditions; neither
provides an expected-inode or expected-content operand. They cannot be combined.
See Linux `rename(2)` manual, including supported filesystem notes.

The new native scratch probe holds the cooperative lock and a Linux directory
file descriptor, checks the original registry/stage/journal identities and exact
bytes, then measures:

- Existing destination + `RENAME_NOREPLACE`: `EEXIST`, live and stage unchanged.
  This cannot update an existing registry.
- Two existing names + `RENAME_EXCHANGE`: swap succeeds; the previously live
  registry remains staged. The pending journal is preserved. An exchange alone
  is not a recoverable multi-document transaction.
- An independent interpreter ignoring the lock replaces the live registry with
  *equal bytes but a new inode* between the check and `RENAME_EXCHANGE`: exchange
  still succeeds, and the newly substituted inode is staged afterward. Thus
  an atomic exchange does not imply atomic *content compare-and-swap*.

Each outcome is checked with dirfd-relative identity and exact-image reading;
no power-loss durability is inferred. The ordinary effective UID must be nonroot.
Unsupported syscall/filesystem/owner contexts fail closed. Windows explicitly
refuses this Linux protocol; its native API must be reviewed separately.

## Production security restrictions

No property or return object is a production write permit. A rival with the
same effective OS user can still modify a file even while the cooperating lock
is held. `RENAME_EXCHANGE` is not a general CAS primitive; `RENAME_NOREPLACE`
checks *absence*, not a previously witnessed identity. The operating system
cannot promise isolation against arbitrary code running as the same account.
No real teacher-private paths, actual descriptor, journal, registry or Notes
payload are read/written. All nine production-operation blockers remain open.
No binding, automatic recovery, replay, journal retirement or Notes activation.

## Qualification and handoff

The new focused tests and the 22nd installed-wheel gate on Linux/Windows must
validate these fixed synthetic outcomes and refusal boundaries. Evidence is
limited to static labels, platform, candidate-wheel hash and negative authority
flags. Every prior native installed gate remains enabled.

**Next:** use these results to freeze the Linux transaction protocol's actual
trust boundary (cooperating owner-scoped writers vs. arbitrary same-owner code),
then independently qualify Windows native sharing/replacement and durable
journal replay. Do not require an impossible generic kernel content CAS or
silently reinterpret the synthetic probe as a production security proof.
