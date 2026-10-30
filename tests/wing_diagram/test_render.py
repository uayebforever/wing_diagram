from pathlib import Path

from wing_diagram.render import GraphvizRenderer
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


def test_render_writes_svg_by_default(tmp_path: Path) -> None:
    out_path = GraphvizRenderer().render(_sample_graph(), tmp_path / "diagram")

    assert out_path.suffix == ".svg"
    assert out_path.exists()
    content = out_path.read_text()
    assert "<svg" in content
    assert "Wren" in content
    assert "Sanctuary Mix" in content


def test_render_infers_format_from_out_path_suffix(tmp_path: Path) -> None:
    out_path = GraphvizRenderer().render(_sample_graph(), tmp_path / "diagram.png")

    assert out_path.suffix == ".png"
    assert out_path.exists()
    assert out_path.read_bytes().startswith(b"\x89PNG")


def test_render_empty_graph_does_not_error(tmp_path: Path) -> None:
    out_path = GraphvizRenderer().render(RoutingGraph(nodes=[], edges=[]), tmp_path / "empty.svg")

    assert out_path.exists()


def test_render_shows_node_detail_and_edge_level_label(tmp_path: Path) -> None:
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

    out_path = GraphvizRenderer().render(graph, tmp_path / "diagram.svg")

    content = out_path.read_text()
    assert "preamp +32.5 dB" in content
    assert "WING COMPRESSOR" in content
    assert "trim +3.5 dB" in content
    # Graphviz's SVG output escapes "-" as the `&#45;` entity, so check for
    # the digits rather than the literal minus sign.
    assert "6.2 dB" in content
    assert "POST FADER" in content


def test_render_key_source_edge_is_dashed_and_labelled(tmp_path: Path) -> None:
    graph = RoutingGraph(
        nodes=[
            Node(id=("ch", 13), kind="ch", label="Speakers"),
            Node(id=("ch", 7), kind="ch", label="Ambient", detail=("GATE · DUCKER",)),
        ],
        edges=[Edge(("ch", 13), ("ch", 7), {"kind": "key", "proc": "GATE"})],
    )

    out_path = GraphvizRenderer().render(graph, tmp_path / "diagram.svg")

    content = out_path.read_text()
    assert "KEY (GATE)" in content
    # Graphviz renders a dashed edge with a "stroke-dasharray" in the SVG.
    assert "stroke-dasharray" in content
