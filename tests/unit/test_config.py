"""Configuration and filesystem-layout tests."""

from __future__ import annotations

from pathlib import Path

from vinastudio import config


def test_app_home_honours_environment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VINASTUDIO_HOME", str(tmp_path / "custom"))
    home = config.app_home()
    assert home == tmp_path / "custom"
    assert home.is_dir()


def test_derived_directories_are_created_under_home(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VINASTUDIO_HOME", str(tmp_path))
    for factory in (config.jobs_dir, config.cache_dir, config.projects_dir, config.logs_dir):
        created = factory()
        assert created.is_dir()
        assert created.parent == tmp_path


def test_dev_server_url_is_opt_in(monkeypatch) -> None:
    monkeypatch.delenv(config.DEV_SERVER_ENV, raising=False)
    assert config.dev_server_url() is None
    monkeypatch.setenv(config.DEV_SERVER_ENV, "http://127.0.0.1:5173")
    assert config.dev_server_url() == "http://127.0.0.1:5173"


def test_scoring_weight_counts_match_the_vina_contract() -> None:
    # Vina exposes 7 tunable weights; Vinardo and AutoDock4 expose 6.
    assert config.SCORING_WEIGHT_COUNT == {"vina": 7, "vinardo": 6, "ad4": 6}


def test_only_vina_and_vinardo_compute_maps_natively() -> None:
    # AutoDock4 requires maps produced by AutoGrid4, which is not bundled.
    assert set(config.NATIVE_MAP_SCORING) == {"vina", "vinardo"}
    assert "ad4" not in config.NATIVE_MAP_SCORING


def test_defaults_mirror_the_vina_command_line() -> None:
    defaults = config.DEFAULTS
    assert defaults.scoring == "vina"
    assert defaults.exhaustiveness == 8
    assert defaults.n_poses == 20
    assert defaults.min_rmsd == 1.0
    assert defaults.spacing == 0.375
    assert defaults.energy_range == 3.0
    assert defaults.cpu == 0  # 0 means "use every available core"
