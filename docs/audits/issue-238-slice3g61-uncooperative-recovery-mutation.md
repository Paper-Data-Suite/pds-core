# Core #238 — 3G61: Uncooperative mutation while recovery lock is held

## Exact scope

This **test-only** slice uses disposable nonce-marked Core temporary directories.
It does not create, modify, or publish a production private workspace writer,
Notes record service, replay path, journal-retirement path, or durability permit.

3G59 demonstrated that a parent-killed transaction relinquishes its local native
lock. 3G60 demonstrated that a second recovery holder excludes cooperating
contenders until it too is killed. **3G61 tests a different failure mode:**
a same-user process that deliberately ignores that cooperative lock can change
synthetic registry, descriptor, journal bytes, or the stage namespace.

The recovery holder has already observed a valid exact canonical checkpoint
and remains alive under its scratch lock when the uncooperative worker acts.
A cooperating probe must still be refused during the held scope. After the
holder is forcibly killed, a new reader must observe `conflict_preserve`, not
infer an earlier valid checkpoint, replay, continue a replacement, delete the
pending journal, or grant a production write capability.

The mutation worker accepts only a fixed set of operations and a nonce-marked
single-level directory beneath the system temp root. It verifies the token,
fixed scratch marker, canonical paths, and regular native file status before
changing an existing file. It does not accept arbitrary path names or bytes.

## Matrix

Four transaction checkpoints (prepared, registry replaced, descriptor replaced,
descriptor flush requested) × four tamper modes (journal bytes, registry bytes,
descriptor bytes, unexpected registry-stage entry) = **16 external-mutation
cases**, plus invalid-token and unsupported-mode refusals.

An initial valid result obtained under a held lock is **not** an immutable
capability. Cooperative locks do not defeat uncooperative same-owner processes;
future production code must establish native owner/ACL custody, hold verified
native file identities throughout operation, and independently re-qualify
exact current images before any write. Even complete postimages do not
establish power-loss durability.

## Non-claims and remaining gates

All findings are scratch-only and read-only from the recovery process. Mutator
writes are intentional *disposable test fixture corruption*, never production.
No run proves power-loss durability, safe auto-replay, journal retirement,
cloud synchronization, cross-machine exclusion, or a production transaction
writer. Core's nine-requirement production-write barrier remains unchanged.

The authoritative native Windows matrix, full focused Core suite, Ruff and
strict mypy must pass before this additive test slice is committed.
