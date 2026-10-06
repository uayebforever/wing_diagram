# WingDiagram — Initial Plan

## Goal

Build a tool that reads a Behringer/Midas **Wing** mixer `.snap` snapshot file
and produces a **routing diagram**: a picture of how signal flows from
physical inputs, through channels, buses/mains/matrices, to physical outputs.

This doc captures the shape of the plan as agreed, so separate implementation
passes can work from it without re-deriving context.

## Source data, as understood from `wing_snaps/Announcements.snap`

- The `.snap` file is JSON. The data we care about lives under the top-level
  `ae_data` key.
- `ae_data` top-level sections (each keyed by index, as strings "1", "2", ...):
  - `cfg` — global config (monitor, solo, talkback, etc.) — not routing.
  - `io` — physical I/O:
    - `io.in.<GRP>.<n>` — physical input `n` in group `GRP` (`LCL`, `AUX`,
      `A`/`B`/`C` = AES50, `SC`, `USB`, `CRD`, `MOD`, `PLAY`, `AES`, ...).
      Has a `name` (often the real human label, e.g. `"Wren"`).
    - `io.out.<GRP>.<n>` — physical output `n` in group `GRP`. Has `grp` +
      `in`, pointing *back* to the internal source it carries, e.g.
      `{"grp": "MAIN", "in": 3}` means that output jack carries Main 3.
  - `ch` (1–20) — input channels. Each has:
    - `in.conn` — `{"grp": ..., "in": N, "altgrp": ..., "altin": N}`: where
      the channel's signal comes from (mirrors `io.in` group codes, but also
      can be `BUS`/`MAIN`/`MTX` for internal re-patching).
    - `name` — channel's own name (frequently blank; fall back to the
      source's `io.in.<grp>.<n>.name` when blank).
    - `main.{1-4}` — `{"on": bool, "lvl": float, "pre": bool}` per Main bus.
    - `send.{1-16, MX1-8}` — `{"on": bool, "lvl": float, "pon": bool,
      "mode": "PRE"/"POST", "plink": ..., "pan": ...}` per Bus (1–16) and
      Matrix (MX1–8).
  - `aux` (1–8) — auxiliary input channels. Same shape as `ch` for routing
    purposes (`in.conn`, `main`, `send`) — these are *input* strips (e.g. for
    USB/stereo return), not "aux send" busses — don't confuse with the
    classic "aux bus" naming from other consoles.
  - `bus` (1–16) — the actual sub/send busses. Each has:
    - `name` (e.g. `"Speakers"`).
    - `main.{1-4}` and `send.{1-16, MX1-8}` — a bus can itself feed mains and
      matrices, same shape as above.
  - `main` (1–4) — main mixes. Has `name` (e.g. `"Sanctuary Mix"`,
    `"Stream Mix"`). Mains are *terminal* on the audio side (they don't have
    a `send`/`main` block feeding further busses) — they reach the outside
    world only via `io.out` entries whose `grp` is `"MAIN"`.
  - `mtx` (1–8) — matrix mixes. Expected to have `in`/send shape similar to
    bus; not yet fully inspected — verify during implementation.
  - `dca` (1–16), `mgrp` (1–8) — DCA and mute groups. These are **control**
    groupings (fader/mute association), not audio signal paths. **Out of
    scope** for the routing diagram.
  - `fx` (1–16) — effects. In the sample file, each `fx.<n>` only has `mdl`
    and `fxmix` — no visible `send`/`in` block. How effects are patched
    in/out (likely via `plink` fields elsewhere, or a dedicated return path)
    is **not yet understood** and is explicitly **out of scope for v1**.
    Revisit as a separate investigation before adding FX to the graph.
  - `cards`, `play`, `rec` — hardware card config, USB player, recording.
    Not routing.

## `propmap.jsonl`

- ~10MB, one JSON object per line, one line per parameter in the whole Wing
  parameter space (not just this snapshot).
- Each line has a `fullname` (slash-delimited path, e.g.
  `/ch/1/in/conn/grp`), `name` (short key matching the last path segment),
  `longname` (human label), `type` (`node`, `integer`, `linear float`,
  `log float`, `string`, `string enum`, ...), and for `string enum` types an
  `items` list of `{"item": <raw value>, "longitem": <human label>}`
  (longitem sometimes omitted when same as item).
- Purpose: given a path under `ae_data` (same shape as `fullname`, minus the
  leading context), look up how to *display* the raw value — e.g. resolve
  `"grp": "LCL"` to `"LOCAL IN"`, or get the proper on-console label for a
  parameter instead of its short key.
- Practical note: load once into an in-memory dict keyed by `fullname`;
  10MB / few hundred-thousand small records is fine to hold in memory for
  the lifetime of a CLI run. No need for lazy/streaming access in v1.

## Decisions made so far

1. **Diagram tool: Graphviz first**, via the `graphviz` Python package
   (emits DOT, renders SVG/PNG/PDF). Keep the renderer behind a thin
   interface so other backends (e.g. Mermaid) can be added later without
   touching the routing/graph-building code.
