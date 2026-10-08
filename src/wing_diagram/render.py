from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import graphviz

from .routing import Edge, Node, NodeId, RoutingGraph

#: Left-to-right rank groups: nodes in the same group get `rank=same`, and
#: groups are declared in this order so Graphviz lays the diagram out as a
#: signal-flow chain, as per `ai/initial-plan.md`.
_RANK_GROUPS: tuple[tuple[str, ...], ...] = (
    ("io_in",),
    ("ch", "aux"),
    ("bus",),
    ("main", "mtx"),
    ("io_out",),
)

_NODE_COLORS = {
    "io_in": "#cfe8ff",
    "io_out": "#ffe0b3",
    "ch": "#d9f2d9",
    "aux": "#d9f2d9",
    "bus": "#f2e6ff",
    "main": "#ffd9d9",
    "mtx": "#ffd9d9",
}

#: Key (sidechain) edges are a control tap into a Gate/Comp, not an audio
#: signal path -- rendered dashed, in a distinct color, and non-rank-
#: `constraint`-ing so a bus/main/matrix keying off a later-ranked element
#: doesn't warp the left-to-right signal-flow layout. See
#: `ai/dynamics-and-levels-plan.md` section 2.
_KEY_EDGE_COLOR = "#b35900"


class Renderer(ABC):
    """Renders a `RoutingGraph` to a file. Implementation-agnostic boundary."""

    @abstractmethod
    def render(self, graph: RoutingGraph, out_path: Path) -> Path:
        """Render `graph` to `out_path` and return the path actually written."""
        raise NotImplementedError()


class GraphvizRenderer(Renderer):
    """Renders a `RoutingGraph` as a left-to-right Graphviz diagram.

    One box per node, colored by kind, laid out left-to-right by rank
    group (see `_RANK_GROUPS`). A node's box also shows any `detail` lines
    (preamp gain, own trim, active Gate/Comp badges) under its label, and
    an edge's label shows whichever of its `meta` applies -- L/R tap,
    send/main level + tap point, or input trim (see `_node_label`/
    `_edge_label`, and `ai/dynamics-and-levels-plan.md` section 2). Key
    (sidechain) edges are drawn separately: dashed, a distinct color, and
    non-rank-constraining, since they're a control tap rather than an
    audio path.
    """

    def __init__(self, format: str | None = None) -> None:
        """`format` is a Graphviz output format (`"svg"`, `"png"`, `"pdf"`,
        ...). Defaults to inferring it from `out_path`'s suffix at render
        time, falling back to `"svg"` if it has none."""
        self._format = format

    def render(self, graph: RoutingGraph, out_path: Path) -> Path:
        out_path = Path(out_path)
        format = self._format or out_path.suffix.lstrip(".") or "svg"
        dot = self._build_dot(graph, format)
        rendered = dot.render(
            filename=out_path.stem, directory=str(out_path.parent) or ".", cleanup=True
        )
        return Path(rendered)

    def _build_dot(self, graph: RoutingGraph, format: str) -> graphviz.Digraph:
        dot = graphviz.Digraph(
            name="wing_routing",
            format=format,
            graph_attr={"rankdir": "LR", "splines": "spline"},
            node_attr={"shape": "box", "style": "filled", "fontname": "Helvetica"},
        )

        nodes_by_kind: dict[str, list[Node]] = {}
        for node in graph.nodes:
            nodes_by_kind.setdefault(node.kind, []).append(node)

        for rank_index, kinds in enumerate(_RANK_GROUPS):
            rank_nodes = [n for kind in kinds for n in nodes_by_kind.get(kind, [])]
            if not rank_nodes:
                continue
            with dot.subgraph(name=f"rank_{rank_index}") as sub:  # pyright: ignore [reportOptionalContextManager]
                sub.attr(rank="same")
                for node in rank_nodes:
                    sub.node(
                        _dot_id(node),
                        label=_node_label(node),
                        fillcolor=_NODE_COLORS.get(node.kind, "#ffffff"),
                    )

        for edge in graph.edges:
            if edge.meta.get("kind") == "key":
                dot.edge(
                    _dot_node_id(edge.source),
                    _dot_node_id(edge.dest),
                    label=f"KEY ({edge.meta['proc']})" if edge.meta.get("proc") else "KEY",
                    fontsize="10",
                    style="dashed",
                    color=_KEY_EDGE_COLOR,
                    fontcolor=_KEY_EDGE_COLOR,
                    constraint="false",
                )
                continue
            dot.edge(
                _dot_node_id(edge.source),
                _dot_node_id(edge.dest),
                label=_edge_label(edge),
                fontsize="10",
            )

        return dot


def _node_label(node: Node) -> str:
    """`node.label` plus any `detail` lines (preamp gain, own trim, active
    Gate/Comp badges), each on its own line. `\\n` is Graphviz's line-break
    escape inside a plain (non-HTML) label -- see `ai/dynamics-and-levels-
    plan.md` section 2."""
    return "\\n".join((node.label, *node.detail))


def _edge_label(edge: Edge) -> str:
    """Builds an edge's label from whichever of `channel` (an `io_out`
    edge's L/R tap), `level_db`/`tap` (a send/main edge's level and where
    it's tapped from), or `trim_db` (an input edge's channel trim) is
    present in `edge.meta` -- these are mutually exclusive by edge kind
    (see `ai/dynamics-and-levels-plan.md` section 2), so simply collecting
    whichever apply is safe."""
    parts: list[str] = []
    channel = edge.meta.get("channel")
    if channel:
        parts.append(channel)
    level_db = edge.meta.get("level_db")
    if level_db is not None:
        parts.append(_format_level(level_db))
    tap = edge.meta.get("tap")
    if tap:
        parts.append(tap)
    trim_db = edge.meta.get("trim_db")
    if trim_db is not None:
        parts.append(f"trim {trim_db:+.1f} dB")
    return "\\n".join(parts)


def _format_level(level_db: float) -> str:
    if level_db <= -144:
        return "-∞ dB"
    return f"{level_db:+.1f} dB"


def _dot_id(node: Node) -> str:
    return _dot_node_id(node.id)


def _dot_node_id(node_id: NodeId) -> str:
    return "_".join(str(part) for part in node_id)
