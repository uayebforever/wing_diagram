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


def test_render_omits_label_for_default_post_fader_send() -> None:
    graph = RoutingGraph(
        nodes=[
            Node(id=("ch", 1), kind="ch", label="Ch 1"),
            Node(id=("main", 1), kind="main", label="Sanctuary Mix"),
        ],
        edges=[Edge(("ch", 1), ("main", 1), {"level_db": 0.0, "tap": "POST FADER"})],
    )

    content = MermaidRenderer()._build_mermaid(graph)

    assert "POST FADER" not in content
    assert "n_ch_1 --> n_main_1" in content


def test_render_shares_one_label_for_matching_non_default_sends() -> None:
    graph = RoutingGraph(
        nodes=[
            Node(id=("ch", 1), kind="ch", label="Ch 1"),
            Node(id=("bus", 1), kind="bus", label="Bus 1"),
            Node(id=("bus", 2), kind="bus", label="Bus 2"),
        ],
        edges=[
            Edge(("ch", 1), ("bus", 1), {"level_db": -20.0, "tap": "PRE FADER"}),
            Edge(("ch", 1), ("bus", 2), {"level_db": -20.0, "tap": "PRE FADER"}),
        ],
    )

    content = MermaidRenderer()._build_mermaid(graph)

    # The matching label is shown exactly once, on a shared label node that
    # the source fans out through to both destinations.
    assert content.count("PRE FADER") == 1
    assert "n_ch_1 --> n_label_n_ch_1_0" in content
    assert "n_label_n_ch_1_0 --> n_bus_1" in content
    assert "n_label_n_ch_1_0 --> n_bus_2" in content


def test_render_keeps_separate_labels_for_differing_sends() -> None:
    graph = RoutingGraph(
        nodes=[
            Node(id=("ch", 1), kind="ch", label="Ch 1"),
            Node(id=("bus", 1), kind="bus", label="Bus 1"),
            Node(id=("bus", 2), kind="bus", label="Bus 2"),
        ],
        edges=[
            Edge(("ch", 1), ("bus", 1), {"level_db": -20.0, "tap": "PRE FADER"}),
            Edge(("ch", 1), ("bus", 2), {"level_db": -6.0, "tap": "POST FADER"}),
        ],
    )

    content = MermaidRenderer()._build_mermaid(graph)

    assert "n_ch_1 -->|" in content
    assert "n_label_" not in content
    assert "PRE FADER" in content
    assert "6.0 dB" in content


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


def test_render_declares_nodes_in_the_graphs_given_order() -> None:
    """Node *declaration* order is what `elk.forceNodeModelOrder` (see
    `MermaidRenderer`) preserves as the final top-to-bottom layout order --
    so `_build_mermaid` must declare nodes in `graph.nodes`' given order
    (which `routing.build_routing_graph` already sorts ascending by index)
    rather than reordering them itself."""
    graph = RoutingGraph(
        nodes=[
            Node(id=("ch", 1), kind="ch", label="Wren"),
            Node(id=("ch", 7), kind="ch", label="Ambient"),
            Node(id=("ch", 13), kind="ch", label="Speakers"),
            Node(id=("io_in", "LCL", 1), kind="io_in", label="Wren"),
            Node(id=("io_in", "LCL", 9), kind="io_in", label="Choir Solo"),
        ],
        edges=[],
    )

    content = MermaidRenderer()._build_mermaid(graph)

    assert content.index("n_ch_1[") < content.index("n_ch_7[") < content.index("n_ch_13[")
    assert content.index("n_io_in_LCL_1[") < content.index("n_io_in_LCL_9[")


def test_render_orders_physical_inputs_by_their_channel_assignment() -> None:
    """With `forceNodeModelOrder` on, ELK never reorders nodes to cut down
    on crossings -- so a physical input declared in raw hardware-id order
    regardless of which channel it feeds (e.g. an AES50 input patched to a
    channel near the bottom of the channel list, declared ahead of local
    inputs patched to channels near the top) draws one edge that cuts
    across every other input-to-channel edge. `_build_mermaid` instead
    declares inputs in the order of the channel each is patched to."""
    graph = RoutingGraph(
        nodes=[
            Node(id=("io_in", "A", 1), kind="io_in", label="Matched Pair"),
            Node(id=("io_in", "LCL", 1), kind="io_in", label="Wren"),
            Node(id=("io_in", "LCL", 2), kind="io_in", label="Wendy"),
            Node(id=("ch", 1), kind="ch", label="Wren"),
            Node(id=("ch", 2), kind="ch", label="Wendy"),
            Node(id=("ch", 10), kind="ch", label="Choir"),
        ],
        edges=[
            Edge(("io_in", "A", 1), ("ch", 10)),
            Edge(("io_in", "LCL", 1), ("ch", 1)),
            Edge(("io_in", "LCL", 2), ("ch", 2)),
        ],
    )

    content = MermaidRenderer()._build_mermaid(graph)

    assert (
        content.index("n_io_in_LCL_1[")
        < content.index("n_io_in_LCL_2[")
        < content.index("n_io_in_A_1[")
    )


def test_render_keeps_hardware_order_for_inputs_without_a_channel_target() -> None:
    """A physical input with no direct ch/aux edge (e.g. a hardware
    passthrough straight to an output) has no channel position to sort by,
    so it keeps its relative hardware-id order, trailing inputs that do
    have a channel target."""
    graph = RoutingGraph(
        nodes=[
            Node(id=("io_in", "LCL", 1), kind="io_in", label="Direct"),
            Node(id=("io_in", "LCL", 2), kind="io_in", label="Wendy"),
            Node(id=("ch", 2), kind="ch", label="Wendy"),
            Node(id=("io_out", "CRD", 1), kind="io_out", label="Exp Card 1"),
        ],
        edges=[
            Edge(("io_in", "LCL", 1), ("io_out", "CRD", 1)),
            Edge(("io_in", "LCL", 2), ("ch", 2)),
        ],
    )

    content = MermaidRenderer()._build_mermaid(graph)

    assert content.index("n_io_in_LCL_2[") < content.index("n_io_in_LCL_1[")


