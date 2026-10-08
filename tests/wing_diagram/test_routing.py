import json
from pathlib import Path

from wing_diagram.propmap import PropMap
from wing_diagram.routing import Edge, build_routing_graph
from wing_diagram.snapfile import Snapshot, load_snapshot

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_SNAP = _REPO_ROOT / "wing_snaps" / "Announcements.snap"
_SAMPLE_PROPMAP = _REPO_ROOT / "src" / "wing_diagram" / "propmap.jsonl"

#: `io.<section>.<grp>` bank container labels -- direction-specific (e.g.
#: `LCL` is "LOCAL IN" under `io.in` but "LOCAL OUT" under `io.out`), unlike
#: the shared `grp`-*value* enum used elsewhere (`in.conn.grp`,
#: `io.out.*.grp`) where "LCL" always means "LOCAL IN" regardless of
#: direction. See `ai/schema-notes.md`.
_IN_GROUP_LABELS = {"LCL": "LOCAL IN", "A": "AES50 A", "USB": "USB AUDIO"}
_OUT_GROUP_LABELS = {"LCL": "LOCAL OUT", "A": "AES50 A"}


def _write_minimal_propmap(path: Path) -> Path:
    """A propmap with just enough `io.in`/`io.out` bank-container entries
    for `_io_group_label`'s fallback-label lookups in the tests below."""
    entries = [
        {"id": i, "name": grp, "longname": longname, "type": "node", "fullname": f"/io/in/{grp}"}
        for i, (grp, longname) in enumerate(_IN_GROUP_LABELS.items())
    ] + [
        {
            "id": 100 + i,
            "name": grp,
            "longname": longname,
            "type": "node",
            "fullname": f"/io/out/{grp}",
        }
        for i, (grp, longname) in enumerate(_OUT_GROUP_LABELS.items())
    ]
    propmap_path = path / "propmap.jsonl"
    propmap_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n")
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

    # ch 1's main/bus sends: `main.{1,2}` and `send.1` all carry `lvl`/
    # `pre`/`mode` in the real sample file, so every active send/main edge
    # now carries a resolved `level_db`/`tap` -- see
    # `ai/dynamics-and-levels-plan.md` section 1.4/2.
    assert Edge(("ch", 1), ("main", 1), {"level_db": 0, "tap": "POST FADER"}) in graph.edges
    assert Edge(("ch", 1), ("main", 2), {"level_db": 0, "tap": "POST FADER"}) in graph.edges
    assert Edge(("ch", 1), ("bus", 1), {"level_db": -144, "tap": "POST FADER"}) in graph.edges

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

    # Physical output jacks are labelled from the direction-specific
    # io.out.LCL bank ("LOCAL OUT"), not the direction-agnostic grp-value
    # enum ("LOCAL IN") that in.conn/io.out's own `grp` field shares with
    # io.in -- see ai/schema-notes.md.
    assert nodes_by_id[("io_out", "LCL", 8)].label == "LOCAL OUT 8"

    # main 3/4 are blank-named and untouched by any edge in this sample.
    assert ("main", 3) not in nodes_by_id
    assert ("main", 4) not in nodes_by_id

    # Outputs carrying the out-of-scope MON bus are not modelled as edges,
    # and the physical inputs that *only* feed MON (never used elsewhere)
    # are therefore not touched/included at all.
    assert ("io_out", "LCL", 1) not in nodes_by_id
    assert not any(e.dest == ("io_out", "LCL", 1) for e in graph.edges)

    # ch 1's preamp (on the physical input, not the channel) is at unity.
    assert nodes_by_id[("io_in", "LCL", 1)].detail == ("preamp +0.0 dB",)

    # ch 1 has an active Comp (no Gate); the badge resolves `mdl`'s enum
    # value through the propmap and includes threshold/make-up gain.
    assert nodes_by_id[("ch", 1)].detail == ("COMP · WING COMPRESSOR · thr -20 dB · gain +6 dB",)

    # ch 7 ("Ambient") has an active Gate-slot Ducker keyed off ch 13
    # ("Speakers") -- the manual's own example of a key source ("KEY
    # SOURCE: select another channel as the sidechain input" / the radio-
    # host ducker example). This is a real extra signal tap, rendered as
    # its own dashed "key" edge -- see `ai/dynamics-and-levels-plan.md`
    # section 1.3.
    assert nodes_by_id[("ch", 7)].detail == ("GATE · DUCKER · thr -20 dB",)
    assert Edge(("ch", 13), ("ch", 7), {"kind": "key", "proc": "GATE"}) in graph.edges


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

    # No `lvl`/`pre` in this minimal fixture -- `level_db` is omitted, and
    # `tap` falls back to "POST FADER" (a falsy/missing `pre` reads the
    # same as `pre: false`).
    assert Edge(("bus", 1), ("mtx", 2), {"tap": "POST FADER"}) in graph.edges


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


