from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import graphviz

from .routing import Node, NodeId, RoutingGraph

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


class Renderer(ABC):
    """Renders a `RoutingGraph` to a file. Implementation-agnostic boundary."""

    @abstractmethod
    def render(self, graph: RoutingGraph, out_path: Path) -> Path:
        """Render `graph` to `out_path` and return the path actually written."""
        raise NotImplementedError()


class GraphvizRenderer(Renderer):
    """Renders a `RoutingGraph` as a left-to-right Graphviz diagram.

    Basic v1 implementation: one box per node, colored by kind, laid out
    left-to-right by rank group (see `_RANK_GROUPS`). Edges carry a label
    only when `Edge.meta["channel"]` is set -- currently just the L/R tap
    an `io.out` edge was patched from when its source is a stereo
    bus/main/mtx (see `wing_diagram.routing._resolve_output_source`);
    every other edge (channel/aux/bus sends, physical passthrough) is a
    full stereo-to-stereo or mono-to-mono connection with nothing to
    disambiguate, so it's left unlabeled. This exists mainly to let the
    routing graph be eyeballed against the real console; refine the
    visuals separately once the routing side is validated.
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
                        label=node.label,
                        fillcolor=_NODE_COLORS.get(node.kind, "#ffffff"),
                    )

        for edge in graph.edges:
            channel = edge.meta.get("channel")
            dot.edge(
                _dot_node_id(edge.source),
                _dot_node_id(edge.dest),
                label=channel if channel else "",
                fontsize="10",
            )

        return dot


def _dot_id(node: Node) -> str:
    return _dot_node_id(node.id)


def _dot_node_id(node_id: NodeId) -> str:
    return "_".join(str(part) for part in node_id)
