from __future__ import annotations

import html
from abc import ABC, abstractmethod
from pathlib import Path

import graphviz

from .exceptions import UserError
from .routing import Edge, Node, NodeId, RoutingGraph

#: Left-to-right rank groups: nodes in the same group get `rank=same`
#: (Graphviz) or sit in the same `subgraph` (Mermaid), and groups are
#: declared in this order so the layout engine produces a signal-flow
#: chain, as per `ai/initial-plan.md`.
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

#: Matching border/stroke colour for each `_NODE_COLORS` fill -- Graphviz
#: doesn't need these (it only fills), Mermaid's `classDef` wants both.
_NODE_STROKE_COLORS = {
    "io_in": "#5b9bd5",
    "io_out": "#d58a3d",
    "ch": "#5aa15a",
    "aux": "#5aa15a",
    "bus": "#9b6fd1",
    "main": "#d16b6b",
    "mtx": "#d16b6b",
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
    parts = _edge_label_parts(edge)
    return "\\n".join(parts)


def _edge_label_parts(edge: Edge) -> list[str]:
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
    return parts


def _format_level(level_db: float) -> str:
    if level_db <= -144:
        return "-∞ dB"
    return f"{level_db:+.1f} dB"


def _dot_id(node: Node) -> str:
    return _dot_node_id(node.id)


def _dot_node_id(node_id: NodeId) -> str:
    return "_".join(str(part) for part in node_id)


#: `node.detail` lines starting with one of these are dynamics (Gate/Comp)
#: badges rather than plain config values (preamp gain, trim) -- these are
#: the fixed prefixes `routing._dynamics_badge` always uses, so sniffing
#: for them is safe. Mermaid renders the two kinds of detail differently
#: (see `MermaidRenderer`): config stays plain small type, dynamics gets
#: its own small-italic style below a divider.
_DYNAMICS_DETAIL_PREFIXES = ("GATE", "COMP")


class MermaidRenderer(Renderer):
    """Renders a `RoutingGraph` as a Mermaid flowchart.

    Uses Mermaid's `elk` layout engine for orthogonal edge routing with
    rounded corners (straight segments, not Graphviz's curved splines),
    and `elk.mergeEdges` so that edges sharing a source or destination
    bundle into a shared trunk instead of criss-crossing independently --
    the closest built-in approximation of "edges should only overlap when
    they share an end".

    Node kinds keep the same fill/stroke colors as `GraphvizRenderer` (via
    `classDef`/`class`), and nodes are declared in the same left-to-right
    `_RANK_GROUPS` order to keep the signal-flow layout -- as a declaration
    order rather than a Mermaid `subgraph`, since ELK treats a `subgraph` as
    its own nested layout problem and silently stops respecting node order
    inside it (see `elk.forceNodeModelOrder` below).

    `elk.forceNodeModelOrder` (+ the `modelOrder` preset) keeps nodes within
    a layer in declaration order -- i.e. ascending by index, since
    `graph.nodes` already comes pre-sorted that way -- rather than ELK's
    default crossing-minimization reordering them freely. This also happens
    to be what keeps a signal-in edge and a signal-out edge from ever
    landing on the same side of a node: ELK's free reordering was what let
    e.g. a monitor-feed edge (bus/main/mtx back into a channel) and a
    sidechain "key" edge end up sharing a node's east side, making the two
    arrowheads ambiguous; with model order enforced, a same-layer edge like
    a key tap instead routes via the node's north/south side.

    A node's label is rendered as HTML (Mermaid's `htmlLabels`, on by
    default) so detail lines can use a different style than the main
    label: plain config detail (preamp gain, trim) is shown in small grey
    type, and dynamics badges (Gate/Comp) are shown below a divider rule
    in smaller italic type -- both the "smaller type" and the "visually
    separated" asks are covered by the same divider+font-size treatment.

    Only `.mmd` (Mermaid source) and `.html` (a self-contained preview
    page that renders it client-side via a CDN-hosted Mermaid) are
    produced directly -- Mermaid has no local-only SVG/PNG export the way
    Graphviz's `dot` binary does, so `render()` raises for any other
    suffix with a pointer to how to convert the `.mmd` output.
    """

    def render(self, graph: RoutingGraph, out_path: Path) -> Path:
        out_path = Path(out_path)
        suffix = out_path.suffix.lower()
        source = self._build_mermaid(graph)

        if suffix in ("", ".mmd", ".mermaid"):
            target = out_path if suffix else out_path.with_suffix(".mmd")
            target.write_text(source)
            return target
        if suffix == ".html":
            out_path.write_text(_wrap_html(source))
            return out_path
        raise UserError(
            f"MermaidRenderer can't write {suffix!r} directly -- write a '.mmd' "
            "or '.html' output instead, then convert the '.mmd' with the Mermaid "
            "CLI (`mmdc`), the VS Code/GitHub Mermaid preview, or "
            "https://mermaid.live."
        )

    def _build_mermaid(self, graph: RoutingGraph) -> str:
        lines: list[str] = [
            "---",
            "config:",
            "  layout: elk",
            "  elk:",
            "    mergeEdges: true",
            #: `modelOrder` + `forceNodeModelOrder` keep nodes within a layer in
            #: the order we declare them (ascending by index, since
            #: `graph.nodes` already comes pre-sorted that way) instead of
            #: ELK's default crossing-minimization freely reordering them.
            #: Also incidentally what gets the sidechain/monitor-feed "key"
            #: edges routed via a node's north/south side rather than sharing
            #: an east/west port with its main signal edges -- see the
            #: "never share an attachment point" note on `MermaidRenderer`.
            "    preset: modelOrder",
            "    forceNodeModelOrder: true",
            "    considerModelOrder: NODES_AND_EDGES",
            "---",
            "flowchart LR",
        ]

        for kind, fill in _NODE_COLORS.items():
            stroke = _NODE_STROKE_COLORS[kind]
            lines.append(f"  classDef {kind} fill:{fill},stroke:{stroke},color:#1a1a1a;")

        nodes_by_kind: dict[str, list[Node]] = {}
        for node in graph.nodes:
            nodes_by_kind.setdefault(node.kind, []).append(node)

        #: Nodes are declared flat (not wrapped in a Mermaid `subgraph` per
        #: rank group) -- ELK treats a `subgraph` as its own nested layout
        #: problem, which was overriding `forceNodeModelOrder` and reordering
        #: nodes within it regardless. `_RANK_GROUPS` still controls the
        #: order nodes are *declared* in, which `forceNodeModelOrder` then
        #: preserves in the actual layout.
        class_members: dict[str, list[str]] = {}
        for kinds in _RANK_GROUPS:
            for node in (n for kind in kinds for n in nodes_by_kind.get(kind, [])):
                mid = _mermaid_id(node.id)
                lines.append(f'  {mid}["{_node_html_label(node)}"]')
                class_members.setdefault(node.kind, []).append(mid)

        key_edge_indices: list[int] = []
        for edge_index, edge in enumerate(graph.edges):
            src = _mermaid_id(edge.source)
            dst = _mermaid_id(edge.dest)
            if edge.meta.get("kind") == "key":
                label = f"KEY ({edge.meta['proc']})" if edge.meta.get("proc") else "KEY"
                lines.append(f'  {src} -.->|"{_small_html(label)}"| {dst}')
                key_edge_indices.append(edge_index)
                continue
            parts = _edge_label_parts(edge)
            if parts:
                label_html = _small_html("<br/>".join(_esc(p) for p in parts), escape=False)
                lines.append(f'  {src} -->|"{label_html}"| {dst}')
            else:
                lines.append(f"  {src} --> {dst}")

        for kind, members in class_members.items():
            lines.append(f"  class {','.join(members)} {kind};")

        for idx in key_edge_indices:
            lines.append(
                f"  linkStyle {idx} stroke:{_KEY_EDGE_COLOR},stroke-width:1.5px,"
                "stroke-dasharray:6 4;"
            )

        return "\n".join(lines) + "\n"


def _node_html_label(node: Node) -> str:
    """Builds a node's HTML label: a bold title line, then plain config
    detail (if any) in small grey type, then dynamics badges (if any)
    below a divider rule in smaller italic type. See `MermaidRenderer`."""
    parts = [f"<div><b>{_esc(_node_title(node))}</b></div>"]

    config_lines = [d for d in node.detail if not d.startswith(_DYNAMICS_DETAIL_PREFIXES)]
    dynamics_lines = [d for d in node.detail if d.startswith(_DYNAMICS_DETAIL_PREFIXES)]

    if config_lines:
        joined = "<br/>".join(_esc(d) for d in config_lines)
        parts.append(f"<div style='font-size:0.75em;color:#555'>{joined}</div>")
    if dynamics_lines:
        joined = "<br/>".join(_esc(d) for d in dynamics_lines)
        parts.append(
            "<hr style='margin:3px 0;border:none;border-top:1px solid #bbb'/>"
            f"<div style='font-size:0.7em;font-style:italic;color:#444'>{joined}</div>"
        )
    return "".join(parts)


def _node_title(node: Node) -> str:
    """`node.label`, prefixed with `"<Kind> <n>: "` for a kind that has a
    numeric index (`ch`/`aux`/`bus`/`main`/`mtx`) and a label distinct from
    that same bare `"<Kind> <n>"` fallback -- so a named channel reads as
    e.g. `"Ch 1: Wren"` rather than just `"Wren"` (ambiguous against an
    `io_in` node that happens to share the same name), while an unnamed
    channel (whose label already *is* the bare fallback, per
    `routing._make_node`) isn't shown twice."""
    kind = node.kind
    if kind in ("ch", "aux", "bus", "main", "mtx"):
        bare = f"{kind.capitalize() if kind != 'mtx' else 'Mtx'} {node.id[1]}"
        if node.label == bare:
            return bare
        return f"{bare}: {node.label}"
    return node.label


def _small_html(text: str, escape: bool = True) -> str:
    content = _esc(text) if escape else text
    return f"<span style='font-size:0.75em'>{content}</span>"


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _mermaid_id(node_id: NodeId) -> str:
    return "n_" + "_".join(str(part) for part in node_id)


def _wrap_html(mermaid_source: str) -> str:
    """A self-contained preview page: loads Mermaid and its `elk` layout
    plugin from a CDN and renders `mermaid_source` client-side. No local
    Mermaid/Node install needed -- just a browser with network access."""
    escaped_source = html.escape(mermaid_source)
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>WING routing diagram</title>
  <style>
    body {{ margin: 0; padding: 1rem; font-family: sans-serif; }}
    #diagram svg {{ max-width: 100%; height: auto; }}
  </style>
</head>
<body>
  <div id="diagram">Rendering...</div>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@12/dist/mermaid.esm.min.mjs";
    import elkLayouts from "https://cdn.jsdelivr.net/npm/@mermaid-js/layout-elk@1/dist/mermaid-layout-elk.esm.min.mjs";
    mermaid.registerLayoutLoaders(elkLayouts);
    mermaid.initialize({{ startOnLoad: false, securityLevel: "loose" }});
    const source = document.getElementById("diagram-source").textContent;
    const {{ svg }} = await mermaid.render("theGraph", source);
    document.getElementById("diagram").innerHTML = svg;
  </script>
  <script type="text/plain" id="diagram-source">{escaped_source}</script>
</body>
</html>
"""