def test_unnamed_io_in_and_io_out_use_direction_specific_group_label(tmp_path: Path) -> None:
    """Regression test: an earlier version resolved an unnamed physical
    jack's fallback label via the shared `grp`-*value* enum (which is
    direction-agnostic -- "LCL" always means "LOCAL IN" there, even for
    an output), producing output jacks mislabeled "LOCAL IN n". The bank
    itself is direction-specific: `io.in.LCL` is "LOCAL IN",
    `io.out.LCL` is "LOCAL OUT". See `ai/schema-notes.md`.
    """
    propmap = _minimal_propmap(tmp_path)
    ae_data = {"io": {"out": {"LCL": {"3": {"grp": "USB", "in": 1}}}}}

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    nodes_by_id = {node.id: node for node in graph.nodes}
    assert nodes_by_id[("io_out", "LCL", 3)].label == "LOCAL OUT 3"


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


# --- Gain, dynamics, key-source, and tap-point detail -----------------------
# See `ai/dynamics-and-levels-plan.md`.


def _propmap(tmp_path: Path, entries: list[dict]) -> PropMap:
    propmap_path = tmp_path / "propmap.jsonl"
    propmap_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n")
    return PropMap.load(propmap_path)


def test_preamp_gain_shown_on_io_in_node(tmp_path: Path) -> None:
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "io": {"in": {"LCL": {"1": {"name": "Kick", "g": 32.5}}}},
        "ch": {"1": {"name": "", "in": {"conn": {"grp": "LCL", "in": 1}}}},
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    nodes_by_id = {node.id: node for node in graph.nodes}
    assert nodes_by_id[("io_in", "LCL", 1)].detail == ("preamp +32.5 dB",)


def test_input_trim_shown_on_edge_when_nonzero(tmp_path: Path) -> None:
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "ch": {
            "1": {
                "name": "Lead",
                "in": {"set": {"trim": 3.5}, "conn": {"grp": "LCL", "in": 1}},
            }
        }
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    assert Edge(("io_in", "LCL", 1), ("ch", 1), {"trim_db": 3.5}) in graph.edges


def test_input_trim_omitted_when_zero(tmp_path: Path) -> None:
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "ch": {
            "1": {
                "name": "Lead",
                "in": {"set": {"trim": 0}, "conn": {"grp": "LCL", "in": 1}},
            }
        }
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    assert Edge(("io_in", "LCL", 1), ("ch", 1)) in graph.edges


def test_bus_own_trim_shown_as_node_detail(tmp_path: Path) -> None:
    """`bus`/`main`/`mtx` have no single inbound edge to hang their own
    trim on (their content is an implicit sum of sends), so it's surfaced
    as node detail instead -- unlike `ch`/`aux`, which show it on their
    inbound source edge (see the trim tests above)."""
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "bus": {"1": {"name": "Sub", "in": {"set": {"trim": -2}}, "main": {"1": {"on": True}}}}
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    nodes_by_id = {node.id: node for node in graph.nodes}
    assert nodes_by_id[("bus", 1)].detail == ("trim -2.0 dB",)


def test_send_group_mode_has_no_independent_level(tmp_path: Path) -> None:
    """`GRP` ("GROUP") send mode is literally the channel's post-fader
    group output -- there's no independent level control, so `level_db`
    is omitted even though the fixture still carries a (meaningless) `lvl`
    value, same as the real console would."""
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "ch": {"1": {"name": "Lead", "send": {"1": {"on": True, "lvl": -6, "mode": "GRP"}}}}
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    assert Edge(("ch", 1), ("bus", 1), {"tap": "GROUP"}) in graph.edges


