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

#: Legend entries: one swatch per distinct node colour, labelled the way a
#: viewer would read it rather than by internal `kind` -- `ch`/`aux` and
#: `main`/`mtx` each share a single colour (see `_NODE_COLORS`), so they
#: collapse into one legend row apiece. Same order as `_RANK_GROUPS`.
_LEGEND_ENTRIES: tuple[tuple[str, str], ...] = (
    ("io_in", "Input"),
    ("ch", "Channel / Aux"),
    ("bus", "Bus"),
    ("main", "Main / Matrix"),
    ("io_out", "Output"),
)

#: Key (sidechain) edges are a control tap into a Gate/Comp, not an audio
#: signal path -- rendered dashed, in a distinct color, and non-rank-
#: `constraint`-ing so a bus/main/matrix keying off a later-ranked element
#: doesn't warp the left-to-right signal-flow layout. See
#: `ai/dynamics-and-levels-plan.md` section 2.
_KEY_EDGE_COLOR = "#b35900"

#: A send at the Wing's own default -- post-fader, unity gain -- is the
#: common case and not worth calling out on every single edge; see
#: `_edge_label_parts`.
_DEFAULT_SEND_TAP = "POST FADER"
_DEFAULT_SEND_LEVEL_DB = 0.0

#: Mermaid `classDef` for a shared-label node: no fill, no border, so it
#: reads as a floating label rather than another diagram element. See
#: `_shared_label_groups`.
_SHARED_LABEL_CLASS = "sharedlabel"

#: Mermaid `classDef` for a rank-anchor dummy node: no fill, no border --
#: purely a layering hint for ELK, never meant to be seen. See
#: `MermaidRenderer._build_mermaid`'s "rank anchor" note.
_RANK_ANCHOR_CLASS = "rankanchor"


class Renderer(ABC):
    """Renders a `RoutingGraph` to a file. Implementation-agnostic boundary."""

    @abstractmethod
    def render(self, graph: RoutingGraph, out_path: Path, title: str | None = None) -> Path:
        """Render `graph` to `out_path` and return the path actually written.
        `title`, if given, is shown on the diagram itself."""
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

    def render(self, graph: RoutingGraph, out_path: Path, title: str | None = None) -> Path:
        out_path = Path(out_path)
        format = self._format or out_path.suffix.lstrip(".") or "svg"
        dot = self._build_dot(graph, format, title)
        rendered = dot.render(
            filename=out_path.stem, directory=str(out_path.parent) or ".", cleanup=True
        )
        return Path(rendered)

    def _build_dot(
        self, graph: RoutingGraph, format: str, title: str | None = None
    ) -> graphviz.Digraph:
        dot = graphviz.Digraph(
            name="wing_routing",
            format=format,
            graph_attr={"rankdir": "LR", "splines": "spline"},
            node_attr={"shape": "box", "style": "filled", "fontname": "Helvetica"},
        )
        if title:
            dot.attr(label=title, labelloc="t", fontsize="20", fontname="Helvetica-Bold")

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

        shared_label_groups = _shared_label_groups(graph.edges)
        shared_label_indices = {i for indices in shared_label_groups.values() for i in indices}

        for edge_index, edge in enumerate(graph.edges):
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
            if edge_index in shared_label_indices:
                continue
            dot.edge(
                _dot_node_id(edge.source),
                _dot_node_id(edge.dest),
                label=_edge_label(edge),
                fontsize="10",
            )

        for (source, parts), indices in shared_label_groups.items():
            label_id = f"label_{_dot_node_id(source)}_{indices[0]}"
            dot.node(
                label_id,
                label="\\n".join(parts),
                shape="plaintext",
                style="",
                fontsize="10",
            )
            dot.edge(_dot_node_id(source), label_id, arrowhead="none")
            for index in indices:
                dot.edge(label_id, _dot_node_id(graph.edges[index].dest), fontsize="10")

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
    if not _is_default_send(edge):
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


def _is_default_send(edge: Edge) -> bool:
    """A send at the Wing's own default -- post-fader, unity gain -- isn't
    worth a label of its own; see `_DEFAULT_SEND_TAP`."""
    return (
        edge.meta.get("tap") == _DEFAULT_SEND_TAP
        and edge.meta.get("level_db") == _DEFAULT_SEND_LEVEL_DB
    )