def test_render_does_not_wrap_flow_nodes_in_subgraphs() -> None:
    """A Mermaid `subgraph` is its own nested ELK layout problem and was
    observed to silently stop `forceNodeModelOrder` from applying to the
    nodes inside it -- see `MermaidRenderer`'s docstring. The legend is the
    one deliberate exception, since it has no edges into the signal-flow
    graph for `forceNodeModelOrder` to preserve order for."""
    content = MermaidRenderer()._build_mermaid(_sample_graph())

    assert content.count("subgraph") == 1
    assert "subgraph legend" in content


def test_render_pins_rank_order_with_invisible_anchor_edges() -> None:
    """ELK's layered algorithm assigns each node's layer itself, by longest
    path from a source -- it ignores declaration order entirely for *which*
    layer a node lands in (only `forceNodeModelOrder` controls order
    *within* a layer, see above). A `bus` node reached in one hop from `ch`,
    just like a `main` node, can end up sharing a layer with `main` instead
    of coming before it as `_RANK_GROUPS` intends -- and an edge routed
    into it then cuts across `main`'s boxes to get there. A chain of
    invisible (`~~~`) edges through one dummy anchor node per rank
    boundary forces strict layer order instead, without subgraphs (which
    break `forceNodeModelOrder`, see `test_render_does_not_wrap_flow_nodes_in_subgraphs`)."""
    graph = RoutingGraph(
        nodes=[
            Node(id=("io_in", "LCL", 1), kind="io_in", label="Wren"),
            Node(id=("ch", 1), kind="ch", label="Wren"),
            Node(id=("bus", 1), kind="bus", label="Speach"),
            Node(id=("main", 1), kind="main", label="Sanctuary Mix"),
            Node(id=("io_out", "CRD", 1), kind="io_out", label="Exp Card 1"),
        ],
        edges=[
            Edge(("io_in", "LCL", 1), ("ch", 1)),
            Edge(("ch", 1), ("bus", 1)),
            Edge(("ch", 1), ("main", 1)),
            Edge(("main", 1), ("io_out", "CRD", 1)),
        ],
    )

    content = MermaidRenderer()._build_mermaid(graph)

    # One dummy anchor node per boundary between the 5 non-empty ranks here.
    assert content.count("rank_anchor_") >= 4 * 2  # declared + referenced in edges
    assert "classDef rankanchor fill:none,stroke:none;" in content
    # Every node gets an invisible edge in from the previous rank's anchor
    # and out to its own rank's anchor -- `bus` included, pinning it ahead
    # of `main` even though both are one hop from `ch`.
    assert "n_bus_1 ~~~ rank_anchor_" in content
    assert "~~~ n_bus_1" in content
    assert "n_main_1 ~~~ rank_anchor_" in content
    assert "~~~ n_main_1" in content


def test_render_sets_elk_model_order_options() -> None:
    content = MermaidRenderer()._build_mermaid(_sample_graph())

    assert "forceNodeModelOrder: true" in content
    assert "preset: modelOrder" in content


def test_render_includes_title_in_frontmatter_when_given() -> None:
    content = MermaidRenderer()._build_mermaid(_sample_graph(), title="Announcements")

    assert 'title: "Announcements"' in content


def test_render_omits_title_when_not_given() -> None:
    content = MermaidRenderer()._build_mermaid(_sample_graph())

    assert "title:" not in content


def test_render_escapes_quotes_in_title() -> None:
    content = MermaidRenderer()._build_mermaid(_sample_graph(), title='Front "House" Mix')

    assert 'title: "Front \\"House\\" Mix"' in content


def test_render_includes_a_legend_with_kind_colors() -> None:
    content = MermaidRenderer()._build_mermaid(_sample_graph())

    assert "subgraph legend[Legend]" in content
    assert 'legend_io_in["Input"]' in content
    assert 'legend_ch["Channel / Aux"]' in content
    assert 'legend_bus["Bus"]' in content
    assert 'legend_main["Main / Matrix"]' in content
    assert 'legend_io_out["Output"]' in content
    # Legend swatches get the same classDef colors as the real nodes.
    class_lines = [line for line in content.splitlines() if line.strip().startswith("class ")]
    assert any("legend_io_in" in line and line.rstrip().endswith("io_in;") for line in class_lines)


def test_render_swaps_hardware_designation_to_title_for_named_input() -> None:
    graph = RoutingGraph(
        nodes=[
            Node(
                id=("io_in", "LCL", 3),
                kind="io_in",
                label="Wendy",
                detail=("LOCAL IN 3", "preamp +0.0 dB"),
            ),
        ],
        edges=[],
    )

    content = MermaidRenderer()._build_mermaid(graph)

    assert "<div><b>LOCAL IN 3</b></div>" in content
    # The name moves down to the first detail line, ahead of the preamp line.
    assert "Wendy<br/>preamp +0.0 dB" in content


def test_render_does_not_swap_title_for_unnamed_input() -> None:
    graph = RoutingGraph(
        nodes=[
            Node(
                id=("io_in", "LCL", 3),
                kind="io_in",
                label="LOCAL IN 3",
                detail=("preamp +0.0 dB",),
            ),
        ],
        edges=[],
    )

    content = MermaidRenderer()._build_mermaid(graph)

    assert "<div><b>LOCAL IN 3</b></div>" in content
    assert "preamp +0.0 dB" in content
