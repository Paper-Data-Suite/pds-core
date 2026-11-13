"""Core #238 3G44: retained native handles with a single attempt marker."""

from __future__ import annotations

import inspect
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal, cast

import pytest

from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_recovery_one_shot_transition_pair as attempt
from pds_core import _teacher_private_recovery_transition_registry_custody as native

State = native.PrivateRegistryTransitionIdentityState
PREPARED = State.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
INSTALLED = State.EXPECTED_STAGE_INSTALLED_RECOVERY_REQUIRED
TX = "11111111-1111-4111-8111-111111111111"


def _window(*states: State) -> attempt._AttemptWindow:
    values = iter(states)
    return attempt._AttemptWindow(lambda: next(values))


@pytest.mark.parametrize("state", list(State))
def test_no_attempt_accepts_only_prepared(state: State) -> None:
    assert attempt._terminal_permitted(False, state) is (state is PREPARED)


@pytest.mark.parametrize("state", list(State))
def test_marked_attempt_requires_exact_stage_installed(state: State) -> None:
    assert attempt._terminal_permitted(True, state) is (state is INSTALLED)


def test_one_attempt_marks_before_native_operation() -> None:
    window = _window(PREPARED, PREPARED, INSTALLED)
    assert window.observe() is PREPARED
    window.mark_attempt()
    assert window.attempted
    assert window.observe() is INSTALLED


def test_one_attempt_is_irreversible_and_never_replayable() -> None:
    window = _window(PREPARED)
    window.mark_attempt()
    with pytest.raises(attempt._AttemptScopeRefused):
        window.mark_attempt()


@pytest.mark.parametrize("refusal", [s for s in State if s is not PREPARED])
def test_cannot_mark_unqualified_native_preimage(refusal: State) -> None:
    window = _window(refusal)
    with pytest.raises(attempt._AttemptScopeRefused):
        window.mark_attempt()
    assert not window.attempted


def test_already_installed_stage_is_not_a_new_attempt() -> None:
    window = _window(INSTALLED)
    with pytest.raises(attempt._AttemptScopeRefused):
        window.mark_attempt()


def test_scope_finish_invalidates_all_future_access() -> None:
    window = _window(PREPARED, INSTALLED)
    assert window._finish() is PREPARED
    with pytest.raises(attempt._AttemptScopeRefused):
        window.observe()
    with pytest.raises(attempt._AttemptScopeRefused):
        window.mark_attempt()
    with pytest.raises(attempt._AttemptScopeRefused):
        window._finish()


def test_scope_finish_invalidated_even_if_native_probe_raises() -> None:
    def broken() -> State:
        raise OSError("injected read refusal")

    window = attempt._AttemptWindow(broken)
    with pytest.raises(attempt._AttemptScopeRefused):
        window._finish()
    with pytest.raises(attempt._AttemptScopeRefused):
        window.observe()


def test_unmarked_post_install_is_never_qualified() -> None:
    window = _window(INSTALLED)
    terminal = window._finish()
    assert not attempt._terminal_permitted(window.attempted, terminal)


def test_attempt_prepared_does_not_claim_replacement() -> None:
    window = _window(PREPARED, PREPARED)
    window.mark_attempt()
    terminal = window._finish()
    assert not attempt._terminal_permitted(window.attempted, terminal)
    assert terminal is PREPARED


def test_attempt_installed_requires_native_identity() -> None:
    window = _window(PREPARED, INSTALLED)
    window.mark_attempt()
    terminal = window._finish()
    assert attempt._terminal_permitted(window.attempted, terminal)
    assert terminal is INSTALLED


def test_refusal_and_handle_repr_do_not_leak_identifiers() -> None:
    window = _window(PREPARED)
    assert "redacted=True" in repr(window)
    assert TX not in repr(window)
    assert not hasattr(window, "path")
    assert not hasattr(window, "write")
    assert not hasattr(window, "replace")
    assert str(attempt._AttemptScopeRefused()) == ""


@pytest.mark.parametrize("size", [None, True, False, 0, -3, 4.0, "4", {}, object()])
def test_invalid_before_size_is_refused(size: object, tmp_path: Path) -> None:
    owner = inspection.EffectiveOSOwner("posix_euid", "1000")
    with pytest.raises(attempt._AttemptScopeRefused):
        with attempt._held_one_shot_transition_pair(
            tmp_path, TX, owner, cast(int, size), 8
        ):
            pytest.fail("Invalid size unexpectedly entered the retained scope")


@pytest.mark.parametrize("size", [None, True, False, 0, -3, 4.0, "4", {}, object()])
def test_invalid_after_size_is_refused(size: object, tmp_path: Path) -> None:
    owner = inspection.EffectiveOSOwner("posix_euid", "1000")
    with pytest.raises(attempt._AttemptScopeRefused):
        with attempt._held_one_shot_transition_pair(
            tmp_path, TX, owner, 8, cast(int, size)
        ):
            pytest.fail("Invalid size unexpectedly entered the retained scope")


def test_unsupported_platform_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    owner = inspection.EffectiveOSOwner("posix_euid", "1000")
    with pytest.raises(attempt._AttemptScopeRefused):
        with attempt._held_one_shot_transition_pair(tmp_path, TX, owner, 8, 8):
            pytest.fail("Unsupported platform entered the scope")


def test_wrapper_keeps_same_window_live_through_release(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner_kind = "windows_token_sid" if sys.platform == "win32" else "posix_euid"
    owner_value = "S-1-5-21-111-222-333-1001" if sys.platform == "win32" else "1000"
    owner = inspection.EffectiveOSOwner(
        cast(Literal["windows_token_sid", "posix_euid"], owner_kind), owner_value
    )
    events: list[str] = []

    @contextmanager
    def fake(
        _root: Path,
        name: str,
        _owner: inspection.EffectiveOSOwner,
        before: int,
        after: int,
    ) -> Iterator[attempt._AttemptWindow]:
        assert name == "." + TX + ".registry-stage"
        assert before == 7 and after == 9
        window = _window(PREPARED, PREPARED)
        events.append("enter")
        try:
            yield window
        finally:
            events.append("release")
            assert window._finish() is PREPARED

    target = "_held_windows_pair" if sys.platform == "win32" else "_held_linux_pair"
    monkeypatch.setattr(attempt, target, fake)
    with attempt._held_one_shot_transition_pair(tmp_path, TX, owner, 7, 9) as window:
        events.append("held")
        window.mark_attempt()
        assert window.attempted
    assert events == ["enter", "held", "release"]


def test_native_scope_contains_no_mutation_or_replay_api() -> None:
    source = inspect.getsource(attempt)
    assert "os.replace(" not in source
    assert "os.rename(" not in source
    assert "unlink(" not in source
    assert "os.remove(" not in source
    assert "shutil." not in source
    assert "def activate_notes" not in source
    assert "_windows_open" in source
    assert "_held_linux_pair" in source
    assert "_held_windows_pair" in source
    assert "_terminal_permitted" in source


def test_source_terminal_review_does_not_claim_commit() -> None:
    assert not hasattr(attempt, "commit_private_transaction")
    assert not hasattr(attempt, "retire_private_journal")
    assert not hasattr(attempt, "enable_notes")
    assert not hasattr(attempt, "replace_registry")