def _shared_label_groups(edges: list[Edge]) -> dict[tuple[NodeId, tuple[str, ...]], list[int]]:
    """Groups non-key edges by `(source, label parts)`, keeping only groups
    of two or more -- i.e. a source fanning out several connections that
    all carry the exact same (non-default) tap point and send level.

    Rather than repeating that label on every one of those edges, the
    caller routes them all through a single shared "label node" (see
    `_GraphvizRenderer._build_dot`/`MermaidRenderer._build_mermaid`), so
    the label is only ever shown once per distinct value per source.
    """
    groups: dict[tuple[NodeId, tuple[str, ...]], list[int]] = {}
    for index, edge in enumerate(edges):
        if edge.meta.get("kind") == "key":
            continue
        parts = tuple(_edge_label_parts(edge))
        if not parts:
            continue
        groups.setdefault((edge.source, parts), []).append(index)
    return {key: indices for key, indices in groups.items() if len(indices) > 1}


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

#: A named `io_in`'s `detail` always leads with its hardware designation
#: (e.g. "Local In 3") -- see `routing._make_node` -- and the only other
#: `io_in` detail line is `_preamp_gain_detail`'s fixed "preamp " prefix, so
#: a config line that doesn't start with it is that hardware designation.
_PREAMP_DETAIL_PREFIX = "preamp "


