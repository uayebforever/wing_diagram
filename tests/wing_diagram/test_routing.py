import json
from pathlib import Path

from wing_diagram.propmap import PropMap
from wing_diagram.routing import Edge, build_routing_graph
from wing_diagram.snapfile import Snapshot, load_snapshot

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_SNAP = _REPO_ROOT / "wing_snaps" / "Announcements.snap"
_SAMPLE_PROPMAP = _REPO_ROOT / "src" / "wing_diagram" / "propmap.jsonl"

_GROUP_LABELS = {
    "OFF": "OFF",
    "LCL": "LOCAL IN",
    "AUX": "AUX IN",
    "A": "AES50 A",
    "B": "AES50 B",
    "C": "AES50 C",
    "SC": "ST CONNECT",
    "USB": "USB AUDIO",
    "CRD": "WLIVE PLAY",
    "MOD": "MODULE",
    "PLAY": "USB PLAYER",
    "AES": "AES/EBU IN",
    "USR": "USER SIGNAL",
    "OSC": "OSCILLATOR",
    "BUS": "BUS",
    "MAIN": "MAIN",
    "MTX": "MATRIX",
    "SEND": "FX SEND",
    "MON": "MONITOR",
}


def _write_minimal_propmap(path: Path) -> Path:
    """A propmap with just enough to resolve `io/out/LCL/1/grp` group labels."""
    entry = {
        "id": 1,
        "name": "grp",
        "type": "string enum",
        "items": [{"item": k, "longitem": v} for k, v in _GROUP_LABELS.items()],
        "fullname": "/io/out/LCL/1/grp",
    }
    propmap_path = path / "propmap.jsonl"
    propmap_path.write_text(json.dumps(entry) + "\n")
    return propmap_path


def _minimal_propmap(tmp_path: Path) -> PropMap:
    return PropMap.load(_write_minimal_propmap(tmp_path))


def _snapshot(ae_data: dict) -> Snapshot:
    return Snapshot(header={}, ae_data=ae_data)


# --- Tests against the real sample snapshot --------------------------------


def test_build_routing_graph_against_real_sample() -> None:
    snapshot = load_snapshot(_SAMPLE_SNAP)
    propmap = PropMap.load(_SAMPLE_PROPMAP)

    graph = build_routing_graph(snapshot, propmap)

    nodes_by_id = {node.id: node for node in graph.nodes}

    # Physical input "Wren" feeds ch 1, which has a blank own name and so
    # falls back to the source's label.
    assert nodes_by_id[("io_in", "LCL", 1)].label == "Wren"
    assert nodes_by_id[("ch", 1)].label == "Wren"
    assert Edge(("io_in", "LCL", 1), ("ch", 1)) in graph.edges
    assert Edge(("ch", 1), ("main", 1)) in graph.edges
    assert Edge(("ch", 1), ("main", 2)) in graph.edges
    assert Edge(("ch", 1), ("bus", 1)) in graph.edges

    # ch 13 is re-patched from bus 1 ("Speakers"), not a physical input, and
    # has a blank own name -- falls back to the bus's label.
    assert nodes_by_id[("bus", 1)].label == "Speakers"
    assert nodes_by_id[("ch", 13)].label == "Speakers"
    assert Edge(("bus", 1), ("ch", 13)) in graph.edges

    # Physical outputs carrying mains (direct patch, not via io.in).
    # `io.out`'s `in` is a flat 1-based L/R tap number -- 2 taps per main,
    # always, regardless of that main's own mono/stereo setting -- not the
    # main's own index. main 1 ("Sanctuary Mix") is mono-downmixed but
    # still occupies taps 1 and 2; its R tap (2) is the one actually
    # patched out to LCL 8. main 2 ("Stream Mix") is genuinely stereo,
    # occupying taps 3 (L) and 4 (R), patched to LCL 5 and LCL 6
    # respectively. See `ai/schema-notes.md`.
    assert Edge(("main", 1), ("io_out", "LCL", 8), {"channel": "R"}) in graph.edges
    assert Edge(("main", 2), ("io_out", "LCL", 5), {"channel": "L"}) in graph.edges
    assert Edge(("main", 2), ("io_out", "LCL", 6), {"channel": "R"}) in graph.edges

    # main 3/4 are blank-named and untouched by any edge in this sample.
    assert ("main", 3) not in nodes_by_id
    assert ("main", 4) not in nodes_by_id

    # Outputs carrying the out-of-scope MON bus are not modelled as edges,
    # and the physical inputs that *only* feed MON (never used elsewhere)
    # are therefore not touched/included at all.
    assert ("io_out", "LCL", 1) not in nodes_by_id
    assert not any(e.dest == ("io_out", "LCL", 1) for e in graph.edges)


def test_disconnected_physical_inputs_are_not_included() -> None:
    snapshot = load_snapshot(_SAMPLE_SNAP)
    propmap = PropMap.load(_SAMPLE_PROPMAP)

    graph = build_routing_graph(snapshot, propmap)

    # AES50-A input 1 is not patched to anything in the sample file.
    assert ("io_in", "A", 1) not in {node.id for node in graph.nodes}


# --- Synthetic unit tests ---------------------------------------------------


