import json
from pathlib import Path

from wing_diagram.propmap import PropMap
from wing_diagram.snapdiff import (
    ParamChange,
    build_diff_report,
    diff_snapshots,
    format_change,
    group_changes,
)
from wing_diagram.snapfile import Snapshot, load_snapshot

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_PROPMAP = _REPO_ROOT / "src" / "wing_diagram" / "propmap.jsonl"
_SAMPLE_SNAP_A = _REPO_ROOT / "wing_snaps" / "Announcements.snap"
_SAMPLE_SNAP_B = _REPO_ROOT / "wing_snaps" / "Test2.snap"

_SAMPLE_ENTRIES = [
    {"id": 1, "name": "ch", "longname": "CHANNEL", "type": "node", "fullname": "/ch"},
    {"id": 2, "name": "name", "longname": "NAME", "type": "string", "fullname": "/ch/3/name"},
    {"id": 3, "name": "gate", "longname": "GATE", "type": "node", "fullname": "/ch/3/gate"},
    {
        "id": 4,
        "name": "on",
        "longname": "GATE",
        "type": "integer",
        "fullname": "/ch/3/gate/on",
    },
    {
        "id": 5,
        "name": "GATE",
        "longname": "GATE",
        "type": "node",
        "fullname": "/ch/3/gate/GATE",
    },
    {
        "id": 6,
        "name": "thr",
        "longname": "THR",
        "type": "linear float",
        "unit": "dB",
        "fullname": "/ch/3/gate/GATE/thr",
    },
    {"id": 10, "name": "in", "longname": "INPUT", "type": "node", "fullname": "/ch/3/in"},
    {
        "id": 11,
        "name": "conn",
        "longname": "CONNECTION",
        "type": "node",
        "fullname": "/ch/3/in/conn",
    },
    {
        "id": 7,
        "name": "grp",
        "longname": "MAIN GROUP",
        "type": "string enum",
        "items": [
            {"item": "OFF", "longitem": "OFF"},
            {"item": "LCL", "longitem": "LOCAL IN"},
        ],
        "fullname": "/ch/3/in/conn/grp",
    },
    {"id": 8, "name": "LCL", "longname": "LOCAL IN", "type": "node", "fullname": "/io/in/LCL"},
    {"id": 9, "name": "cfg", "longname": "CONFIG", "type": "node", "fullname": "/cfg"},
]


def _write_sample_propmap(path: Path) -> Path:
    propmap_path = path / "propmap.jsonl"
    propmap_path.write_text("\n".join(json.dumps(e) for e in _SAMPLE_ENTRIES) + "\n")
    return propmap_path


def _propmap(tmp_path: Path) -> PropMap:
    return PropMap.load(_write_sample_propmap(tmp_path))


def _snapshot(ae_data: dict) -> Snapshot:
    return Snapshot(header={}, ae_data=ae_data)


# --- diff_snapshots ----------------------------------------------------------


def test_diff_snapshots_finds_changed_added_removed_leaves() -> None:
    old = _snapshot({"ch": {"3": {"gate": {"on": False, "thr": -20}}}})
    new = _snapshot({"ch": {"3": {"gate": {"on": True, "thr": -20, "range": 10}}}})

    changes = diff_snapshots(old, new)

    by_path = {c.path: c for c in changes}
    assert by_path["ch/3/gate/on"].kind == "changed"
    assert by_path["ch/3/gate/on"].old is False
    assert by_path["ch/3/gate/on"].new is True
    assert by_path["ch/3/gate/range"].kind == "added"
    assert by_path["ch/3/gate/range"].old is None
    assert "ch/3/gate/thr" not in by_path


def test_diff_snapshots_detects_removed_leaf() -> None:
    old = _snapshot({"ch": {"3": {"name": "Vocal"}}})
    new = _snapshot({"ch": {"3": {}}})

    changes = diff_snapshots(old, new)

    assert changes == [ParamChange(path="ch/3/name", old="Vocal", new=None)]
    assert changes[0].kind == "removed"


def test_diff_snapshots_identical_snapshots_has_no_changes() -> None:
    data = {"ch": {"3": {"name": "Vocal"}}}

    assert diff_snapshots(_snapshot(data), _snapshot(data)) == []


# --- group_changes / heading ------------------------------------------------


def test_group_changes_headings_use_element_name_and_section_label(tmp_path: Path) -> None:
    propmap = _propmap(tmp_path)
    old = _snapshot({"ch": {"3": {"name": "Vocal", "gate": {"on": False}}}})
    new = _snapshot({"ch": {"3": {"name": "Vocal", "gate": {"on": True}}}})

    groups = group_changes(diff_snapshots(old, new), old, new, propmap)

    assert len(groups) == 1
    assert groups[0].prefix == "ch/3"
    assert groups[0].heading == "Ch 3 — Vocal"