class MermaidRenderer(Renderer):
    """Renders a `RoutingGraph` as a Mermaid flowchart.

    Uses Mermaid's `elk` layout engine for orthogonal edge routing with
    rounded corners (straight segments, not Graphviz's curved splines).

    `elk.mergeEdges` is deliberately left off: it bundles any edges ELK
    routes through the same inter-rank gap into a shared visual trunk,
    regardless of whether they actually share an endpoint -- so a page of
    distinct one-to-one connections (e.g. each physical input patched to
    its own, different channel) was drawn as one undifferentiated trunk
    fanning out at both ends, reading as "these inputs connect to these
    channels" as a group rather than as the distinct pairs they are. Every
    edge here gets its own traceable line; `_shared_label_groups` below is
    the one deliberate, explicit exception -- it bundles edges only when
    they share both a source *and* an identical label, which is a real
    shared relationship worth drawing as one fan, not a routing-engine
    space-saving trick.

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

    `forceNodeModelOrder` only controls a node's position *within* whatever
    layer ELK's own layered algorithm assigns it (by longest path from a
    source) -- it does not make ELK respect `_RANK_GROUPS` as the layer
    assignment itself. A rank group that isn't the longest path to every one
    of its nodes (e.g. `bus`, reached in one hop from `ch` just like `main`/
    `mtx` are) can end up sharing a layer with a later rank group, and an
    edge routed into it then has to cut across that later group's node
    boxes to get there. A chain of invisible (`~~~`) edges through one dummy
    "rank anchor" node per rank-group boundary (see `_RANK_ANCHOR_CLASS`)
    fixes this without subgraphs: every node in rank N+1 gets an edge from
    rank N's anchor and an edge to rank N+1's anchor, forcing its layer
    strictly after every node in rank N regardless of what its real edges'
    own topology would otherwise give it.

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

    def render(self, graph: RoutingGraph, out_path: Path, title: str | None = None) -> Path:
        out_path = Path(out_path)
        suffix = out_path.suffix.lower()
        source = self._build_mermaid(graph, title)

        if suffix in ("", ".mmd", ".mermaid"):
            target = out_path if suffix else out_path.with_suffix(".mmd")
            target.write_text(source)
            return target
        if suffix == ".html":
            out_path.write_text(_wrap_html(source, title))
            return out_path
        raise UserError(
            f"MermaidRenderer can't write {suffix!r} directly -- write a '.mmd' "
            "or '.html' output instead, then convert the '.mmd' with the Mermaid "
            "CLI (`mmdc`), the VS Code/GitHub Mermaid preview, or "
            "https://mermaid.live."
        )

    def _build_mermaid(self, graph: RoutingGraph, title: str | None = None) -> str:
        lines: list[str] = ["---"]
        if title:
            #: Mermaid's own frontmatter `title` -- renders as a heading above
            #: the diagram, so it needs no node of its own.
            lines.append(f"title: {_yaml_quoted(title)}")
        lines += [
            "config:",
            "  layout: elk",
            "  elk:",
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
            #: ELK's default spacing packs parallel edges passing through the
            #: same inter-rank gap close enough to run visually flush
            #: against each other -- not a crossing, just distinct edges
            #: (see `mergeEdges` above) with no room between them, which
            #: reads the same as a crossing/overlap from a glance. Wider
            #: edge-edge and node-node spacing gives each parallel segment
            #: and each bend point visibly distinct room, so a dense
            #: fan-out/fan-in (e.g. several channels each sending to the
            #: same several mains/matrices) stays busy but traceable.
            "    spacing.edgeEdge: 25",
            "    layered.spacing.edgeEdgeBetweenLayers: 25",
            "    layered.spacing.edgeNodeBetweenLayers: 25",
            "    layered.spacing.nodeNodeBetweenLayers: 80",
            "    spacing.nodeNode: 40",
            "---",
            "flowchart LR",
        ]

        for kind, fill in _NODE_COLORS.items():
            stroke = _NODE_STROKE_COLORS[kind]
            lines.append(f"  classDef {kind} fill:{fill},stroke:{stroke},color:#1a1a1a;")

        nodes_by_kind: dict[str, list[Node]] = {}
        for node in graph.nodes:
            nodes_by_kind.setdefault(node.kind, []).append(node)

        _reorder_io_in_by_target(nodes_by_kind, graph.edges)

        #: Nodes are declared flat (not wrapped in a Mermaid `subgraph` per
        #: rank group) -- ELK treats a `subgraph` as its own nested layout
        #: problem, which was overriding `forceNodeModelOrder` and reordering
        #: nodes within it regardless. `_RANK_GROUPS` still controls the
        #: order nodes are *declared* in, which `forceNodeModelOrder` then
        #: preserves in the actual layout.
        class_members: dict[str, list[str]] = {}
        rank_ids: list[list[str]] = []
        for kinds in _RANK_GROUPS:
            ids: list[str] = []
            for node in (n for kind in kinds for n in nodes_by_kind.get(kind, [])):
                mid = _mermaid_id(node.id)
                lines.append(f'  {mid}["{_node_html_label(node)}"]')
                class_members.setdefault(node.kind, []).append(mid)
                ids.append(mid)
            if ids:
                rank_ids.append(ids)

        #: ELK's layered algorithm assigns each node's *layer* itself (by
        #: longest path from a source), ignoring `_RANK_GROUPS`/declaration
        #: order entirely -- that only controls a node's position *within*
        #: whatever layer ELK gave it (see `forceNodeModelOrder` above). A
        #: rank group that isn't the longest path to every one of its nodes
        #: (e.g. `bus`, reached in one hop from `ch` just like `main`/`mtx`
        #: are) can end up sharing a layer with a later rank group, and an
        #: edge into it then has to cut across that later group's node
        #: boxes to get there. A chain of invisible (`~~~`) edges through
        #: one dummy "anchor" node per rank boundary fixes this without
        #: subgraphs (which broke `forceNodeModelOrder`'s within-layer
        #: ordering, see above): every node in rank N+1 gets an edge from
        #: rank N's anchor, and an edge to rank N+1's anchor, so its layer
        #: is forced strictly after every node in rank N regardless of its
        #: real edges' own topology.
        anchor_ids = [f"rank_anchor_{i}" for i in range(len(rank_ids) - 1)]
        for anchor_id in anchor_ids:
            lines.append(f"  {anchor_id}[ ]")
            class_members.setdefault(_RANK_ANCHOR_CLASS, []).append(anchor_id)
        for rank_index, ids in enumerate(rank_ids):
            if rank_index > 0:
                for mid in ids:
                    lines.append(f"  {anchor_ids[rank_index - 1]} ~~~ {mid}")
            if rank_index < len(anchor_ids):
                for mid in ids:
                    lines.append(f"  {mid} ~~~ {anchor_ids[rank_index]}")
        for prev_anchor, next_anchor in zip(anchor_ids, anchor_ids[1:]):
            lines.append(f"  {prev_anchor} ~~~ {next_anchor}")

        #: The legend is the one deliberate exception to "nodes are declared
        #: flat" above: it has no edges into the signal-flow graph, so
        #: `forceNodeModelOrder`/ELK have nothing to preserve order *for*,
        #: and wrapping it in its own `subgraph` is what keeps its swatches
        #: visually grouped as a single box rather than scattered wherever
        #: ELK places disconnected nodes.
        lines.append("  subgraph legend[Legend]")
        lines.append("    direction TB")
        for kind, text in _LEGEND_ENTRIES:
            lid = f"legend_{kind}"
            lines.append(f'    {lid}["{_esc(text)}"]')
            class_members.setdefault(kind, []).append(lid)
        lines.append("  end")

        shared_label_groups = _shared_label_groups(graph.edges)
        shared_label_indices = {i for indices in shared_label_groups.values() for i in indices}

        key_edge_indices: list[int] = []
        for edge_index, edge in enumerate(graph.edges):
            src = _mermaid_id(edge.source)
            dst = _mermaid_id(edge.dest)
            if edge.meta.get("kind") == "key":
                label = f"KEY ({edge.meta['proc']})" if edge.meta.get("proc") else "KEY"
                lines.append(f'  {src} -.->|"{_small_html(label)}"| {dst}')
                key_edge_indices.append(edge_index)
                continue
            if edge_index in shared_label_indices:
                continue
            parts = _edge_label_parts(edge)
            if parts:
                label_html = _small_html("<br/>".join(_esc(p) for p in parts), escape=False)
                lines.append(f'  {src} -->|"{label_html}"| {dst}')
            else:
                lines.append(f"  {src} --> {dst}")

        #: Several edges sharing a source and an identical (non-default)
        #: tap/level label are routed through one shared label node instead
        #: of repeating the label on each -- see `_shared_label_groups`.
        for (source, parts), indices in shared_label_groups.items():
            lid = f"n_label_{_mermaid_id(source)}_{indices[0]}"
            label_html = _small_html("<br/>".join(_esc(p) for p in parts), escape=False)
            lines.append(f'  {lid}["{label_html}"]')
            class_members.setdefault(_SHARED_LABEL_CLASS, []).append(lid)
            lines.append(f"  {_mermaid_id(source)} --> {lid}")
            for index in indices:
                lines.append(f"  {lid} --> {_mermaid_id(graph.edges[index].dest)}")

        lines.append(f"  classDef {_SHARED_LABEL_CLASS} fill:none,stroke:none;")
        lines.append(f"  classDef {_RANK_ANCHOR_CLASS} fill:none,stroke:none;")

        for kind, members in class_members.items():
            lines.append(f"  class {','.join(members)} {kind};")

        for idx in key_edge_indices:
            lines.append(
                f"  linkStyle {idx} stroke:{_KEY_EDGE_COLOR},stroke-width:1.5px,"
                "stroke-dasharray:6 4;"
            )

        return "\n".join(lines) + "\n"


def _reorder_io_in_by_target(nodes_by_kind: dict[str, list[Node]], edges: list[Edge]) -> None:
    """Reorders `nodes_by_kind["io_in"]` in place to track the declared
    order of the ch/aux node each physical input is patched to, instead of
    raw hardware id order.

    `MermaidRenderer` forces node order (`forceNodeModelOrder`) and so
    disables ELK's own crossing minimization -- see its docstring. ch/aux/
    bus/main/mtx/io_out keep their natural index order, since that's what a
    user expects of a channel list; but a physical input's hardware id has
    no relation to which channel it's patched to, so hardware-id order can
    put e.g. an AES50 input patched to a channel near the bottom of the
    list first, producing one edge that cuts across every other
    input-to-channel edge. Ordering inputs by their target channel's
    position instead keeps same-direction input/channel edges roughly
    parallel, with only genuine reorderings left to cross.

    An input with no direct ch/aux edge (e.g. a hardware passthrough
    straight to an output) keeps its relative hardware-id position,
    trailing the ones that do have a channel target.
    """
    io_in = nodes_by_kind.get("io_in")
    if not io_in:
        return

    target_position = {
        node.id: position
        for position, node in enumerate(n for kind in ("ch", "aux") for n in nodes_by_kind.get(kind, []))
    }
    io_in_ids = {node.id for node in io_in}
    first_target: dict[NodeId, NodeId] = {}
    for edge in edges:
        if edge.source in io_in_ids and edge.dest in target_position:
            first_target.setdefault(edge.source, edge.dest)

    original_position = {node.id: position for position, node in enumerate(io_in)}
    unanchored = len(target_position)

    def sort_key(node: Node) -> tuple[int, int]:
        target = first_target.get(node.id)
        anchor = target_position[target] if target is not None else unanchored
        return (anchor, original_position[node.id])

    io_in.sort(key=sort_key)


def _node_html_label(node: Node) -> str:
    """Builds a node's HTML label: a bold title line, then plain config
    detail (if any) in small grey type, then dynamics badges (if any)
    below a divider rule in smaller italic type. See `MermaidRenderer`.

    For a named `io_in`, the title and first detail line are swapped from
    `_node_title`'s default: the hardware designation (e.g. "Local In 3")
    is what you'd patch to, so it's shown as the title, with the person's
    own name (e.g. "Wendy") moved down to the first detail line."""
    title = _node_title(node)
    config_lines = [d for d in node.detail if not d.startswith(_DYNAMICS_DETAIL_PREFIXES)]
    dynamics_lines = [d for d in node.detail if d.startswith(_DYNAMICS_DETAIL_PREFIXES)]

    if (
        node.kind == "io_in"
        and config_lines
        and not config_lines[0].startswith(_PREAMP_DETAIL_PREFIX)
    ):
        title, name = config_lines[0], title
        config_lines = [name, *config_lines[1:]]

    parts = [f"<div><b>{_esc(title)}</b></div>"]

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


def _yaml_quoted(text: str) -> str:
    """Double-quoted YAML scalar for Mermaid's frontmatter `title`."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _wrap_html(mermaid_source: str, title: str | None = None) -> str:
    """A self-contained preview page: loads Mermaid and its `elk` layout
    plugin from a CDN and renders `mermaid_source` client-side. No local
    Mermaid/Node install needed -- just a browser with network access."""
    escaped_source = html.escape(mermaid_source)
    page_title = html.escape(title) if title else "WING routing diagram"
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{page_title}</title>
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
