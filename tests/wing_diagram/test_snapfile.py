import json
from pathlib import Path

import pytest

from wing_diagram.exceptions import UserError
from wing_diagram.snapfile import load_snapshot

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_SNAP = _REPO_ROOT / "wing_snaps" / "Announcements.snap"


def test_load_snapshot_header_fields() -> None:
    snapshot = load_snapshot(_SAMPLE_SNAP)

    assert snapshot.type == "snapshot.11"
    assert snapshot.creator_model == "WING-EDIT"
    assert snapshot.creator_fw == "VERSION_FULL"
    assert snapshot.created is not None


def test_get_traverses_nested_path() -> None:
    snapshot = load_snapshot(_SAMPLE_SNAP)

    assert snapshot.get("ch/1/in/conn/grp") == "LCL"
    assert snapshot.get("/ch/1/in/conn/grp") == "LCL"
    assert snapshot.get("ch/1/in/conn/in") == 1


def test_get_missing_path_returns_default() -> None:
    snapshot = load_snapshot(_SAMPLE_SNAP)

    assert snapshot.get("ch/1/does/not/exist") is None
    assert snapshot.get("ch/1/does/not/exist", default="fallback") == "fallback"
    assert snapshot.get("ch/999/name") is None


def test_load_snapshot_rejects_file_without_ae_data(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.snap"
    bogus.write_text(json.dumps({"type": "snapshot.11"}))

    with pytest.raises(UserError):
        load_snapshot(bogus)