2. **Scope of v1 routing graph: active routes only.** Only draw an edge when
   the underlying `on` flag (or equivalent "this connection exists") is
   true. Do not render inactive/off sends, even greyed out — keep it
   legible. (Explicitly rejected for v1: "show everything, grey out
   inactive".)
3. **FX out of scope for v1.** `dca`/`mgrp` out of scope entirely (control,
   not audio).
4. **Renderer boundary must be thin/swappable** — see module shape below.

## Proposed module shape

Package: `wing_diagram` (already scaffolded under `src/wing_diagram`, with
an existing `cli/` subpackage using some command pattern — see
`cli/commands/command.py`, `root_command.py`, etc. New CLI commands should
follow that existing pattern rather than introducing a new one.)

### `wing_diagram.snapfile`

- `load_snapshot(path: str | Path) -> Snapshot`
- `Snapshot` — holds the parsed JSON: header fields (`type`, `creator_fw`,
  `creator_model`, `creator_version`, `created`, etc.) plus `.ae_data` (the
  raw nested dict/whatever structure we land on — pydantic model vs plain
  dict is an implementation decision for whoever builds this).
- Responsibility: *only* reading/parsing the file into a usable Python
  structure. No interpretation of what the data means.

### `wing_diagram.propmap`

- `PropMap.load(path: str | Path) -> PropMap`
- `PropMap.describe(fullname: str) -> PropMapEntry | None`
- `PropMapEntry` — wraps one parsed jsonl line (name, longname, type, enum
  items if any).
- Convenience: something like `PropMap.resolve_enum(fullname, raw_value) ->
  str` that looks up the human `longitem` for an enum raw value, falling
  back to the raw value if not found/not an enum.
- Responsibility: *only* path → metadata lookup. No knowledge of the
  snapshot's actual values.

### `wing_diagram.routing`

This is the domain layer that turns raw snapshot data into "what connects
to what". Suggested shape (names indicative, not final):

- `NodeId` — some hashable identifier for a mixer element, e.g.
  `("ch", 1)`, `("bus", 3)`, `("main", 2)`, `("io_in", "LCL", 1)`,
  `("io_out", "A", 5)`.
- `Node` — `{id: NodeId, kind: str, label: str}` where `label` is the
  resolved display name (own `name` if set, else fallback — e.g. a channel
  with blank `name` falls back to its source's input name).
- `Edge` — `{source: NodeId, dest: NodeId, meta: dict}` — one active
  connection. `meta` can carry things like level/pan for optional edge
  labels later, but v1 only needs the connection itself.
- `RoutingGraph` — `{nodes: list[Node], edges: list[Edge]}`, plain data,
  **no Graphviz-specific types** — this is the renderer-agnostic boundary.
- `build_routing_graph(snapshot: Snapshot, propmap: PropMap) -> RoutingGraph`
  — walks `ch`, `aux`, `bus`, `main`, `mtx`, `io.in`, `io.out`; for each
  channel/aux/bus/mtx:
  - emits an edge from its `in.conn` source (if that source is itself a
    mixer element already in-graph — e.g. BUS/MAIN/MTX re-patch — or from
    the corresponding `io_in` node) into the element itself;
  - emits an edge from the element to each `main.{n}`/`send.{n or MXn}`
    target where `on` is true;
  - emits an edge from any internal node to an `io_out` node wherever an
    `io.out` entry's `grp`/`in` points at that node.
  - Explicitly skips `fx`, `dca`, `mgrp` (see Decisions above).
- Open question to resolve during implementation: confirm `mtx` shape
  matches `bus` (has `in`/`send`/`main` analogous keys) — not yet verified
  against the actual sample data.

### `wing_diagram.render`

- `Renderer` — protocol/ABC: `render(graph: RoutingGraph, out_path: Path) ->
  Path` (or returns bytes — implementation's call).
- `GraphvizRenderer(Renderer)` — first implementation. Suggested layout
  approach: rank/cluster nodes left-to-right by kind
  (`io_in` → `ch`/`aux` → `bus` → `main`/`mtx` → `io_out`), using Graphviz
  subgraphs/`rank=same` groups, so the picture reads as a left-to-right
  signal flow rather than a tangled generic graph.
- Keep this module's public surface limited to the `Renderer`
  interface + concrete implementations, so a `MermaidRenderer` can be added
  later as a sibling class without changing callers.

### `wing_diagram.cli`

- New command (matching the existing `cli/commands` pattern) e.g.:
  `wing_diagram routing <snapfile> [-o out.svg] [--renderer graphviz]`
- Wires together: `load_snapshot` → `PropMap.load` → `build_routing_graph`
  → `Renderer.render`.

## Suggested build order (separable chunks for different implementation passes)

1. `wing_diagram.snapfile` — load & parse `.snap` into `Snapshot`. Small,
   no external dependencies beyond `json`/pydantic. Testable against
   `wing_snaps/Announcements.snap`.
2. `wing_diagram.propmap` — load & index `propmap.jsonl`, with enum
   resolution helper. Testable independently of the snapshot.
3. `wing_diagram.routing` — the domain/graph-building logic. Depends on 1
   and 2. This is the piece most likely to need iteration once real output
   is eyeballed against the actual console routing (verify `mtx` shape,
   verify fallback-naming logic, verify `io.out` → internal-node mapping
   covers all groups seen in a real snapshot).
4. `wing_diagram.render` (Graphviz) — depends on 3's `RoutingGraph` type
   only, not on how it was built. Can be developed/tested against hand-built
   `RoutingGraph` fixtures before step 3 is finished, if useful.
5. `wing_diagram.cli` — wires 1–4 together behind the existing CLI command
   pattern.

## Explicitly out of scope for v1

- FX routing (`fx.*`) — structure not understood yet, needs separate
  investigation.
- DCA (`dca.*`) and mute groups (`mgrp.*`) — control groupings, not audio
  signal paths.
- Inactive/off routes — not shown at all (not even greyed out).
- Any non-routing parameters (EQ, dynamics, gate, filters, delay, etc.) —
  irrelevant to this diagram by design.
- Alternate renderers (Mermaid etc.) — the `Renderer` boundary should make
  this easy later, but only Graphviz ships in v1.
