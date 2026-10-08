from pathlib import Path

import pytest

from wing_diagram.exceptions import UserError
from wing_diagram.render import MermaidRenderer
from wing_diagram.routing import Edge, Node, RoutingGraph


def _sample_graph() -> RoutingGraph:
    return RoutingGraph(
        nodes=[
            Node(id=("io_in", "LCL", 1), kind="io_in", label="Wren"),
            Node(id=("ch", 1), kind="ch", label="Wren"),
            Node(id=("main", 1), kind="main", label="Sanctuary Mix"),
        ],
        edges=[
            Edge(("io_in", "LCL", 1), ("ch", 1)),
            Edge(("ch", 1), ("main", 1)),
        ],
    )


def test_render_writes_mmd_by_default(tmp_path: Path) -> None:
    out_path = MermaidRenderer().render(_sample_graph(), tmp_path / "diagram")

    assert out_path.suffix == ".mmd"
    assert out_path.exists()
    content = out_path.read_text()
    assert "flowchart LR" in content
    assert "layout: elk" in content
    assert "Wren" in content
    assert "Sanctuary Mix" in content


def test_render_accepts_mmd_suffix_directly(tmp_path: Path) -> None:
    out_path = MermaidRenderer().render(_sample_graph(), tmp_path / "diagram.mmd")

    assert out_path == tmp_path / "diagram.mmd"
    assert out_path.exists()


def test_render_writes_self_contained_html_preview(tmp_path: Path) -> None:
    out_path = MermaidRenderer().render(_sample_graph(), tmp_path / "diagram.html")

    assert out_path == tmp_path / "diagram.html"
    content = out_path.read_text()
    assert "<html>" in content
    assert "mermaid" in content.lower()
    # The Mermaid source is HTML-escaped and embedded for client-side rendering.
    assert "flowchart LR" in content


def test_render_rejects_unsupported_suffix(tmp_path: Path) -> None:
    with pytest.raises(UserError):
        MermaidRenderer().render(_sample_graph(), tmp_path / "diagram.svg")


def test_render_empty_graph_does_not_error(tmp_path: Path) -> None:
    out_path = MermaidRenderer().render(RoutingGraph(nodes=[], edges=[]), tmp_path / "empty.mmd")

    assert out_path.exists()
    assert "flowchart LR" in out_path.read_text()


def test_render_splits_config_detail_from_dynamics_detail(tmp_path: Path) -> None:
    graph = RoutingGraph(
        nodes=[
            Node(
                id=("io_in", "LCL", 1),
                kind="io_in",
                label="Wren",
                detail=("preamp +32.5 dB",),
            ),
            Node(
                id=("ch", 1),
                kind="ch",
                label="Wren",
                detail=("COMP · WING COMPRESSOR · thr -20 dB",),
            ),
            Node(id=("main", 1), kind="main", label="Sanctuary Mix"),
        ],
        edges=[
            Edge(("io_in", "LCL", 1), ("ch", 1), {"trim_db": 3.5}),
            Edge(("ch", 1), ("main", 1), {"level_db": -6.2, "tap": "POST FADER"}),
        ],
    )

    content = MermaidRenderer()._build_mermaid(graph)

    # Config detail (preamp/trim) renders in the small plain-grey style.
    assert "font-size:0.75em;color:#555" in content
    assert "preamp +32.5 dB" in content
    assert "trim +3.5 dB" in content
    # Dynamics detail (Gate/Comp) renders below a divider, in small italic.
    assert "<hr " in content
    assert "font-size:0.7em;font-style:italic" in content
    assert "WING COMPRESSOR" in content
    # Edge labels still show level/tap.
    assert "6.2 dB" in content
    assert "POST FADER" in content
    # A named channel is disambiguated with its kind/index.
    assert "Ch 1: Wren" in content


def test_render_key_source_edge_is_dashed_and_colored(tmp_path: Path) -> None:
    graph = RoutingGraph(
        nodes=[
            Node(id=("ch", 13), kind="ch", label="Speakers"),
            Node(id=("ch", 7), kind="ch", label="Ambient", detail=("GATE · DUCKER",)),
        ],
        edges=[Edge(("ch", 13), ("ch", 7), {"kind": "key", "proc": "GATE"})],
    )

    content = MermaidRenderer()._build_mermaid(graph)

    assert "-.->" in content
    assert "KEY (GATE)" in content
    assert "stroke-dasharray:6 4" in content
    assert "#b35900" in content


def test_render_applies_classdef_colors_matching_graphviz(tmp_path: Path) -> None:
    content = MermaidRenderer()._build_mermaid(_sample_graph())

    assert "classDef io_in fill:#cfe8ff" in content
    assert "classDef ch fill:#d9f2d9" in content
    assert "classDef main fill:#ffd9d9" in content


def test_render_does_not_duplicate_bare_fallback_label(tmp_path: Path) -> None:
    graph = RoutingGraph(
        nodes=[Node(id=("ch", 5), kind="ch", label="Ch 5")],
        edges=[],
    )

    content = MermaidRenderer()._build_mermaid(graph)

    assert "Ch 5: Ch 5" not in content
    assert "Ch 5" in content
