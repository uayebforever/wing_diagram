from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, cast

from .propmap import PropMap
from .snapfile import Snapshot

#: Identifies one mixer element: `("ch", 5)`, `("bus", 2)`, or
#: `("io_in", "LCL", 1)` / `("io_out", "A", 12)` for physical I/O.
NodeId = tuple[str, int] | tuple[str, str, int]

#: Sections that carry a single-source `in.conn` block, same shape as `ch`
#: for routing purposes. See `ai/schema-notes.md` ("Source types have
#: different connection shapes").
_SINGLE_SOURCE_SECTIONS = ("ch", "aux")

#: Sections that carry `main.{1-4}` / `send.{1-16,MX1-8}` blocks of their
#: own (i.e. can feed mains/buses/matrices further downstream). `mtx` is
#: excluded: it has neither block, it's a dead end on the audio side aside
#: from `io.out`.
_SENDING_SECTIONS = ("ch", "aux", "bus", "main")

#: `in.conn.grp` / `io.out.<grp>.<n>.grp` values that mean "re-patched from
#: another internal mixer element" rather than a physical input.
_INTERNAL_SOURCE_KINDS = {"BUS": "bus", "MAIN": "main", "MTX": "mtx"}

#: `grp` values that are real connections but to something out of scope for
#: v1 (see `ai/initial-plan.md` "Explicitly out of scope") -- skip silently
#: rather than emitting an edge to a node we don't model.
#: - `SEND` is an FX send tap; FX routing is unexplored/out of scope.
#: - `MON` is a monitor/PFL bus (`cfg.mon.*`), a control/monitoring feature
#:   the initial plan already classifies as "not routing".
_OUT_OF_SCOPE_SOURCE_GROUPS = frozenset({"SEND", "MON"})

#: A `propmap.jsonl` path whose `grp`-type enum happens to be the superset
#: of every group code we need a display label for (physical I/O groups
#: plus BUS/MAIN/MTX/SEND/MON) -- see `ai/schema-notes.md` "`io.out` has
#: more destination kinds than the initial plan covered". Used purely to
#: resolve a group *code* (e.g. `"LCL"`) to its on-console label (e.g.
#: `"LOCAL IN"`), independent of any particular node's data.
_GROUP_LABEL_PROPMAP_PATH = "io/out/LCL/1/grp"

_KIND_LABELS = {"ch": "Ch", "aux": "Aux", "bus": "Bus", "main": "Main", "mtx": "Mtx"}

#: Left-to-right rank order for node kinds, matching the signal-flow layout
#: `wing_diagram.render` is meant to produce.
_KIND_ORDER = {"io_in": 0, "ch": 1, "aux": 1, "bus": 2, "main": 3, "mtx": 3, "io_out": 4}


@dataclass(frozen=True)
class Node:
    id: NodeId
    kind: str
    label: str


@dataclass(frozen=True)
class Edge:
    source: NodeId
    dest: NodeId
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RoutingGraph:
    """Renderer-agnostic routing graph: plain data, no Graphviz types."""

    nodes: list[Node]
    edges: list[Edge]


def build_routing_graph(snapshot: Snapshot, propmap: PropMap) -> RoutingGraph:
    """Walk `snapshot.ae_data` and build the active-routes-only graph.

    Only elements that participate in at least one active (`on: true`, or
    an actual `in.conn`/`io.out` patch) connection become nodes -- a fully
    unpatched physical input or an unused channel is omitted rather than
    shown disconnected, per the "active routes only" decision in
    `ai/initial-plan.md`. `fx`, `dca`, and `mgrp` are not visited at all.
    """
    ae = snapshot.ae_data
    edges: list[Edge] = []
    touched: set[NodeId] = set()

    def touch(node_id: NodeId) -> NodeId:
        touched.add(node_id)
        return node_id

    def add_edge(source: NodeId, dest: NodeId, meta: dict[str, Any] | None = None) -> None:
        edges.append(Edge(touch(source), touch(dest), meta or {}))

    for section in _SINGLE_SOURCE_SECTIONS:
        for index, data in _section_items(ae, section):
            conn = _active_conn(data)
            source_id = _resolve_source(conn) if conn is not None else None
            if source_id is not None:
                add_edge(source_id, (section, index))

    for section in _SENDING_SECTIONS:
        for index, data in _section_items(ae, section):
            _add_sends(data, (section, index), add_edge)

    for out_grp, index, data in _io_out_entries(ae):
        resolved = _resolve_output_source(data)
        if resolved is not None:
            source_id, channel = resolved
            meta = {"channel": channel} if channel is not None else None
            add_edge(source_id, ("io_out", out_grp, index), meta)

    nodes = [_make_node(node_id, ae, propmap) for node_id in touched]
    nodes.sort(key=lambda n: (_KIND_ORDER.get(n.kind, 99), n.id))
    edges.sort(key=lambda e: (e.source, e.dest))
    return RoutingGraph(nodes=nodes, edges=edges)


def _section_items(ae: dict[str, Any], section: str) -> list[tuple[int, dict[str, Any]]]:
    items = ae.get(section) or {}
    return [(int(index), data) for index, data in items.items()]


def _io_out_entries(ae: dict[str, Any]) -> list[tuple[str, int, dict[str, Any]]]:
    out_groups = (ae.get("io") or {}).get("out") or {}
    return [
        (grp, int(index), data)
        for grp, group in out_groups.items()
        for index, data in group.items()
    ]


