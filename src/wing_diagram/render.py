from __future__ import annotations

import html
import shutil
import subprocess
import tempfile
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
            dot.attr(label=title, labelloc="t", fontsize="32", fontname="Helvetica-Bold")

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
    tap = edge.meta.get("tap")
    # 0.0 dB post-fader is the unity/default send config -- not worth
    # labelling since it's what every unconfigured send looks like.
    if not (level_db == 0.0 and tap == "POST FADER"):
        if level_db is not None:
            parts.append(_format_level(level_db))
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
    rounded corners (straight segments, not Graphviz's curved splines).

    `elk.mergeEdges` is deliberately left off. It sounds like exactly what
    we want -- edges sharing a source or destination bundling into a shared
    trunk -- but what it actually does is bundle together *any* edges that
    happen to travel through the same inter-layer routing channel, even
    when they share neither endpoint, which in this densely-connected graph
    made unrelated channels look wired to busses they never send to (see
    the "overlapping connection lines" writeup).

    An earlier version of this renderer worked around that by routing
    same-source/same-destination edges through an explicit junction-dot
    node, so a real ELK node (not a heuristic) marked where edges actually
    shared an endpoint. That's gone for now -- see `D2Renderer`, which gets
    materially better edge separation than Mermaid+elk ever did, with
    neither `mergeEdges` nor junction dots, for anything that needs more
    than "just don't draw false merges." This renderer is kept simple
    (`mergeEdges` off, nothing else) until/unless Mermaid is worth that
    complexity again.

    Node kinds keep the same fill/stroke colors as `GraphvizRenderer` (via
    `classDef`/`class`), and nodes are declared in the same left-to-right
    `_RANK_GROUPS` order -- as a declaration order rather than a Mermaid
    `subgraph`, since ELK treats a `subgraph` as its own nested layout
    problem and silently stops respecting node order inside it.

    ELK's own crossing-minimization is left free to reorder nodes within a
    layer (no `elk.forceNodeModelOrder`), which gives the independent edges
    above more room to separate instead of being pinned into a corridor
    that forces them to run parallel. It groups nodes by shared destination
    instead of raw index, which reads a little less like a numeric channel
    list but keeps crossings down.

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
        ]
        if title:
            #: Mermaid's default title size is barely larger than node text --
            #: bump it via `themeCSS` (the one config knob Mermaid exposes for
            #: arbitrary CSS) since there's no dedicated "title font size" option.
            lines.append(
                '  themeCSS: ".flowchartTitleText { font-size: 32px; font-weight: bold; }"'
            )
        lines += [
            "  layout: elk",
            "  elk:",
            #: Left off -- see `MermaidRenderer`'s docstring for why
            #: `mergeEdges` is unsafe for this graph's density.
            "    mergeEdges: false",
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
        #: problem, which stops `_RANK_GROUPS` from influencing layer order
        #: across group boundaries. `_RANK_GROUPS` still controls the order
        #: nodes are *declared* in, which ELK's crossing-minimization takes
        #: as its starting point (see `MermaidRenderer`'s docstring).
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


class D2Renderer(Renderer):
    """Renders a `RoutingGraph` using D2 (https://d2lang.com) with its `elk`
    layout engine.

    D2 was added after `MermaidRenderer`'s `elk.mergeEdges` turned out to
    bundle together edges that merely passed through the same routing
    corridor rather than edges that actually shared an endpoint (see
    `MermaidRenderer`'s docstring) -- a problem `MermaidRenderer` works
    around with explicit junction-dot nodes. Measuring the rendered SVG
    geometry of a real, densely-connected snapshot (most channels feeding
    both a bus and the mains) found D2+elk's *default* routing left only one
    pair of unrelated edges running briefly parallel (out of 72 edges, 78px
    of incidental closeness, never literally coincident), against 188 such
    pairs (up to 464px) for Mermaid's `mergeEdges`, and a dozen-ish smaller
    incidents for Graphviz with or without `concentrate`. D2+elk needed none
    of Mermaid's junction-dot workaround to get there -- it just doesn't
    share routing lanes between unrelated edges by default.

    D2 ships as a single self-contained binary (no Node/browser dependency,
    unlike `MermaidRenderer`'s `.html` preview) and renders straight to
    `.svg`/`.png`/`.pdf`/... itself, the same shape as `GraphvizRenderer`
    shelling out to `dot`.

    The layout engine is selected from inside the generated `.d2` source
    (`vars.d2-config.layout-engine`) rather than a CLI flag, so the source
    file is self-contained the same way `MermaidRenderer`'s frontmatter is.

    A node's label is a Markdown block inside an explicitly-declared
    `shape: rectangle` (D2 keeps the fill/stroke box in that case), so it
    can mix styles the way `MermaidRenderer`'s HTML labels do: a bold title,
    plain config detail (preamp gain, trim) as its own paragraph, and
    dynamics badges (Gate/Comp) in italics as a separate paragraph. Markdown
    has no per-span colour or size, so unlike Mermaid the config detail
    isn't small grey type, and there is no divider rule (an `<hr>` in a D2
    Markdown block is untested). Edge labels stay plain strings, see
    `_d2_label`.
    """

    def __init__(self, d2_path: str = "d2", layout_engine: str = "elk") -> None:
        """`d2_path` is the `d2` executable to run (default: look up `d2` on
        `PATH`). `layout_engine` is any engine the installed `d2` ships --
        `"elk"` (default), `"dagre"`, or `"tala"` (bundled since d2 v0.9.0)."""
        self._d2_path = d2_path
        self._layout_engine = layout_engine

    def render(self, graph: RoutingGraph, out_path: Path, title: str | None = None) -> Path:
        out_path = Path(out_path)
        if shutil.which(self._d2_path) is None:
            raise UserError(
                f"D2Renderer needs the {self._d2_path!r} executable on PATH -- install it "
                "from https://d2lang.com/tour/install (`go install oss.terrastruct.com/d2@latest` "
                "also works if you have a Go toolchain)."
            )
        source = self._build_d2(graph, title)
        with tempfile.NamedTemporaryFile(
            "w", suffix=".d2", dir=str(out_path.parent) or ".", delete=False
        ) as f:
            f.write(source)
            d2_path = Path(f.name)
        try:
            result = subprocess.run(
                [self._d2_path, str(d2_path), str(out_path)],
                capture_output=True,
                text=True,
            )
        finally:
            d2_path.unlink(missing_ok=True)
        if result.returncode != 0:
            raise UserError(f"d2 failed to render the diagram:\n{result.stderr}")
        return out_path

    def _build_d2(self, graph: RoutingGraph, title: str | None = None) -> str:
        lines: list[str] = [
            "vars: {",
            "  d2-config: {",
            f"    layout-engine: {self._layout_engine}",
            "  }",
            "}",
            "direction: right",
            "",
        ]
        if title:
            lines += [
                "title: {",
                f"  label: {_d2_quoted(title)}",
                "  near: top-center",
                "  shape: text",
                "  style.font-size: 28",
                "  style.bold: true",
                "}",
                "",
            ]
        elif not graph.nodes:
            #: d2 silently writes nothing at all for a diagram with zero
            #: shapes (no error, just no output file) -- an untitled empty
            #: `RoutingGraph` would otherwise hit that with no node or title
            #: to act as a shape, so give it an invisible placeholder.
            lines += ['_empty_: "" { style.opacity: 0 }', ""]

        for node in graph.nodes:
            nid = _d2_id(node.id)
            fill = _NODE_COLORS.get(node.kind, "#ffffff")
            stroke = _NODE_STROKE_COLORS.get(node.kind, "#333333")
            lines.append(f"{nid}: {{")
            lines.extend(f"  {line}" for line in _d2_node_label_block(node))
            #: Required: D2 only keeps a box around a Markdown label if the
            #: shape is declared explicitly (even though rectangle is the
            #: default).
            lines.append("  shape: rectangle")
            lines.append(f'  style.fill: "{fill}"')
            lines.append(f'  style.stroke: "{stroke}"')
            lines.append("}")

        for edge in graph.edges:
            src = _d2_id(edge.source)
            dst = _d2_id(edge.dest)
            if edge.meta.get("kind") == "key":
                label = f"KEY ({edge.meta['proc']})" if edge.meta.get("proc") else "KEY"
                lines.append(f"{src} -> {dst}: {_d2_quoted(label)} {{")
                lines.append(f'  style.stroke: "{_KEY_EDGE_COLOR}"')
                lines.append(f'  style.font-color: "{_KEY_EDGE_COLOR}"')
                lines.append("  style.stroke-dash: 4")
                lines.append("}")
                continue
            parts = _edge_label_parts(edge)
            if parts:
                lines.append(f"{src} -> {dst}: {_d2_label(parts)}")
            else:
                lines.append(f"{src} -> {dst}")

        return "\n".join(lines) + "\n"


def _d2_id(node_id: NodeId) -> str:
    return "n_" + "_".join(str(part) for part in node_id)


def _d2_quoted(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _d2_label(lines_list: list[str]) -> str:
    """A D2 quoted-string label, `\\n`-joined when there's more than one
    line. Unlike `MermaidRenderer`'s HTML labels, this stays a plain
    rectangle -- D2's multi-line block-string syntax (`|...|`) renders as a
    markdown/text shape instead, dropping the fill/stroke box entirely.

    Each line is escaped on its own and *then* joined with a literal
    `\\n` -- escaping the whole joined string first would double-escape
    that separator's own backslash into a literal `\\n` in the output
    rather than a line break."""
    escaped = (line.replace("\\", "\\\\").replace('"', '\\"') for line in lines_list)
    return '"' + "\\n".join(escaped) + '"'


#: Characters that are Markdown syntax in a D2 `|md` block and so are
#: backslash-escaped in label text.
_MD_SPECIAL = "\\`*_[]<>#|~"


def _md_escape(text: str) -> str:
    return "".join(f"\\{c}" if c in _MD_SPECIAL else c for c in text)


def _d2_node_label_block(node: Node) -> list[str]:
    """The `label: |||md ... |||` block for a node, as unindented lines:
    a bold title, then any config detail lines (one paragraph), then any
    dynamics badges (`GATE`/`COMP`, one italic paragraph) -- the Markdown
    counterpart of `_node_html_label`.

    Uses `|||` delimiters (rather than `|`) so a label containing `|` can't
    end the block early, and separates lines with blank lines (paragraphs)
    rather than relying on Markdown hard-break syntax."""
    config_lines = [d for d in node.detail if not d.startswith(_DYNAMICS_DETAIL_PREFIXES)]
    dynamics_lines = [d for d in node.detail if d.startswith(_DYNAMICS_DETAIL_PREFIXES)]

    paragraphs = [f"**{_md_escape(_node_title(node))}**"]
    paragraphs += [_md_escape(d) for d in config_lines]
    paragraphs += [f"*{_md_escape(d)}*" for d in dynamics_lines]

    lines = ["label: |||md"]
    for i, paragraph in enumerate(paragraphs):
        if i:
            lines.append("")
        lines.append(f"  {paragraph}")
    lines.append("|||")
    return lines
