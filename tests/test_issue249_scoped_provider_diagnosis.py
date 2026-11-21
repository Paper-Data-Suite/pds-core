"""Core #249: one-owner metadata selection before any optional provider load."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pds_core.module_operations import (
    ModuleAttentionReport,
    ModuleOperationsProfile,
    ModuleOperationsRequest,
    invoke_module_attention,
)
from pds_core.provider_diagnostics import (
    ProviderDiagnosticRequestError,
    ProviderDiagnosticResult,
    ProviderEnumerationError,
    diagnose_core_providers,
    diagnose_selected_core_provider,
)


def _attention(_request: ModuleOperationsRequest) -> ModuleAttentionReport:
    return ModuleAttentionReport(evaluation="evaluated")


def _profile(
    owner: str = "scoreform", versions: frozenset[str] = frozenset({"1"})
) -> ModuleOperationsProfile:
    return ModuleOperationsProfile(
        module_id=owner,
        supported_core_operations_contract_versions=versions,
        attention_provider=_attention,
    )


class EntryPoint:
    def __init__(
        self,
        name: object,
        target: object,
        *,
        owner: str | None,
        loaded: object,
    ) -> None:
        self.name = name
        self.value = target
        self.dist = None if owner is None else SimpleNamespace(name=owner)
        self.loaded = loaded
        self.load_calls = 0

    def load(self) -> object:
        self.load_calls += 1
        if isinstance(self.loaded, Exception):
            raise self.loaded
        return self.loaded


def _entry(
    name: object = "scoreform",
    *,
    owner: str | None = "scoreform",
    target: object = "scoreform.pds_operations:get_module_operations_profile",
    loaded: object | None = None,
) -> EntryPoint:
    return EntryPoint(
        name,
        target,
        owner=owner,
        loaded=(lambda: _profile(str(name))) if loaded is None else loaded,
    )


def _install(
    monkeypatch: pytest.MonkeyPatch,
    entries: tuple[EntryPoint, ...],
    *,
    fail: bool = False,
) -> list[str]:
    observed: list[str] = []

    def entry_points(*, group: str) -> tuple[EntryPoint, ...]:
        observed.append(group)
        if fail:
            raise RuntimeError("PRIVATE_KEY_AND_STUDENT_DATA")
        return entries

    monkeypatch.setattr(
        "pds_core.provider_diagnostics.metadata.entry_points", entry_points
    )
    return observed


def _diagnose(
    *, name: str = "scoreform", distribution: str = "scoreform"
) -> ProviderDiagnosticResult:
    return diagnose_selected_core_provider(
        provider_kind="module_operations",
        entry_point_name=name,
        expected_distribution=distribution,
    )


def test_one_selected_owner_only_is_loaded_even_with_malicious_neighbors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chosen = _entry()
    foreign = _entry(
        "foreign",
        owner="foreign",
        loaded=RuntimeError("PRIVATE_DATA_SHOULD_NEVER_EXECUTE"),
    )
    quillan = _entry("quillan", owner="quillan")
    concord = _entry("concord", owner="pds-concord")
    observed = _install(monkeypatch, (foreign, quillan, chosen, concord))

    result = _diagnose()
    assert observed == ["paper_data_suite.module_operations"]
    assert result.code == "provider.valid"
    assert result.validated_profile == _profile()
    assert chosen.load_calls == 1
    assert foreign.load_calls == quillan.load_calls == concord.load_calls == 0
    assert isinstance(result.validated_profile, ModuleOperationsProfile)
    # Diagnosis must not run the separate operations attention capability.
    outcome = invoke_module_attention(
        result.validated_profile, ModuleOperationsRequest()
    )
    assert outcome.code == "module_operations.evaluated"


@pytest.mark.parametrize(
    "other",
    [
        _entry(),
        _entry(owner="other-publisher"),
    ],
)
def test_duplicate_selected_identity_refused_before_any_load(
    monkeypatch: pytest.MonkeyPatch, other: EntryPoint
) -> None:
    chosen = _entry()
    _install(monkeypatch, (chosen, other))
    result = _diagnose()
    assert result.code == "provider.entry_point_ambiguous"
    assert result.stage == "registry_conflict"
    assert result.registry_conflict
    assert result.validated_profile is None
    assert chosen.load_calls == other.load_calls == 0


def test_missing_selection_refuses_without_loading_other_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unrelated = _entry("quillan", owner="quillan")
    _install(monkeypatch, (unrelated,))
    result = _diagnose()
    assert result.code == "provider.entry_point_missing"
    assert not result.load_attempted
    assert unrelated.load_calls == 0


@pytest.mark.parametrize(
    ("owner", "expected_code"),
    [
        (None, "provider.metadata_invalid"),
        ("other-distribution", "provider.distribution_mismatch"),
        ("../private", "provider.metadata_invalid"),
    ],
)
def test_missing_foreign_or_malformed_distribution_refuses_before_load(
    monkeypatch: pytest.MonkeyPatch,
    owner: str | None,
    expected_code: str,
) -> None:
    chosen = _entry(owner=owner)
    _install(monkeypatch, (chosen,))
    result = _diagnose()
    assert result.code == expected_code
    assert not result.load_attempted
    assert chosen.load_calls == 0
    assert "private" not in result.message


@pytest.mark.parametrize(
    "target",
    [
        None,
        "",
        "fake\n:run",
        "target " + "z" * 1100,
        "missing_colon",
        "scoreform..operations:factory",
    ],
)
def test_malformed_target_refused_without_loading(
    monkeypatch: pytest.MonkeyPatch, target: object
) -> None:
    chosen = _entry(target=target)
    _install(monkeypatch, (chosen,))
    result = _diagnose()
    assert result.code == "provider.metadata_invalid"
    assert chosen.load_calls == 0


@pytest.mark.parametrize(
    ("name", "distribution"),
    [
        ("", "scoreform"),
        ("../scoreform", "scoreform"),
        ("ScoreForm", "scoreform"),
        ("scoreform", "bad/path"),
        ("scoreform", ""),
        ("scoreform", " " * 258),
    ],
)
def test_invalid_requested_identity_or_owner_rejected_before_enumeration(
    monkeypatch: pytest.MonkeyPatch, name: str, distribution: str
) -> None:
    calls = _install(monkeypatch, (_entry(),))
    with pytest.raises(ProviderDiagnosticRequestError):
        _diagnose(name=name, distribution=distribution)
    assert not calls


def test_exact_expected_distribution_is_pep503_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chosen = _entry(owner="pds_core_scoreform")
    _install(monkeypatch, (chosen,))
    result = _diagnose(distribution="pds-core-scoreform")
    assert result.code == "provider.valid"
    assert chosen.load_calls == 1


def test_selected_load_or_factory_failure_remains_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chosen = _entry(loaded=ImportError("SECRET_STUDENT_PATH"))
    _install(monkeypatch, (chosen,))
    result = _diagnose()
    assert result.code == "provider.load_failed"
    assert "SECRET" not in result.message

    def raised() -> ModuleOperationsProfile:
        raise RuntimeError("SECRET_STUDENT_PATH")

    called = _entry(loaded=raised)
    _install(monkeypatch, (called,))
    second = _diagnose()
    assert second.code == "provider.call_failed"
    assert "SECRET" not in second.message


@pytest.mark.parametrize(
    ("loaded", "code"),
    [
        (object(), "provider.not_callable"),
        (lambda: {}, "provider.profile_invalid"),
        (lambda: _profile("quillan"), "provider.identity_mismatch"),
        (
            lambda: _profile("scoreform", frozenset({"100"})),
            "provider.core_incompatible",
        ),
    ],
)
def test_invalid_selected_profile_is_not_admitted(
    monkeypatch: pytest.MonkeyPatch, loaded: object, code: str
) -> None:
    _install(monkeypatch, (_entry(loaded=loaded),))
    result = _diagnose()
    assert result.code == code
    assert result.validated_profile is None


def test_broad_diagnostic_retains_original_all_candidates_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _entry()
    other = _entry("quillan", owner="quillan")
    _install(monkeypatch, (other, first))
    results = diagnose_core_providers(provider_kind="module_operations")
    assert [result.code for result in results] == ["provider.valid", "provider.valid"]
    assert first.load_calls == other.load_calls == 1


def test_metadata_enumeration_failure_stays_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, (), fail=True)
    with pytest.raises(ProviderEnumerationError) as raised:
        _diagnose()
    assert "PRIVATE_KEY" not in str(raised.value)


def test_invalid_provider_kind_fails_before_enumeration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install(monkeypatch, (_entry(),))
    with pytest.raises(ProviderDiagnosticRequestError):
        diagnose_selected_core_provider(
            provider_kind="other",  # type: ignore[arg-type]
            entry_point_name="scoreform",
            expected_distribution="scoreform",
        )
    assert not calls


def test_str_subclass_duplicate_selected_name_is_not_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NamedString(str):
        pass

    chosen = _entry()
    imposter = _entry(NamedString("scoreform"), owner="foreign-distribution")
    _install(monkeypatch, (chosen, imposter))
    result = _diagnose()
    assert result.code == "provider.entry_point_ambiguous"
    assert chosen.load_calls == imposter.load_calls == 0


def test_single_str_subclass_identity_is_rejected_preload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NamedString(str):
        pass

    selected = _entry(NamedString("scoreform"))
    _install(monkeypatch, (selected,))
    result = _diagnose()
    assert result.code == "provider.metadata_invalid"
    assert selected.load_calls == 0


def test_diagnosis_does_not_execute_independent_attention_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def attention(_request: ModuleOperationsRequest) -> ModuleAttentionReport:
        calls.append("attention")
        return ModuleAttentionReport(evaluation="evaluated")

    def factory() -> ModuleOperationsProfile:
        calls.append("factory")
        return ModuleOperationsProfile(
            module_id="scoreform",
            supported_core_operations_contract_versions=frozenset({"1"}),
            attention_provider=attention,
        )

    _install(monkeypatch, (_entry(loaded=factory),))
    result = _diagnose()
    assert result.code == "provider.valid"
    assert calls == ["factory"]
    assert isinstance(result.validated_profile, ModuleOperationsProfile)
    outcome = invoke_module_attention(
        result.validated_profile, ModuleOperationsRequest()
    )
    assert outcome.code == "module_operations.evaluated"
    assert calls == ["factory", "attention"]


def test_one_failed_selected_owner_does_not_prevent_next_explicit_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = _entry(loaded=RuntimeError("PRIVATE_FAIL"))
    good = _entry("quillan", owner="quillan")
    _install(monkeypatch, (broken, good))
    first = _diagnose()
    assert first.code == "provider.load_failed"
    assert good.load_calls == 0
    second = _diagnose(name="quillan", distribution="quillan")
    assert second.code == "provider.valid"
    assert good.load_calls == 1
    assert broken.load_calls == 1