def _active_conn(data: dict[str, Any]) -> dict[str, Any] | None:
    """Pick whichever of `in.conn`'s primary/alt source is actually in use.

    `in.set.altsrc` (not `srcauto`, which only governs automatic failover
    on signal loss -- irrelevant to a static snapshot) selects between
    `grp`/`in` and `altgrp`/`altin`. See `ai/schema-notes.md`.
    """
    in_block = data.get("in")
    if not in_block:
        return None
    conn = in_block.get("conn")
    if not conn:
        return None
    use_alt = bool((in_block.get("set") or {}).get("altsrc"))
    if use_alt:
        return {"grp": conn.get("altgrp"), "in": conn.get("altin")}
    return {"grp": conn.get("grp"), "in": conn.get("in")}


def _resolve_source(conn: dict[str, Any]) -> NodeId | None:
    """Resolve an `in.conn`-shaped `{"grp": ..., "in": ...}` to a `NodeId`.

    `grp` is either a physical I/O group or an internal re-patch target
    (`BUS`/`MAIN`/`MTX`), in which case `in` addresses that element
    directly (bus/main/mtx are stereo throughout the signal path up to
    this point, so re-patching into a channel strip picks up the whole
    stereo element, same as `cfg.mon.*.src`'s `"BUS.<n>"`-style source
    enum does) -- *not* the flattened L/R tap numbering `io.out` uses
    (see `_resolve_output_source`). See `ai/schema-notes.md`.
    """
    grp = conn.get("grp")
    index = conn.get("in")
    if not grp or grp == "OFF" or index is None:
        return None
    if grp in _INTERNAL_SOURCE_KINDS:
        return (_INTERNAL_SOURCE_KINDS[grp], int(index))
    if grp in _OUT_OF_SCOPE_SOURCE_GROUPS:
        return None
    return ("io_in", grp, int(index))


def _resolve_output_source(conn: dict[str, Any]) -> tuple[NodeId, str | None] | None:
    """Resolve an `io.out.<grp>.<n>`-shaped `{"grp": ..., "in": ...}`.

    Physical output jacks are mono, so when `grp` is an internal re-patch
    target (`BUS`/`MAIN`/`MTX`), `in` is *not* that element's own index --
    it's a flat 1-based tap number across a fixed 2 taps (L, R) per
    element, in element order, regardless of whether the element itself
    is actually configured mono or stereo (`<section>.<n>.busmono`): a
    mono-downmixed main still reserves and duplicates its signal across
    both taps. E.g. tap 3 is always "element 2, L" whether that element
    is a stereo or a (down-mixed) mono main/bus/mtx. Confirmed against a
    real snapshot where a mono main's *second* tap (R) was the one
    actually patched out -- see `ai/schema-notes.md`.

    Returns `(node_id, channel)` where `channel` is `"L"`/`"R"` for an
    internal re-patch tap, or `None` for a physical passthrough (no
    channel-split concept there).
    """
    grp = conn.get("grp")
    tap = conn.get("in")
    if not grp or grp == "OFF" or tap is None:
        return None
    if grp in _INTERNAL_SOURCE_KINDS:
        tap = int(tap)
        element_index = (tap - 1) // 2 + 1
        channel = "L" if (tap - 1) % 2 == 0 else "R"
        return (_INTERNAL_SOURCE_KINDS[grp], element_index), channel
    if grp in _OUT_OF_SCOPE_SOURCE_GROUPS:
        return None
    return ("io_in", grp, int(tap)), None


def _add_sends(
    data: dict[str, Any],
    source_id: NodeId,
    add_edge: Callable[[NodeId, NodeId, dict[str, Any] | None], None],
) -> None:
    """Emit edges for every active `main.{1-4}` / `send.{1-16,MX1-8}` target.

    Shape varies by section (see `ai/schema-notes.md` "Source types have
    different connection shapes") but the key vocabulary -- numeric keys
    under `main` mean a main index, numeric keys under `send` mean a bus
    index, `MX<n>` keys under `send` mean a matrix index -- is uniform
    across every section that has these blocks at all.
    """
    for key, target in (data.get("main") or {}).items():
        if target.get("on"):
            add_edge(source_id, ("main", int(key)), None)
    for key, target in (data.get("send") or {}).items():
        if not target.get("on"):
            continue
        if key.startswith("MX"):
            add_edge(source_id, ("mtx", int(key[2:])), None)
        else:
            add_edge(source_id, ("bus", int(key)), None)


def _make_node(node_id: NodeId, ae: dict[str, Any], propmap: PropMap) -> Node:
    kind = node_id[0]
    if kind == "io_in" or kind == "io_out":
        _, grp, index = cast("tuple[str, str, int]", node_id)
        section = "in" if kind == "io_in" else "out"
        data = (((ae.get("io") or {}).get(section) or {}).get(grp) or {}).get(str(index)) or {}
        label = data.get("name") or f"{_group_label(propmap, grp)} {index}"
        return Node(id=node_id, kind=kind, label=label)

    _, index = cast("tuple[str, int]", node_id)
    data = (ae.get(kind) or {}).get(str(index)) or {}
    own_name = data.get("name")
    if own_name:
        return Node(id=node_id, kind=kind, label=own_name)

    if kind in _SINGLE_SOURCE_SECTIONS:
        conn = _active_conn(data)
        source_id = _resolve_source(conn) if conn is not None else None
        if source_id is not None:
            return Node(id=node_id, kind=kind, label=_make_node(source_id, ae, propmap).label)

    return Node(id=node_id, kind=kind, label=f"{_KIND_LABELS[kind]} {index}")


def _group_label(propmap: PropMap, grp: str) -> str:
    resolved = propmap.resolve(_GROUP_LABEL_PROPMAP_PATH, grp)
    return resolved if isinstance(resolved, str) else grp
