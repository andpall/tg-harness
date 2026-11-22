import pytest
from tg_harness import config


def test_parse_workdirs_names_by_folder_default_first(tmp_path):
    (tmp_path / "alpha").mkdir(); (tmp_path / "beta").mkdir()
    workdirs = config.parse_workdirs(str(tmp_path / "beta"), f" {tmp_path / 'alpha'} ,,")
    assert workdirs == {"beta": str(tmp_path / "beta"), "alpha": str(tmp_path / "alpha")}
    assert list(workdirs)[0] == "beta"


def test_parse_workdirs_defaults_to_repo():
    assert config.parse_workdirs(".", "") == {config.ROOT.name: str(config.ROOT)}


def test_parse_workdirs_rejects_missing_and_duplicate_names(tmp_path):
    (tmp_path / "one" / "app").mkdir(parents=True); (tmp_path / "two" / "app").mkdir(parents=True)
    with pytest.raises(AssertionError, match="not found"):
        config.parse_workdirs(".", str(tmp_path / "missing"))
    with pytest.raises(AssertionError, match="two workdirs"):
        config.parse_workdirs(str(tmp_path / "one" / "app"), str(tmp_path / "two" / "app"))
