"""Core #238 Slice 3E7: exact native descriptor-byte observation, advisory only."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Iterator

import pytest

from pds_core import _teacher_private_descriptor_image_snapshot as images
from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core.teacher_experience import get_teacher_experience_capabilities

ASSOCIATION = "6fb32a62-83e2-43f6-9823-687801593c8b"


def _raw() -> bytes:
    return metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(ASSOCIATION)
    )


def test_returns_original_canonical_bytes_without_leaking_them() -> None:
    raw = _raw()
    review = images._checked_image(raw)
    assert review.state is images.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED
    assert review.image is raw
    assert raw not in repr(review).encode()
    assert ASSOCIATION not in repr(review)


@pytest.mark.parametrize(
    "untrusted",
    [
        b"",
        b"{}",
        b"invalid",
        b"\xff",
        _raw() + b" ",
        b"x" * (metadata.MAX_ASSOCIATION_BYTES + 1),
    ],
    ids=["empty", "object", "text", "utf8", "trailing-byte", "oversized"],
)
def test_invalid_descriptor_refused_without_bytes(untrusted: bytes) -> None:
    result = images._checked_image(untrusted)
    assert result.state is images.PrivateDescriptorImageState.INVALID_DESCRIPTOR
    assert result.image is None


def test_review_frozen_and_messages_sanitized() -> None:
    result = images._result(images.PrivateDescriptorImageState.MISSING)
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", images.PrivateDescriptorImageState.IO_ERROR)
    for code in images.PrivateDescriptorImageState:
        review = images._result(code)
        assert ASSOCIATION not in repr(review)
        assert "synthetic_workspace" not in repr(review)
        assert review.image is None


@pytest.mark.parametrize(
    "code,expected",
    [
        (
            retained.RetainedDescriptorGuardCode.OWNER_CHANGED,
            images.PrivateDescriptorImageState.OWNER_CHANGED,
        ),
        (
            retained.RetainedDescriptorGuardCode.OWNER_UNAVAILABLE,
            images.PrivateDescriptorImageState.OWNER_UNAVAILABLE,
        ),
        (
            retained.RetainedDescriptorGuardCode.UNSUPPORTED,
            images.PrivateDescriptorImageState.UNSUPPORTED,
        ),
        (
            retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE,
            images.PrivateDescriptorImageState.GUARD_REFUSED,
        ),
    ],
)
def test_retained_guard_failure_mapping(
    code: retained.RetainedDescriptorGuardCode,
    expected: images.PrivateDescriptorImageState,
) -> None:
    assert images._guard_failure(code) is expected


def test_unsupported_platform_does_not_enter_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "freebsd")
    result = images.inspect_existing_workspace_descriptor_image(tmp_path, tmp_path)
    assert result.state is images.PrivateDescriptorImageState.UNSUPPORTED


def test_invalid_paths_refused_before_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    result = images.inspect_existing_workspace_descriptor_image(
        tmp_path, Path("relative")
    )
    assert result.state is images.PrivateDescriptorImageState.INVALID_REQUEST


@contextmanager
def _held() -> Iterator[None]:
    yield


def _mock_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(
        retained, "_hold_existing_retained_descriptor_guard", lambda *_: _held()
    )
    monkeypatch.setattr(ordered, "_owner", lambda: "synthetic-native-owner")


def test_public_guarded_read_returns_exact_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_guard(monkeypatch)
    monkeypatch.setattr(images, "_read_linux", lambda *_: images._checked_image(_raw()))
    result = images.inspect_existing_workspace_descriptor_image(tmp_path, tmp_path)
    assert result.state is images.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED
    assert result.image == _raw()


def test_public_guard_exit_failure_overrides_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_guard(monkeypatch)

    @contextmanager
    def failing() -> Iterator[None]:
        yield
        raise retained.RetainedDescriptorGuardError(
            retained.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE
        )

    monkeypatch.setattr(
        retained, "_hold_existing_retained_descriptor_guard", lambda *_: failing()
    )
    monkeypatch.setattr(images, "_read_linux", lambda *_: images._checked_image(_raw()))
    result = images.inspect_existing_workspace_descriptor_image(tmp_path, tmp_path)
    assert result.state is images.PrivateDescriptorImageState.GUARD_REFUSED
    assert result.image is None


def test_public_owner_drift_discards_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_guard(monkeypatch)
    owners = iter(["first", "second"])
    monkeypatch.setattr(ordered, "_owner", lambda: next(owners))
    monkeypatch.setattr(images, "_read_linux", lambda *_: images._checked_image(_raw()))
    result = images.inspect_existing_workspace_descriptor_image(tmp_path, tmp_path)
    assert result.state is images.PrivateDescriptorImageState.OWNER_CHANGED
    assert result.image is None


def test_public_reader_error_returns_sanitized_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_guard(monkeypatch)

    def fail(_path: Path) -> images.PrivateDescriptorImageReview:
        raise OSError("unsafe-private-path")

    monkeypatch.setattr(images, "_read_linux", fail)
    result = images.inspect_existing_workspace_descriptor_image(tmp_path, tmp_path)
    assert result.state is images.PrivateDescriptorImageState.IO_ERROR
    assert "unsafe-private-path" not in repr(result)


@pytest.fixture
def linux_workspace(tmp_path: Path) -> Path:
    if sys.platform != "linux":
        pytest.skip("Linux native fixture")
    root = tmp_path / "workspace"
    (root / ".pds").mkdir(parents=True)
    return root


def test_linux_canonical_image(linux_workspace: Path) -> None:
    path = linux_workspace / ".pds" / "teacher-private-association.json"
    path.write_bytes(_raw())
    outcome = images._read_linux(linux_workspace)
    assert outcome.state is images.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED
    assert outcome.image == _raw()


def test_linux_missing_descriptor(linux_workspace: Path) -> None:
    result = images._read_linux(linux_workspace)
    assert result.state is images.PrivateDescriptorImageState.MISSING


def test_linux_rejects_malformed_without_modification(linux_workspace: Path) -> None:
    path = linux_workspace / ".pds" / "teacher-private-association.json"
    path.write_bytes(b"malformed-preserved")
    result = images._read_linux(linux_workspace)
    assert result.state is images.PrivateDescriptorImageState.INVALID_DESCRIPTOR
    assert path.read_bytes() == b"malformed-preserved"


def test_linux_refuses_symlink_sidecar(linux_workspace: Path) -> None:
    target = linux_workspace / "target.json"
    target.write_bytes(_raw())
    (linux_workspace / ".pds" / "teacher-private-association.json").symlink_to(target)
    result = images._read_linux(linux_workspace)
    assert (
        result.state is not images.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED
    )
    assert target.read_bytes() == _raw()


def test_linux_refuses_symlink_metadata_directory(linux_workspace: Path) -> None:
    real = linux_workspace / "real"
    real.mkdir()
    (real / "teacher-private-association.json").write_bytes(_raw())
    (linux_workspace / ".pds").rmdir()
    (linux_workspace / ".pds").symlink_to(real, target_is_directory=True)
    result = images._read_linux(linux_workspace)
    assert (
        result.state is not images.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED
    )
    assert (real / "teacher-private-association.json").read_bytes() == _raw()


def test_linux_detects_replacement_during_read(
    linux_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = linux_workspace / ".pds" / "teacher-private-association.json"
    path.write_bytes(_raw())
    original = os.read
    done = False

    def replace(fd: int, count: int) -> bytes:
        nonlocal done
        result = original(fd, count)
        if not done:
            done = True
            replacement = path.parent / "replacement.json"
            replacement.write_bytes(_raw())
            replacement.replace(path)
        return result

    monkeypatch.setattr(os, "read", replace)
    result = images._read_linux(linux_workspace)
    assert result.state is images.PrivateDescriptorImageState.CHANGED_DURING_READ
    assert path.read_bytes() == _raw()


def test_linux_refuses_hardlinked_descriptor(linux_workspace: Path) -> None:
    path = linux_workspace / ".pds" / "teacher-private-association.json"
    path.write_bytes(_raw())
    os.link(path, linux_workspace / "linked.json")
    result = images._read_linux(linux_workspace)
    assert result.state is images.PrivateDescriptorImageState.REFUSED_PATH


def test_no_public_notes_or_write_capability() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(images, "write_private_descriptor")
    assert not hasattr(images, "commit_private_transaction")


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows only")
def test_windows_native_untrusted_workspace_descriptor(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    folder = workspace / ".pds"
    folder.mkdir(parents=True)
    path = folder / "teacher-private-association.json"
    path.write_bytes(_raw())
    result = images._read_windows(workspace)
    assert result.state is images.PrivateDescriptorImageState.OBSERVED_REVIEW_REQUIRED
    assert result.image == _raw()
