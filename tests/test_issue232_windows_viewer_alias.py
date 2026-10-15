"""#232: no-copy Windows default-viewer handoff for deep local paths."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import time

import pytest

from pds_core import local_open
from pds_core.local_open import LocalOpenError, open_local_path


def _deep_file(root: Path) -> Path:
    current = root
    while len(str(current)) <= 270:
        current /= "deep-area"
    current.mkdir(parents=True, exist_ok=True)
    target = current / "artifact.pdf"
    target.write_bytes(b"%PDF-1.4\nSynthetic document\n%%EOF\n")
    return target


_NATIVE_JUNCTION = local_open._create_windows_junction


def _simulated_junction(link: Path, target: Path) -> None:
    # On Windows, use real unprivileged junctions instead of symlinks, which
    # commonly require Developer Mode or privileges on CI. POSIX uses a mock.
    if os.name == "nt":
        _NATIVE_JUNCTION(link, target)
    else:
        link.symlink_to(target, target_is_directory=True)


def _simulate_windows(
    monkeypatch: pytest.MonkeyPatch,
    alias_root: Path,
) -> list[Path]:
    opened: list[Path] = []
    monkeypatch.setattr(local_open.sys, "platform", "win32")
    monkeypatch.setattr(local_open, "_viewer_alias_root", lambda: alias_root)
    monkeypatch.setattr(local_open, "_create_windows_junction", _simulated_junction)
    if os.name != "nt":
        monkeypatch.setattr(
            local_open, "_remove_viewer_junction", lambda link: link.unlink()
        )
    monkeypatch.setattr(local_open.os, "startfile", opened.append, raising=False)
    return opened


def test_short_windows_path_keeps_existing_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "short.pdf"
    target.write_bytes(b"short")
    opened: list[Path] = []
    monkeypatch.setattr(local_open.sys, "platform", "win32")
    monkeypatch.setattr(local_open.os, "startfile", opened.append, raising=False)
    monkeypatch.setattr(
        local_open,
        "_prepare_windows_viewer_alias",
        lambda unused: pytest.fail("short path must not create an alias"),
    )
    assert open_local_path(target) == target.resolve()
    assert opened == [target.resolve()]


def test_deep_pdf_uses_short_lexical_alias_no_copy_and_returns_canonical(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original = _deep_file(tmp_path / "workspace")
    alias_root = tmp_path / "aliases"
    alias_root.mkdir()
    opened = _simulate_windows(monkeypatch, alias_root)
    expected = original.read_bytes()

    assert open_local_path(original) == original.resolve()
    assert len(opened) == 1
    alias = opened[0]
    assert alias != original
    assert len(str(alias)) < len(str(original))
    assert local_open._windows_path_units(alias) <= 240
    assert alias.read_bytes() == expected
    assert original.read_bytes() == expected
    assert alias.resolve() == original.resolve()
    assert local_open._is_reparse_point(
        alias.parent
    )  # lease survives after startfile returns


def test_deep_directory_uses_junction_not_folder_copy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _deep_file(tmp_path / "workspace").parent
    alias_root = tmp_path / "aliases"
    alias_root.mkdir()
    opened = _simulate_windows(monkeypatch, alias_root)
    assert open_local_path(source) == source.resolve()
    assert len(opened) == 1
    assert local_open._is_reparse_point(opened[0])
    assert opened[0].resolve() == source.resolve()
    assert (opened[0] / "artifact.pdf").read_bytes() == (
        source / "artifact.pdf"
    ).read_bytes()


def test_created_alias_must_reference_exact_original(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _deep_file(tmp_path / "workspace")
    other = tmp_path / "other"
    other.mkdir()
    (other / "artifact.pdf").write_bytes(b"different")
    alias_root = tmp_path / "aliases"
    alias_root.mkdir()
    _simulate_windows(monkeypatch, alias_root)
    monkeypatch.setattr(
        local_open,
        "_create_windows_junction",
        lambda link, unused_target: _simulated_junction(link, other),
    )
    with pytest.raises(LocalOpenError, match="did not match"):
        open_local_path(source)
    assert list(alias_root.iterdir()) == []
    assert source.read_bytes().startswith(b"%PDF")


def test_too_long_alias_rejected_without_side_effects(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _deep_file(tmp_path / "workspace")
    alias_root = tmp_path / ("r" * 125) / ("s" * 110)
    # Intentionally do not create an overlong test path on Windows hosts.
    _simulate_windows(monkeypatch, alias_root)
    with pytest.raises(LocalOpenError, match="short Windows viewer path"):
        open_local_path(source)
    assert not alias_root.exists()


def test_launch_failure_does_not_claim_viewer_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _deep_file(tmp_path / "workspace")
    alias_root = tmp_path / "aliases"
    alias_root.mkdir()
    _simulate_windows(monkeypatch, alias_root)

    def fail(unused: Path) -> None:
        raise OSError("shell failed")

    monkeypatch.setattr(local_open.os, "startfile", fail, raising=False)
    with pytest.raises(LocalOpenError, match="Could not request"):
        open_local_path(source)
    assert source.is_file()
    assert list(alias_root.iterdir()) == []  # synchronous launch rejection cleans up


def test_old_owned_alias_removed_without_removing_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if os.name == "nt":
        pytest.skip("Windows junction mtime expiry requires a physical gate")
    source = tmp_path / "source"
    source.mkdir()
    (source / "must-stay.pdf").write_bytes(b"important")
    root = tmp_path / "aliases"
    root.mkdir()
    old = root / ("v_" + "a" * 32)
    fresh = root / ("v_" + "b" * 32)
    unrelated = root / "keep"
    _simulated_junction(old, source)
    _simulated_junction(fresh, source)
    unrelated.mkdir()
    age = time.time() - local_open._WINDOWS_VIEWER_ALIAS_RETENTION_SECONDS - 200
    os.utime(old, (age, age), follow_symlinks=False)
    monkeypatch.setattr(local_open.sys, "platform", "linux")

    local_open._prune_stale_aliases(root)
    assert not old.exists()
    assert local_open._is_reparse_point(fresh)
    assert unrelated.is_dir()
    assert (source / "must-stay.pdf").read_bytes() == b"important"


def test_real_directories_are_never_deleted_by_stale_cleanup(tmp_path: Path) -> None:
    root = tmp_path / "aliases"
    root.mkdir()
    bogus = root / ("v_" + "0" * 32)
    bogus.mkdir()
    (bogus / "important").write_text("leave", encoding="utf-8")
    age = time.time() - local_open._WINDOWS_VIEWER_ALIAS_RETENTION_SECONDS - 200
    os.utime(bogus, (age, age))
    local_open._prune_stale_aliases(root)
    assert (bogus / "important").read_text(encoding="utf-8") == "leave"


def test_junction_creation_uses_environment_not_shell_interpolation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(args: list[str], **kwargs: object) -> None:
        assert kwargs["check"] is True
        assert kwargs["timeout"] == 20
        env = kwargs["env"]
        assert isinstance(env, dict)
        calls.append((args, env))

    monkeypatch.setattr(subprocess, "run", fake_run)
    target = tmp_path / "a ; & ` $ ( )"  # shell-sensitive characters
    local_open._create_windows_junction(tmp_path / "link", target)
    args, env = calls[0]
    assert str(target) not in " ".join(args)
    assert env["PDS_CORE_VIEWER_TARGET"] == str(target)
    assert env["PDS_CORE_VIEWER_LINK"] == str(tmp_path / "link")


def test_windows_path_units_count_utf16_surrogate_pairs() -> None:
    assert local_open._windows_path_units(Path("C:/x/🙂")) == len("C:/x/") + 2


def test_alias_directory_reparse_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    appdata = tmp_path / "LocalAppData"
    appdata.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    _simulated_junction(appdata / "PaperDataSuite", elsewhere)
    monkeypatch.setenv("LOCALAPPDATA", str(appdata))
    with pytest.raises(LocalOpenError, match="not a real directory"):
        local_open._viewer_alias_root()
    assert list(elsewhere.iterdir()) == []


def test_alias_collision_including_dangling_link_is_rejected_without_replacement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _deep_file(tmp_path / "workspace")
    alias_root = tmp_path / "aliases"
    alias_root.mkdir()
    suffix = "c" * 32
    chosen = alias_root / ("v_" + suffix)
    dangling_target = tmp_path / "missing-target"
    if os.name == "nt":
        dangling_target.mkdir()
        _NATIVE_JUNCTION(chosen, dangling_target)
        dangling_target.rmdir()
    else:
        chosen.symlink_to(dangling_target, target_is_directory=True)
    class FixedUUID:
        hex = suffix

    monkeypatch.setattr(local_open.uuid, "uuid4", lambda: FixedUUID())
    _simulate_windows(monkeypatch, alias_root)
    with pytest.raises(LocalOpenError, match="unexpectedly exists"):
        open_local_path(source)
    assert os.path.lexists(chosen)
    assert source.read_bytes().startswith(b"%PDF")


def test_cleanup_failure_is_nonblocking_for_other_open_requests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _deep_file(tmp_path / "workspace")
    alias_root = tmp_path / "aliases"
    alias_root.mkdir()
    old = alias_root / ("v_" + "b" * 32)
    _simulated_junction(old, source.parent)
    age = time.time() - local_open._WINDOWS_VIEWER_ALIAS_RETENTION_SECONDS - 100
    if os.name != "nt":
        os.utime(old, (age, age), follow_symlinks=False)
    else:
        monkeypatch.setattr(local_open, "_WINDOWS_VIEWER_ALIAS_RETENTION_SECONDS", -1)
    opened = _simulate_windows(monkeypatch, alias_root)
    native_remove = local_open._remove_viewer_junction

    def deny_removal(path: Path) -> None:
        if path == old:
            raise LocalOpenError("link replaced during cleanup")
        native_remove(path)

    monkeypatch.setattr(local_open, "_remove_viewer_junction", deny_removal)
    assert open_local_path(source) == source.resolve()
    assert len(opened) == 1
    assert opened[0].is_file()
    assert source.is_file()


@pytest.mark.skipif(os.name != "nt", reason="real Windows junction removal only")
def test_real_windows_expired_junction_removed_without_traversing_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "private-source"
    target.mkdir()
    contents = target / "do-not-delete.txt"
    contents.write_text("authoritative", encoding="utf-8")
    root = tmp_path / "aliases"
    root.mkdir()
    junction = root / ("v_" + "e" * 32)
    _NATIVE_JUNCTION(junction, target)
    assert local_open._is_reparse_point(junction)
    assert junction.is_dir()
    monkeypatch.setattr(local_open, "_WINDOWS_VIEWER_ALIAS_RETENTION_SECONDS", -1)
    local_open._prune_stale_aliases(root)
    assert not os.path.lexists(junction)
    assert contents.read_text(encoding="utf-8") == "authoritative"