def test_altsrc_true_uses_alt_source(tmp_path: Path) -> None:
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "ch": {
            "1": {
                "name": "",
                "in": {
                    "set": {"altsrc": True},
                    "conn": {"grp": "LCL", "in": 1, "altgrp": "USB", "altin": 2},
                },
                "main": {"1": {"on": True}},
            }
        }
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    assert Edge(("io_in", "USB", 2), ("ch", 1)) in graph.edges
    assert not any(e.source == ("io_in", "LCL", 1) for e in graph.edges)


def test_altsrc_false_uses_primary_source(tmp_path: Path) -> None:
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "ch": {
            "1": {
                "name": "",
                "in": {
                    "set": {"altsrc": False},
                    "conn": {"grp": "LCL", "in": 1, "altgrp": "USB", "altin": 2},
                },
                "main": {},
            }
        }
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    assert Edge(("io_in", "LCL", 1), ("ch", 1)) in graph.edges


def test_inactive_sends_are_not_edges(tmp_path: Path) -> None:
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "ch": {
            "1": {
                "name": "Lead",
                "in": {"conn": {"grp": "OFF"}},
                "main": {"1": {"on": False}},
                "send": {"1": {"on": False}, "MX1": {"on": False}},
            }
        }
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    assert graph.edges == []
    # The channel itself is untouched -- no active connection at all -- and
    # so isn't included as a disconnected node.
    assert graph.nodes == []


def test_send_to_matrix_via_mx_key(tmp_path: Path) -> None:
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "bus": {
            "1": {
                "name": "Sub",
                "main": {},
                "send": {"MX2": {"on": True}},
            }
        }
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    assert Edge(("bus", 1), ("mtx", 2)) in graph.edges


def test_fx_send_and_monitor_sources_are_skipped(tmp_path: Path) -> None:
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "io": {
            "out": {
                "LCL": {
                    "1": {"grp": "SEND", "in": 1},
                    "2": {"grp": "MON", "in": 1},
                    "3": {"grp": "OFF", "in": 1},
                }
            }
        }
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    assert graph.edges == []
    assert graph.nodes == []


def test_io_out_direct_physical_passthrough(tmp_path: Path) -> None:
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "io": {
            "in": {"USB": {"1": {"name": "Playback L"}}},
            "out": {"LCL": {"3": {"grp": "USB", "in": 1}}},
        }
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    assert Edge(("io_in", "USB", 1), ("io_out", "LCL", 3)) in graph.edges


def test_io_out_internal_source_uses_flattened_lr_taps(tmp_path: Path) -> None:
    """`io.out`'s `in`, for an internal re-patch `grp`, is a flat 1-based
    L/R tap number (2 taps per element, always) -- not that element's own
    index. Taps 1-2 are element 1 (L, R), taps 3-4 are element 2 (L, R),
    etc. This holds even for a mono-downmixed element: it still reserves
    (and duplicates its signal across) both taps. Mirrors the real
    "Sanctuary Mix" (mono main 1, patched out via its R tap) / "Stream
    Mix" (stereo main 2, L and R both patched out) case in
    `Announcements.snap`. See `ai/schema-notes.md`.
    """
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "io": {
            "out": {
                "LCL": {
                    "1": {"grp": "MAIN", "in": 1},  # main 1, L
                    "2": {"grp": "MAIN", "in": 2},  # main 1, R
                    "3": {"grp": "MAIN", "in": 3},  # main 2, L
                    "4": {"grp": "MAIN", "in": 4},  # main 2, R
                    "5": {"grp": "BUS", "in": 5},  # bus 3, L
                    "6": {"grp": "MTX", "in": 1},  # mtx 1, L
                }
            }
        }
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    assert Edge(("main", 1), ("io_out", "LCL", 1), {"channel": "L"}) in graph.edges
    assert Edge(("main", 1), ("io_out", "LCL", 2), {"channel": "R"}) in graph.edges
    assert Edge(("main", 2), ("io_out", "LCL", 3), {"channel": "L"}) in graph.edges
    assert Edge(("main", 2), ("io_out", "LCL", 4), {"channel": "R"}) in graph.edges
    assert Edge(("bus", 3), ("io_out", "LCL", 5), {"channel": "L"}) in graph.edges
    assert Edge(("mtx", 1), ("io_out", "LCL", 6), {"channel": "L"}) in graph.edges


def test_unnamed_io_out_falls_back_to_group_label(tmp_path: Path) -> None:
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "main": {"1": {"name": "", "send": {}}},
        "io": {"out": {"A": {"12": {"grp": "MAIN", "in": 1}}}},
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    nodes_by_id = {node.id: node for node in graph.nodes}
    assert nodes_by_id[("io_out", "A", 12)].label == "AES50 A 12"
    assert nodes_by_id[("main", 1)].label == "Main 1"


def test_node_and_edge_ordering_is_deterministic(tmp_path: Path) -> None:
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "ch": {
            "2": {"name": "Two", "in": {"conn": {"grp": "LCL", "in": 2}}, "main": {"1": {"on": True}}},
            "1": {"name": "One", "in": {"conn": {"grp": "LCL", "in": 1}}, "main": {"1": {"on": True}}},
        }
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    # io_in nodes (rank 0) before ch nodes (rank 1), each in index order.
    assert [n.id for n in graph.nodes] == [
        ("io_in", "LCL", 1),
        ("io_in", "LCL", 2),
        ("ch", 1),
        ("ch", 2),
        ("main", 1),
    ]
