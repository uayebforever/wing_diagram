import json
from pathlib import Path

from wing_diagram.propmap import PropMap

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_PROPMAP = _REPO_ROOT / "src" / "wing_diagram" / "propmap.jsonl"

_SAMPLE_ENTRIES = [
    {
        "id": 1,
        "name": "grp",
        "longname": "MAIN GROUP",
        "type": "string enum",
        "items": [
            {"item": "OFF", "longitem": "OFF"},
            {"item": "LCL", "longitem": "LOCAL IN"},
        ],
        "fullname": "/ch/1/in/conn/grp",
    },
    {"id": 2, "name": "name", "longname": "NAME", "type": "string", "fullname": "/ch/1/name"},
    {
        "id": 3,
        "name": "stat",
        "type": "string enum",
        "items": [{"item": "OK"}],
        "fullname": "/$stat/A/stat",
    },
]
_SAMPLE_LINES = "\n".join(json.dumps(entry) for entry in _SAMPLE_ENTRIES) + "\n"


def _write_sample_propmap(path: Path) -> Path:
    propmap_path = path / "propmap.jsonl"
    propmap_path.write_text(_SAMPLE_LINES)
    return propmap_path


def test_describe_resolves_leading_slash(tmp_path: Path) -> None:
    propmap = PropMap.load(_write_sample_propmap(tmp_path))

    entry = propmap.describe("ch/1/in/conn/grp")
    assert entry is not None
    assert propmap.describe("/ch/1/in/conn/grp") is entry
    assert entry.display_name == "MAIN GROUP"


def test_describe_unknown_path_returns_none(tmp_path: Path) -> None:
    propmap = PropMap.load(_write_sample_propmap(tmp_path))

    assert propmap.describe("ch/1/does/not/exist") is None


def test_entry_display_name_falls_back_to_name(tmp_path: Path) -> None:
    propmap = PropMap.load(_write_sample_propmap(tmp_path))

    entry = propmap.describe("$stat/A/stat")
    assert entry is not None
    assert entry.display_name == "stat"


def test_resolve_enum_uses_longitem(tmp_path: Path) -> None:
    propmap = PropMap.load(_write_sample_propmap(tmp_path))

    assert propmap.resolve("ch/1/in/conn/grp", "LCL") == "LOCAL IN"
    assert propmap.resolve("ch/1/in/conn/grp", "OFF") == "OFF"


def test_resolve_enum_falls_back_to_item_when_no_longitem(tmp_path: Path) -> None:
    propmap = PropMap.load(_write_sample_propmap(tmp_path))

    assert propmap.resolve("$stat/A/stat", "OK") == "OK"


def test_resolve_unknown_value_returns_raw(tmp_path: Path) -> None:
    propmap = PropMap.load(_write_sample_propmap(tmp_path))

    assert propmap.resolve("ch/1/in/conn/grp", "SOMETHING_NEW") == "SOMETHING_NEW"


def test_resolve_non_enum_type_returns_raw(tmp_path: Path) -> None:
    propmap = PropMap.load(_write_sample_propmap(tmp_path))

    assert propmap.resolve("ch/1/name", "Wren") == "Wren"


def test_resolve_unknown_path_returns_raw(tmp_path: Path) -> None:
    propmap = PropMap.load(_write_sample_propmap(tmp_path))

    assert propmap.resolve("ch/1/does/not/exist", 42) == 42


def test_load_against_real_propmap_file() -> None:
    propmap = PropMap.load(_SAMPLE_PROPMAP)

    assert len(propmap) > 50_000

    entry = propmap.describe("/ch/1/in/conn/grp")
    assert entry is not None
    assert entry.type == "string enum"
    assert propmap.resolve("/ch/1/in/conn/grp", "LCL") == "LOCAL IN"

    mtx_dir_in = propmap.describe("/mtx/1/dir/in")
    assert mtx_dir_in is not None
    assert {item.item for item in mtx_dir_in.items} == {
        "OFF", "AES", "MON.PH", "MON.SPK", "MON.BUS",
    }
