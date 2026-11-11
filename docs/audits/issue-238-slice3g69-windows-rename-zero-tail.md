# Core #238 — Slice 3G69: zero-terminated Windows rename destination storage

## Baseline and evidence

- Exact base: `c95e82c680f845e86cee113cbd8084f5fef2837d` (3G68), draft PR #247.
- CI run `43112424085`: 13/15 jobs passed; Windows 3.12/3.13 each failed the same *real native* stage-to-registry replacement postcondition.
- The staging bytes appeared in an unexpected adjacent entry whose leaf was the intended `registry.json` **plus two arbitrary UTF-16 characters**; values differed across runs, consistent with an out-of-bounds suffix read from an exactly sized `FILE_RENAME_INFO` request. The original target remained unchanged.
- Windows `FILE_RENAME_INFO.FileNameLength` is the filename's byte length, and the protocol permits trailing padding. Do not change FileNameLength or substitute a different rename API without evidence.

## Bounded correction

- Modify the **internal** `FileRenameInfoEx` buffer allocation to include 64 explicitly zero-initialized trailing bytes after the encoded target name; preserve the exact name, byte count, `FILE_RENAME_REPLACE_IF_EXISTS|FILE_RENAME_POSIX_SEMANTICS`, FILE_SHARE_DELETE access and original single native rename syscall.
- Extend the existing mocked API test to verify that every byte after `FileNameLength` is zero and at least 64 bytes of trailing storage are available.
- Do not modify the strict independent Windows native child test, original postconditions, other private-storage modules, public APIs, CI exclusions, Notes, or release behavior. No alternate rename or post-failure retry is allowed.

## Qualification and explicit limits

- Guard exact branch, HEAD, remote, worktree and two file blobs. Check replacements/AST in memory before writing, then run focused pytest, Ruff, strict mypy on native Windows/Linux targets, isolated candidate wheel installed no-write gate, and a two-source/one-audit staged diff check. Commit/push only if green locally.
- Native CI Windows 3.12/3.13 is the **decisive** acceptance evidence. If any source/target content or native identity assertion fails, keep PR #247 draft and treat the rename operation as unqualified; do not mask the failure.
- This slice does not approve production private storage writes, binding authorization, initialization, multi-file atomicity, durability, journal replay/retirement, or Notes.
