from pathlib import Path

import pytest

from wing_diagram.exceptions import UserError
from wing_diagram.render import D2Renderer
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
    out_path = D2Renderer().render(_sample_graph(), tmp_path / "diagram.svg")

    assert out_path.suffix == ".svg"
    assert out_path.exists()
    content = out_path.read_text()
    assert "<svg" in content
    assert "Wren" in content
    assert "Sanctuary Mix" in content


def test_render_infers_format_from_out_path_suffix(tmp_path: Path) -> None:
    # PNG (unlike SVG) goes through d2's bundled Playwright, which fetches
    # its driver from the network on first use -- skip rather than fail in
    # a sandbox with no egress to playwright's CDN, since that's an
    # environment limitation, not something `D2Renderer` controls.
    try:
        out_path = D2Renderer().render(_sample_graph(), tmp_path / "diagram.png")
    except UserError as e:
        if "playwright" in str(e).lower():
            pytest.skip(f"d2's Playwright driver isn't reachable in this environment: {e}")
        raise

    assert out_path.suffix == ".png"
    assert out_path.exists()
    assert out_path.read_bytes().startswith(b"\x89PNG")


def test_render_empty_graph_does_not_error(tmp_path: Path) -> None:
    out_path = D2Renderer().render(RoutingGraph(nodes=[], edges=[]), tmp_path / "empty.svg")

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

    out_path = D2Renderer().render(graph, tmp_path / "diagram.svg")

    content = out_path.read_text()
    assert "preamp +32.5 dB" in content
    assert "WING COMPRESSOR" in content
    assert "trim +3.5 dB" in content
    assert "-6.2 dB" in content
    assert "POST FADER" in content
    # The `\n` line-break escape in a D2 label must survive to an actual
    # line break -- not a literal backslash-n -- see `_d2_label`.
    assert "\\n" not in content


def test_render_includes_title_when_given(tmp_path: Path) -> None:
    out_path = D2Renderer().render(_sample_graph(), tmp_path / "diagram.svg", title="Announcements")

    content = out_path.read_text()
    assert "Announcements" in content


def test_render_key_source_edge_is_dashed_and_labelled(tmp_path: Path) -> None:
    graph = RoutingGraph(
        nodes=[
            Node(id=("ch", 13), kind="ch", label="Speakers"),
            Node(id=("ch", 7), kind="ch", label="Ambient", detail=("GATE · DUCKER",)),
        ],
        edges=[Edge(("ch", 13), ("ch", 7), {"kind": "key", "proc": "GATE"})],
    )

    out_path = D2Renderer().render(graph, tmp_path / "diagram.svg")

    content = out_path.read_text()
    assert "KEY (GATE)" in content
    assert "stroke-dasharray" in content


def test_render_raises_user_error_when_d2_is_not_on_path(tmp_path: Path) -> None:
    with pytest.raises(UserError, match="PATH"):
        D2Renderer(d2_path="not-a-real-d2-executable").render(
            _sample_graph(), tmp_path / "diagram.svg"
        )


def test_build_d2_sets_elk_layout_engine() -> None:
    content = D2Renderer()._build_d2(_sample_graph())

    assert "layout-engine: elk" in content


def test_build_d2_omits_edge_label_for_standard_unity_post_fader_send() -> None:
    graph = RoutingGraph(
        nodes=[
            Node(id=("ch", 1), kind="ch", label="Wren"),
            Node(id=("bus", 1), kind="bus", label="Speech"),
        ],
        edges=[Edge(("ch", 1), ("bus", 1), {"level_db": 0.0, "tap": "POST FADER"})],
    )

    content = D2Renderer()._build_d2(graph)

    assert "n_ch_1 -> n_bus_1\n" in content
    assert "POST FADER" not in content


def test_build_d2_node_label_is_markdown_in_an_explicit_rectangle() -> None:
    graph = RoutingGraph(
        nodes=[
            Node(
                id=("ch", 1),
                kind="ch",
                label="Wren",
                detail=("preamp +32.5 dB", "COMP · WING COMPRESSOR · thr -20 dB"),
            ),
        ],
        edges=[],
    )

    content = D2Renderer()._build_d2(graph)

    assert "label: |||md" in content
    assert "**Ch 1: Wren**" in content
    assert "preamp +32.5 dB" in content
    # Dynamics badges are italic; plain config detail is not.
    assert "*COMP · WING COMPRESSOR · thr -20 dB*" in content
    assert "*preamp" not in content
    # Without an explicit shape D2 would drop the box around a Markdown label.
    assert "shape: rectangle" in content


def test_build_d2_escapes_markdown_syntax_in_node_labels() -> None:
    graph = RoutingGraph(
        nodes=[Node(id=("ch", 1), kind="ch", label="Kick | Snare_*1*", detail=())],
        edges=[],
    )

    content = D2Renderer()._build_d2(graph)

    assert "Kick \\| Snare\\_\\*1\\*" in content


def test_build_d2_layout_engine_is_selectable() -> None:
    content = D2Renderer(layout_engine="tala")._build_d2(_sample_graph())

    assert "layout-engine: tala" in content
    assert "layout-engine: elk" not in content
