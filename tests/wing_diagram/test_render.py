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
