# Plan: gain, dynamics, key sources, and tap points

Follow-up to `ai/initial-plan.md` and `ai/schema-notes.md`, covering the next
round of detail requested for the diagram: gain staging, the Gate/Comp
dedicated slots on channel-strips, sidechain ("key source") routing, and the
multiple tap points a signal can be collected from. Written from direct
inspection of `wing_snaps/Announcements.snap` + `propmap.jsonl`, cross-checked
against the WING User Manual (section 6, "Channel Processing").
Deliberately still excludes `fx`/`dca`/`mgrp` and the separate FX engine, per
the existing out-of-scope list — nothing here changes that.

## 1. New schema findings

### 1.1 Gain stages

There are two independent gain stages upstream of a channel, plus the levels
already threaded through `send`/`main`:

- **Preamp (analog) gain** — `io/in/<grp>/<n>/g`, `-2.5..45 dB`. Lives on the
  physical input jack (a `Source`), *not* on the channel strip — in Wing, a
  Source's preamp gain follows it around even if a channel is re-patched to a
  different Source. Only present under `io/in/...`; `io/out` has no
  equivalent (no analog stage on an output jack).
- **Channel digital trim** — `<section>/<n>/in/set/trim`, `±18 dB`. Present
  on `ch`/`aux`/`bus`/`main`/`mtx` uniformly (confirmed in schema-notes.md's
  "do have an `in` key" note — that `in.set` block is `{inv, trim, bal}`
  everywhere, we'd just never looked at `trim` specifically before).
- **Send/main levels** — `send.<n|MXn>.lvl` and `main.<n>.lvl`, already read
  by `routing._add_sends` to gate the `on` flag but currently discarded.
  `-144` is the console's "off"/-∞ sentinel.
- **Dynamics make-up gain** — `gate.gain` (small, mostly cosmetic) and
  `dyn.gain` (`-6..12 dB`, the compressor's actual make-up gain). Belongs with
  the dynamics detail (§1.2), not the routing edges.

### 1.2 Gate/Comp dedicated slots

Confirmed directly in `ae_data` (`ch/1` keys) and the manual (§6.1–6.3):

- **`ch` only** gets a separate `gate` block (plus `gatesc` for its
  sidechain). `aux`/`bus`/`main`/`mtx` have **no `gate` key at all** — just
  `dyn`/`dynsc`. This matches the manual: Input Channels get
  GATE+EQ+COMP+INS1 (pre-fader, order user-configurable) +INS2 (post-fader);
  every other strip type gets one Dynamics slot (comp-family processor only)
  + pre/post insert points.
- Both `gate` and `dyn` carry `on` (bool), `mdl` (processor model — "GATE",
  "COMP", but also emulations like "76LA", "WAVE", a ducker, etc. — the Gate
  and Comp slots share the same model list), `thr`, `ratio` or `range`,
  `att`/`hld`/`rel`, and `gain`. Good minimal summary for a diagram badge:
  model + threshold + ratio/range + gain, shown only when `on: true`
  (consistent with the project's existing "active only" rule).

### 1.3 Key source (sidechain) routing

This is a real extra signal input into a specific processing block, not just
a cosmetic parameter — manual §6.1 ("KEY SOURCE: select another channel as
the sidechain input") and §"Common Controls" (dynamics) both describe it as
an actual audio tap:

- `ch.<n>.gatesc.src` / `ch.<n>.dynsc.src`: enum `SELF` or `CH.1`..`CH.40` —
  a channel's Gate or Comp can key off *another input channel*, not a bus.
- `bus/main/mtx.<n>.dynsc.src`: enum `SELF` or `BUS.1-16`/`MAIN.1-4`/
  `MTX.1-8`/`AUX.1-8` — a bus/main/matrix's Comp can key off *any* other
  bus/main/matrix/aux (not individual input channels).
- So the premise "a bus can be used as a key source instead of the channel
  it's applied to" is literally true for bus/main/matrix dynamics, and the
  equivalent for a channel's Gate/Comp is "another channel" rather than a
  bus — worth confirming that's the distinction you had in mind, since the
  console doesn't offer `BUS.n` as a channel-level key source at all.
- `gatesc.tap`/`dynsc.tap` additionally picks *which point* along the key
  source's own chain to grab (same 8-value enum as `ptap`, §1.4). The manual
  phrasing here ("the channel's signal path") is ambiguous about whose
  chain it means; I'm reading it as the *key source's* chain since that's
  the only one with a meaningful choice, but haven't been able to verify
  against a snapshot that actually exercises it (the sample file has every
  `*sc.src` at `SELF`, `*sc.type` at `OFF`) — flag this as needing a
  real-world snapshot to confirm, rather than something to design hard
  around.

### 1.4 Tap points

- `ch.<n>.ptap` ("TAP POINT"): 8 positions — `INPUT`, `FILTER`, `TAP 3`,
  `TAP 4`, `TAP 5`, `PRE FDR`, `POST FDR`, `POST PROC`. TAP 3/4/5 are
  "between processing slot N and N+1", and the slot order itself is
  configurable per-channel via `ch.<n>.proc` (a 4-letter permutation of
  G/E/D/I — Gate/EQ/Dyn/Ins1; Ins2 is always last, post-fader). So "TAP 3"
  on one channel and "TAP 3" on another may sit before/after different
  processors. For a routing diagram, I'd treat `ptap`'s enum label as
  sufficient detail (resolving it against `proc` to say exactly which
  processor it's before/after is possible but feels like more precision
  than the diagram needs — flag if you disagree).
- `aux`/`bus`/`main`/`mtx` have **no `ptap` field** — confirmed absent from
  `ae_data`. Their tap point is fixed by the manual: Aux = "post insert
  point, pre-fader"; Bus/Main/Matrix = "post insert point 1, pre-fader".
  These only matter as a fixed label, since there's no selectable value to
  surface from the snapshot.
- This feeds **send mode**, which is where tap points actually show up as
  routing: `send.<n|MXn>.mode` on `ch`/`aux` is one of `PRE` (manual calls
  this "TAP" — derived from the channel's `ptap` point), `POST`
  (post-fader), or `GRP` ("GROUP" — no independent level, literally the
  same signal as the channel's main/group output post-fader). `bus`/`main`/
  `mtx` sends have no `mode` key at all, just a `pre` boolean (pre-fader at
  the fixed tap position, or post-fader) — no GROUP option, matching the
  manual (no "group" concept for those strip types).

## 2. Proposed representation

Keep `RoutingGraph`'s node/edge shape as-is; extend via the existing
`meta: dict` on `Edge`, plus one new optional field on `Node`, rather than
reworking the data model:

- **`Edge.meta["level_db"]`** — the resolved `lvl` for any `send`/`main`
  edge (and, new, **`main.<n>.send.MXn`/`bus.<n>.send.n`**, which currently
  go through the same `_add_sends` path and already carry `lvl`). Render as
  the edge label (e.g. `"-6.2 dB"`), replacing the current blank/`channel`-
  only label.
- **`Edge.meta["tap"]`** — a short string describing where the send
  actually originates: the `ptap` label when `mode == "PRE"`, `"POST"`
  when `mode == "POST"`, `"GROUP"` (and suppress `level_db` there — GROUP
  has no independent level) when `mode == "GRP"`, or `"PRE-FADER"`/
  `"POST-FADER"` from the `pre` boolean for bus/main/mtx sends. Appended to
  the edge label alongside the level.
- **Preamp gain / trim** — attach preamp gain (`io/in/.../g`) to the
  `io_in` node's own label (it's a property of the Source, not the edge),
  and channel trim (`in/set/trim`) to the `io_in → channel` edge label,
  since trim is per-strip.
- **`Node.dynamics: tuple[DynamicsBadge, ...]`** (new, small dataclass:
  `kind` "gate"/"comp", `model`, `threshold`, `ratio_or_range`, `gain`) —
  populated only from blocks with `on: true`. Rendered as extra rows inside
  the node's box via Graphviz's HTML-like label table, so it reads as
  "this channel has an active gate + compressor" without needing a separate
  node in the signal-flow graph (it isn't a routing branch, it's inline
  processing).
- **Key source edges** — a new edge *kind*, e.g. `Edge.meta["kind"] =
  "key"`, from the key-source node to the *same destination node* that
  hosts the Gate/Comp (not a separate processor node). Rendered with
  `style="dashed"`, a distinct color, and `constraint="false"` in Graphviz
  so it doesn't warp the left-to-right rank layout (a bus/main/mtx keying
  off a downstream bus would otherwise introduce a back-edge into the rank
  ordering). This directly answers "shown with a different line type."

## 3. Main open question: how much of this is always-on?

The current diagram is deliberately minimal (plain boxes, blank edges) so it
stays legible across a real console's worth of channels. Adding level
labels, tap-point text, dynamics badges, and key-source edges to *every*
node/edge at once risks making a 40-channel diagram unreadable. I'd suggest
making this additive detail **opt-in via CLI flags** on the existing
`routing` command (e.g. `--show-levels`, `--show-dynamics`, `--show-keys`),
independently togglable, rather than baking all of it into the one diagram
unconditionally — the routing-only diagram stays the default/clean view,
and detail layers stack on top for whoever wants to audit gain staging or
dynamics setup specifically. Happy to default some subset on if you'd rather
not have flags at all; flagging this because it changes the CLI surface and
seemed worth agreeing on before building it.

## 4. Suggested build order

1. Extend `routing.py`: carry `lvl`/`mode`/`pre` into `Edge.meta` for
   existing send/main edges (no new nodes yet) — smallest change, immediately
   useful, no rendering changes required beyond reading the new meta keys.
2. Add preamp-gain/trim labelling on `io_in` nodes and input edges.
3. Add `Node.dynamics` population from `gate`/`dyn` blocks + badge rendering.
4. Add key-source edges (`gatesc.src`/`dynsc.src` resolution, new edge kind,
   dashed/non-constraining rendering) — do this last since it's the one
   piece touching graph layout (rank/constraint behavior), and benefits most
   from the rest of the label vocabulary already existing to borrow from.
5. Wire the above behind CLI flags per §3, defaulting to the current
   routing-only behaviour.

Each step is independently testable against `wing_snaps/Announcements.snap`,
same pattern as the existing `test_routing.py`/`test_render.py` suites.