def test_send_pre_mode_uses_channel_tap_point(tmp_path: Path) -> None:
    propmap = _propmap(
        tmp_path,
        [
            {
                "id": 1,
                "name": "ptap",
                "longname": "TAP POINT",
                "type": "string enum",
                "items": [{"item": "FILT", "longitem": "FILTER"}],
                "fullname": "/ch/1/ptap",
            }
        ],
    )
    ae_data = {
        "ch": {
            "1": {
                "name": "Lead",
                "ptap": "FILT",
                "send": {"1": {"on": True, "lvl": -3, "mode": "PRE"}},
            }
        }
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    assert Edge(("ch", 1), ("bus", 1), {"level_db": -3, "tap": "TAP (FILTER)"}) in graph.edges


def test_send_post_mode_label(tmp_path: Path) -> None:
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "ch": {"1": {"name": "Lead", "send": {"1": {"on": True, "lvl": -3, "mode": "POST"}}}}
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    assert Edge(("ch", 1), ("bus", 1), {"level_db": -3, "tap": "POST FADER"}) in graph.edges


def test_bus_send_fixed_pre_fader_tap(tmp_path: Path) -> None:
    """`bus`/`main`/`mtx` sends have no `mode` at all -- just a `pre`
    boolean against a fixed (non-selectable) tap position."""
    propmap = _minimal_propmap(tmp_path)
    ae_data = {"bus": {"1": {"name": "Sub", "send": {"MX1": {"on": True, "lvl": 0, "pre": True}}}}}

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    assert Edge(("bus", 1), ("mtx", 1), {"level_db": 0, "tap": "PRE FADER"}) in graph.edges


def test_inactive_dynamics_are_not_shown(tmp_path: Path) -> None:
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "ch": {
            "1": {
                "name": "Lead",
                "gate": {"on": False, "mdl": "GATE", "thr": -40},
                "dyn": {"on": False, "mdl": "COMP", "thr": -20},
                "main": {"1": {"on": True}},
            }
        }
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    nodes_by_id = {node.id: node for node in graph.nodes}
    assert nodes_by_id[("ch", 1)].detail == ()


def test_dynamics_badge_falls_back_to_raw_model_without_propmap_entry(tmp_path: Path) -> None:
    """A dynamics model's `mdl` enum is resolved via the propmap when
    available (see the real-sample test), but defensively falls back to
    the raw value when it isn't -- the badge should never blow up just
    because one model's propmap entry wasn't loaded."""
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "bus": {
            "1": {
                "name": "Sub",
                "dyn": {"on": True, "mdl": "SBUS", "thr": -10},
                "main": {"1": {"on": True}},
            }
        }
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    nodes_by_id = {node.id: node for node in graph.nodes}
    assert nodes_by_id[("bus", 1)].detail == ("COMP · SBUS · thr -10 dB",)


def test_key_source_edge_for_comp_sidechain(tmp_path: Path) -> None:
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "bus": {
            "1": {
                "name": "Sub",
                "dyn": {"on": True, "mdl": "COMP", "thr": -10},
                "dynsc": {"src": "BUS.2"},
                "main": {"1": {"on": True}},
            },
            "2": {"name": "Drums", "main": {"1": {"on": True}}},
        }
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    assert Edge(("bus", 2), ("bus", 1), {"kind": "key", "proc": "COMP"}) in graph.edges


def test_self_key_source_produces_no_key_edge(tmp_path: Path) -> None:
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "ch": {
            "1": {
                "name": "Lead",
                "dyn": {"on": True, "mdl": "COMP", "thr": -10},
                "dynsc": {"src": "SELF"},
                "main": {"1": {"on": True}},
            }
        }
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    assert not any(e.meta.get("kind") == "key" for e in graph.edges)


def test_disabled_dynamics_produces_no_key_edge(tmp_path: Path) -> None:
    """A configured key source on a disabled processor isn't a live signal
    path -- consistent with the project's "active only" rule."""
    propmap = _minimal_propmap(tmp_path)
    ae_data = {
        "ch": {
            "1": {
                "name": "Lead",
                "dyn": {"on": False, "mdl": "COMP", "thr": -10},
                "dynsc": {"src": "CH.2"},
                "main": {"1": {"on": True}},
            },
            "2": {"name": "Other", "main": {"1": {"on": True}}},
        }
    }

    graph = build_routing_graph(_snapshot(ae_data), propmap)

    assert not any(e.meta.get("kind") == "key" for e in graph.edges)
