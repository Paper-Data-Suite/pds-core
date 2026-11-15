"""Native installed-wheel 3G86: characterize cross-process advisory-lock gap.

All mutations occur in a new, disposable directory inside the caller's
qualified scratch area. No production workspace or teacher-private root is
opened. Locking a separate coordination file does not stop an uncooperative
process from atomically replacing an unrelated metadata file.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

_LOCK_CHILD = r"""
import os,sys
p=sys.argv[1]
fd=os.open(p, os.O_RDWR | getattr(os,'O_BINARY',0))
try:
    if os.name=='nt':
        import msvcrt
        os.lseek(fd,0,os.SEEK_SET)
        msvcrt.locking(fd,msvcrt.LK_NBLCK,1)
    else:
        import fcntl
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
except OSError:
    raise SystemExit(23)
else:
    raise SystemExit(24)
finally:
    os.close(fd)
"""

_REPLACE_CHILD = r"""
import os,sys
from pathlib import Path
base=Path(sys.argv[1]); dest=base/'registry.json'; stage=base/'staged-registry.tmp'
stage.write_bytes(b'changed-by-uncooperative-process')
os.replace(stage,dest)
raise SystemExit(0)
"""


def _provenance(wheel: Path, source: Path, version: str) -> str:
    import pds_core
    from pds_core import _teacher_private_file_lock as locking
    from pds_core import _teacher_private_writer_guard_gap as review

    purelib = Path(sysconfig.get_paths()["purelib"]).resolve(strict=True)
    if (
        version != "0.6.6"
        or importlib.metadata.version("pds-core") != version
        or not wheel.is_file()
        or wheel.suffix != ".whl"
    ):
        raise RuntimeError("installed_wheel_provenance_refused")
    for item in (pds_core, locking, review):
        origin = item.__file__
        if origin is None:
            raise RuntimeError("module_origin_refused")
        path = Path(origin).resolve(strict=True)
        if not path.is_relative_to(purelib) or path.is_relative_to(source):
            raise RuntimeError("installed_module_origin_refused")
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _child(script: str, arg: Path) -> int:
    completed = subprocess.run(
        [sys.executable, "-I", "-c", script, str(arg)],
        check=False,
        capture_output=True,
        timeout=15,
    )
    if completed.stdout or completed.stderr:
        raise RuntimeError("child_process_unexpected_output")
    return completed.returncode


def _scratch_exclusion_probe(scratch: Path) -> dict[str, object]:
    from pds_core import _teacher_private_file_lock as locking

    with tempfile.TemporaryDirectory(prefix="core238_3g86_", dir=scratch) as name:
        directory = Path(name)
        lock = directory / ".registry.lock"
        image = directory / "registry.json"
        lock.write_bytes(b"0")
        if sys.platform == "linux":
            lock.chmod(0o600)
        image.write_bytes(b"canonical-before")
        with locking.hold_existing_private_lock(lock):
            cooperative_refusal = _child(_LOCK_CHILD, lock)
            if cooperative_refusal != 23:
                raise RuntimeError("cooperative_lock_exclusion_unqualified")
            prior = image.read_bytes()
            uncooperative_replace = _child(_REPLACE_CHILD, directory)
            altered = image.read_bytes()
            if (
                prior != b"canonical-before"
                or uncooperative_replace != 0
                or altered != b"changed-by-uncooperative-process"
            ):
                raise RuntimeError("uncooperative_replacement_observation_failed")
        # TemporaryDirectory deletes only this invocation's disposable files.
    return {
        "cooperating_contender_refused": True,
        "uncooperative_other_file_replace_succeeded": True,
        "postimage_changed_under_cooperative_guard": True,
        "disposable_native_only": True,
    }


def _review() -> dict[str, object]:
    from pds_core import _teacher_private_production_readiness as readiness
    from pds_core import _teacher_private_writer_guard_gap as gap
    from pds_core.teacher_experience import get_teacher_experience_capabilities

    refused = gap.review_private_writer_owned_exclusivity_gap(
        Path("invalid-relative"), "invalid", 0
    )
    if (
        type(refused) is not gap.PrivateWriterGuardGapReview
        or refused.state
        is not gap.PrivateWriterGuardGapState.STAGE_REVIEW_REFUSED_PRESERVE
        or refused.unqualified_requirements != readiness._REQUIRED
        or len(refused.unqualified_requirements) != 9
        or refused.stage_read_review_only
        or any(
            (
                refused.cooperative_lock_exclusion_is_production_exclusion,
                refused.operation_owned_guard_qualified,
                refused.noncooperating_writer_exclusion_qualified,
                refused.native_parent_custody_for_write_qualified,
                refused.exact_preimage_cas_for_write_qualified,
                refused.native_replace_postimage_qualified,
                refused.production_mutation_admitted,
                refused.automatic_replay_allowed,
                refused.journal_retirement_allowed,
                refused.notes_records_available,
                refused.directory_crash_durability_qualified,
                refused.multi_document_atomic_commit_qualified,
            )
        )
        or get_teacher_experience_capabilities()
        != frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
    ):
        raise RuntimeError("writer_guard_gap_not_fail_closed")
    return {
        "invalid_request_refusal": refused.state.value,
        "unqualified_requirements": list(refused.unqualified_requirements),
        "operation_owned_guard_qualified": False,
        "noncooperating_writer_exclusion_qualified": False,
        "native_parent_custody_for_write_qualified": False,
        "exact_preimage_cas_for_write_qualified": False,
        "native_replace_postimage_qualified": False,
        "production_mutation_admitted": False,
        "automatic_replay_allowed": False,
        "journal_retirement_allowed": False,
        "notes_records_available": False,
        "directory_crash_durability_qualified": False,
        "multi_document_atomic_commit_qualified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkout", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform not in {"linux", "win32"}:
        raise RuntimeError("unsupported_native_platform")
    source = args.source_checkout.resolve(strict=True)
    wheel = args.wheel.resolve(strict=True)
    scratch = args.scratch_root.resolve(strict=True)
    report = args.report.resolve(strict=False)
    if (
        not scratch.is_dir()
        or scratch.is_symlink()
        or scratch.name != "scratch"
        or scratch.is_relative_to(source)
        or report.is_relative_to(source)
        or report.exists()
        or report.parent != scratch.parent
    ):
        raise RuntimeError("unsafe_evidence_scope")
    digest = _provenance(wheel, source, args.expected_version)
    detail = _review()
    native = _scratch_exclusion_probe(scratch)
    evidence = {
        "schema": "pds.core.issue238.installed-writer-guard-gap.v1",
        "result": "passed_native_scratch_noncooperator_gap_only",
        "platform": sys.platform,
        "installed_version": "0.6.6",
        "wheel_sha256": digest,
        **detail,
        **native,
    }
    report.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("ISSUE238_INSTALLED_WRITER_GUARD_GAP: PASS (scratch only; no authority)")
    print("QUALIFIED_WHEEL_SHA256: " + digest)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        subprocess.TimeoutExpired,
    ) as exc:
        print(
            "ISSUE238_INSTALLED_WRITER_GUARD_GAP: STOP (" + type(exc).__name__ + ")",
            file=sys.stderr,
        )
        raise SystemExit(1)