def test_group_changes_heading_falls_back_to_bare_label_without_a_name(tmp_path: Path) -> None:
    propmap = _propmap(tmp_path)
    old = _snapshot({"ch": {"3": {"gate": {"on": False}}}})
    new = _snapshot({"ch": {"3": {"gate": {"on": True}}}})

    groups = group_changes(diff_snapshots(old, new), old, new, propmap)

    assert groups[0].heading == "Ch 3"


def test_group_changes_separates_different_elements(tmp_path: Path) -> None:
    propmap = _propmap(tmp_path)
    old = _snapshot({"ch": {"3": {"gate": {"on": False}}, "4": {"gate": {"on": False}}}})
    new = _snapshot({"ch": {"3": {"gate": {"on": True}}, "4": {"gate": {"on": True}}}})

    groups = group_changes(diff_snapshots(old, new), old, new, propmap)

    assert [g.prefix for g in groups] == ["ch/3", "ch/4"]


def test_group_changes_non_indexed_section_uses_propmap_label(tmp_path: Path) -> None:
    propmap = _propmap(tmp_path)
    old = _snapshot({"cfg": {"muteovr": False}})
    new = _snapshot({"cfg": {"muteovr": True}})

    groups = group_changes(diff_snapshots(old, new), old, new, propmap)

    assert groups[0].prefix == "cfg"
    assert groups[0].heading == "CONFIG"


# --- format_change -----------------------------------------------------------


def test_format_change_dedupes_repeated_model_segment_label(tmp_path: Path) -> None:
    propmap = _propmap(tmp_path)
    change = ParamChange(path="ch/3/gate/GATE/thr", old=-20.0, new=-18.0)

    text = format_change(change, "ch/3", propmap)

    assert text == "GATE > THR: -20.00 dB → -18.00 dB"


def test_format_change_resolves_enum_values(tmp_path: Path) -> None:
    propmap = _propmap(tmp_path)
    change = ParamChange(path="ch/3/in/conn/grp", old="OFF", new="LCL")

    text = format_change(change, "ch/3", propmap)

    assert text == "INPUT > CONNECTION > MAIN GROUP: OFF → LOCAL IN"


def test_format_change_renders_boolean_as_on_off(tmp_path: Path) -> None:
    propmap = _propmap(tmp_path)
    change = ParamChange(path="ch/3/gate/on", old=False, new=True)

    text = format_change(change, "ch/3", propmap)

    assert text == "GATE: Off → On"


def test_format_change_added_and_removed_phrasing(tmp_path: Path) -> None:
    propmap = _propmap(tmp_path)

    added = format_change(ParamChange(path="ch/3/name", old=None, new="Vocal"), "ch/3", propmap)
    removed = format_change(ParamChange(path="ch/3/name", old="Vocal", new=None), "ch/3", propmap)

    assert added == "NAME: added (Vocal)"
    assert removed == "NAME: removed (was Vocal)"


# --- build_diff_report --------------------------------------------------------


def test_build_diff_report_no_differences(tmp_path: Path) -> None:
    propmap = _propmap(tmp_path)
    data = {"ch": {"3": {"name": "Vocal"}}}

    report = build_diff_report(_snapshot(data), _snapshot(data), propmap, title="Same")

    assert "# Same" in report
    assert "No differences." in report


def test_build_diff_report_includes_heading_and_change_lines(tmp_path: Path) -> None:
    propmap = _propmap(tmp_path)
    old = _snapshot({"ch": {"3": {"name": "Vocal", "gate": {"on": False}}}})
    new = _snapshot({"ch": {"3": {"name": "Vocal", "gate": {"on": True}}}})

    report = build_diff_report(old, new, propmap, title="Test diff")

    assert "# Test diff" in report
    assert "## Ch 3 — Vocal" in report
    assert "GATE: Off → On" in report
    assert "1 parameter changed across 1 element." in report


# --- real sample files --------------------------------------------------------


def test_diff_report_runs_against_real_sample_snapshots() -> None:
    propmap = PropMap.load(_SAMPLE_PROPMAP)
    old = load_snapshot(_SAMPLE_SNAP_A)
    new = load_snapshot(_SAMPLE_SNAP_B)

    changes = diff_snapshots(old, new)
    report = build_diff_report(old, new, propmap, title="Announcements → Test2")

    assert len(changes) > 0
    assert "# Announcements → Test2" in report
    assert "parameter" in report and "changed across" in report
