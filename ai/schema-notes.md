# Wing schema notes

Working notes on the actual shape of `ae_data` and `propmap.jsonl`, gathered
by inspecting `wing_snaps/Announcements.snap` and `src/wing_diagram/propmap.jsonl`
directly. `ai/initial-plan.md` sketched the schema from a first pass; this
file corrects/extends it as we learn more, and exists so the next
implementation pass (`wing_diagram.routing`, in particular) doesn't have to
re-derive this by grepping the raw files again. Update it whenever a
build pass learns something new and non-obvious about the shape — treat it
as a living doc, not a one-time writeup.

## `propmap.jsonl` is not templated

Every instance of a repeated block is listed out in full: `/ch/1/...`
through `/ch/40/...` each get their own ~565 lines with identical
`longname`/`type`/`items`, rather than one templated `/ch/{n}/...` entry.
Same for `bus` (16), `main` (4), `mtx` (8), `aux` (8), `dca` (16), `mgrp`
(8), `fx` (16). This is why the file is ~60k lines / ~10MB. `PropMap`
currently keeps one entry per literal fullname (simplest correct thing); if
memory or load time ever becomes a problem, the fix is to normalize numeric
path segments (e.g. `/ch/1/...` -> `/ch/#/...`) and dedupe, since the
metadata is index-invariant.

## Not every `propmap.jsonl` line has a `name`

~3000 of the ~60700 lines omit `name` entirely and have `index` instead
(e.g. `{"id":...,"index":1,"type":"node","fullname":"/io/in/LCL/1"}`).
This happens exactly when the final path segment is a bare numeric array
index (an instance number) rather than a named key — confirmed by checking
every `name`-less line's `fullname` tail is all-digits. These are mostly
`type: node` container entries (sometimes with `longname`, sometimes with
`minint`/`maxint` instead) for one specific instance in an array, not
leaf parameters. `PropMap` falls back to that index segment as `name` when
it's missing.

## Model-dependent sub-blocks

Many nodes (`eq`, `dyn`, `gate`, `preins`/`postins`, `flt`, ...) have an
`mdl` (or `ins`) selector field alongside a *set* of mutually-exclusive
model-specific sub-objects, all enumerated in `propmap.jsonl` under that
node — e.g. `/mtx/1/eq/STD/...`, `/mtx/1/eq/SOUL/...`, `/mtx/1/eq/E88/...`
are all present in propmap for a single channel, but only one of those
model families' keys actually shows up in a given snapshot's `ae_data`,
selected by the sibling `mdl` field. This doesn't matter for routing
(we only care about `in`/`main`/`send`/`dir` keys, never `eq`/`dyn`), but it
means propmap's line count per node is not a reliable proxy for "how many
keys will actually be present on this node in a real snapshot" — don't
assume every propmap key for a path will be present in `ae_data`.

## Source types have different connection shapes

- `ch`/`aux` (and presumably anything with a single upstream source) use
  `in.conn` = `{"grp": <enum>, "in": <int>, "altgrp": <enum>, "altin": <int>}`.
  `grp` enum includes the physical I/O groups (`LCL`, `AUX`, `A`/`B`/`C`,
  `SC`, `USB`, `CRD`, `MOD`, `PLAY`, `AES`, `USR`, `OSC`) *and* internal
  re-patch targets `BUS`, `MAIN`, `MTX`.
- `bus` has **no** `in.conn` at all — a bus's content is implicitly the sum
  of whatever sources have `send.<busN>.on = true` pointed at it. There is
  no single "this bus's source" field to read.
- `mtx` does **not** have a summed-send-style source list despite being a
  routable destination from `send.MXn`. It has a `dir` block
  (`{"on", "lvl", "inv", "in"}`) which is a *separate*, single-source "direct
  in" path with its own small enum (`OFF`, `AES`, `MON.PH`, `MON.SPK`,
  `MON.BUS` in the sample file) — this looks like a monitor/AES bypass tap,
  not the matrix's general-purpose input. A matrix's "normal" sources are
  still the `send.MXn` entries on `ch`/`aux`/`bus`/`main`, same mechanism as
  a bus. Treat `dir.in` as a secondary/optional edge source, not the primary
  one, when building the routing graph.
- `main` has a `send` block, but **only** to matrices (`MX1`..`MX8`), not to
  numbered buses — mains cannot feed sub-buses, only matrices. `main` has no
  `main.{1-4}` block (can't feed another main) and no `in.conn` (same
  "implicit sum of channel/bus sends" story as `bus`).
- `main.send.MXn` entries are shaped `{"on", "lvl", "pre"}` — missing the
  `pon`/`mode`/`plink`/`pan` fields that `ch`/`aux`/`bus` sends have. Send
  shape is not uniform across source types; don't assume one dataclass
  covers every `send.*` entry.

## `io.out` has more destination kinds than the initial plan covered

`io.out.<grp>.<n>.grp` enum is `OFF`, `LCL`, `AUX`, `A`, `B`, `C`, `SC`,
`USB`, `CRD`, `MOD`, `MAIN`, `MTX`, `BUS`, `SEND` (FX send), `MON`
(monitor) — i.e. a physical output can carry a bus or matrix too, not just
a main. `io.in` groups and `io.out` groups are also not identical sets
(`in` has `PLAY`/`USR`/`OSC`/`AES`-in that `out` doesn't, `out` has `REC`
that `in` doesn't) — don't assume the group vocabulary is symmetric between
`io.in` and `io.out`.

## Channel count varies by model

The sample file (`creator_model: WING-EDIT`, i.e. the desktop/offline
editor) has 40 `ch` entries, not the 20 the initial plan assumed from a
smaller console. Always derive the instance count from what's actually in
`ae_data` (or from `propmap.jsonl`'s enumerated instances) rather than
hardcoding per-section counts anywhere.

## Open questions, still unverified

- `fx` patching mechanism — still unknown, still out of scope per the
  initial plan.
- Whether `dir.in`'s small enum is truly fixed, or whether its `items` list
  in `propmap.jsonl` varies by model/firmware (we've only inspected one
  snapshot/propmap pairing so far).

## `bus`/`main`/`mtx` do have an `in` key -- it's just not a source

Confirmed directly (schema-notes previously only said bus has "no
`in.conn`", which could be read as "no `in` key at all"): `bus.<n>.in`,
`main.<n>.in`, and `mtx.<n>.in` are all present, but each is just
`{"set": {"inv", "trim", "bal"}}` -- phase/trim/balance controls on the
element's own fader strip, no `conn` sub-key, nothing resembling a source.
Don't let the presence of `in` fool you into thinking these have a single
upstream source after all.

## `in.conn`'s alt-source pair (`altgrp`/`altin`) can be the *active* one

`ch`/`aux`'s `in.set` has `altsrc` (bool-as-int, "ALT INPUT") alongside
`srcauto` ("ALT AUTOSW"). `altsrc` is what actually selects, for a given
snapshot, whether the strip's live source is `conn.{grp,in}` (false) or
`conn.{altgrp,altin}` (true) -- `routing.py` reads this flag and picks the
active pair accordingly. `srcauto` governs *automatic* failover to the alt
source on signal loss, which isn't a property a static snapshot can
represent either way, so `wing_diagram.routing` ignores it entirely. Not
exercised by the sample file (`Announcements.snap` has `altsrc: false`
throughout), so this path is only unit-tested, not validated against real
console data yet -- worth re-checking against a snapshot that actually uses
alt sourcing if one turns up.

## `io.out`'s `grp`/`in` is a full patch matrix, not just "carries a main"

Confirmed by both the sample file and `propmap.jsonl`'s enum for e.g.
`/io/out/LCL/1/grp`: a physical output's source `grp` can be *any* of the
physical input groups (`LCL`, `AUX`, `A`, `B`, `C`, `SC`, `USB`, `CRD`,
`MOD`, `PLAY`, `AES`, `USR`, `OSC` -- the exact same vocabulary as
`io.in`'s own group keys, and as `in.conn.grp`'s physical options) *in
addition to* `BUS`/`MAIN`/`MTX`/`SEND`/`MON`/`OFF`. So a physical output
jack can be patched straight from another physical input (hardware
passthrough, bypassing the mix engine entirely), not only from an internal
bus/main/matrix. `wing_diagram.routing._resolve_output_source` shares the
physical-group half of this resolution with `in.conn`'s
`_resolve_source`, but **not** the internal-re-patch half -- see the next
note, which corrects an earlier (wrong) version of this note that assumed
they were identical.

## `io.out`'s internal-source `in` is a flattened L/R tap index, not the element's own index

This one actually produced a wrong diagram in an earlier pass, caught by
eyeballing the rendered output against the real console: every mixer
element with a stereo signal path (`ch`, `aux`, `bus`, `main`, `mtx` --
all of them, confirmed via each section's own `busmono` field, which lets
*any* of them be downmixed to mono without changing this) occupies
exactly **2** taps in `io.out`'s source numbering for `BUS`/`MAIN`/`MTX`,
always, regardless of that element's own `busmono` setting: tap `1` is
element 1's L, tap `2` is element 1's R, tap `3` is element 2's L, and so
on -- `element = (tap - 1) // 2 + 1`, `channel = "L" if (tap - 1) % 2 ==
0 else "R"`. A mono-downmixed element still reserves both taps (just with
the same signal duplicated onto each), so even its "R" tap is a valid,
meaningful patch target.

Confirmed against `Announcements.snap`: `main.1` ("Sanctuary Mix") has
`busmono: true`; `main.2` ("Stream Mix") has `busmono: false`. The active
`io.out` entries are `io.out.LCL.5 == {"grp": "MAIN", "in": 3}`,
`io.out.LCL.6 == {"grp": "MAIN", "in": 4}`, `io.out.LCL.8 == {"grp":
"MAIN", "in": 2}`. Naively treating `in` as the main's own index (1-4)
would read this as "main 2 → LCL 5, main 3 → LCL 6, main 4 → LCL 8" --
wrong, and an earlier version of `wing_diagram.routing` did exactly that.
Under the tap formula it's "main 1 R → LCL 8, main 2 L → LCL 5, main 2 R →
LCL 6" -- i.e. Sanctuary Mix (mono) on LCL 8, Stream Mix (stereo) split
across LCL 5 (L) / LCL 6 (R). That's what the console is actually
configured to do.

By contrast, `in.conn` (`ch`/`aux` re-patching from `BUS`/`MAIN`/`MTX`)
and `cfg.mon.<n>.src` (whose enum lists exactly 16 `BUS.<n>`/4
`MAIN.<n>`/8 `MTX.<n>` items, not 32/8/16) both address the element
directly by its own 1-based index, picking up the whole stereo element
rather than a single mono tap -- that makes sense, since both of those
targets are themselves stereo-capable (another channel strip; a stereo
headphone/monitor output), unlike a physical output jack which is mono
and must pick a side. So `wing_diagram.routing` has two separate
resolvers: `_resolve_source` (direct index, for `in.conn`) and
`_resolve_output_source` (flattened tap, for `io.out`) -- don't
accidentally reunify them.

`Edge.meta["channel"]` (`"L"`/`"R"`) now carries this for `io.out` edges
sourced from an internal element, and `GraphvizRenderer` draws it as an
edge label, so the rendered diagram shows which side of a stereo
bus/main/mtx actually reached a given physical output.

## `cfg.mon.*` (monitor/PFL buses) are a real routing destination, deliberately out of scope

`io.out.<grp>.<n>.grp` can be `"MON"`, meaning that physical output jack
carries a monitor/PFL bus (`cfg.mon.<n>`, aka "PHONES" in the sample file)
rather than a main/bus/matrix. `cfg.mon.<n>` has its own `src` field (a
dotted-string enum like `"MAIN.2"`, `"BUS.5"`, `"MTX.3"`, `"AUX.1"` --
notably a *different* shape from the `{"grp", "in"}` dict used everywhere
else) selecting what feeds that monitor bus, plus `srcmix`/`dirin` for
further monitor-specific mixing. The initial plan's description of `cfg`
("monitor, solo, talkback, etc. -- not routing") already puts this out of
scope, and `wing_diagram.routing` follows that: `io.out` entries with
`grp == "MON"` are skipped (no edge emitted, same treatment as `SEND`/FX),
and `cfg.mon` itself is never visited. This does mean a small number of
real `io.out` entries (2 of 7 active ones in the sample file) don't appear
in the diagram at all -- that's intentional, not a bug, but worth knowing
if the rendered graph looks like it's missing an output you expected to
see.

## Node/edge inclusion rule actually used by `wing_diagram.routing`

The initial plan said "active routes only" about *edges*; `build_routing_graph`
extends the same idea to *nodes*: a node (physical I/O, channel, bus, main,
or matrix) is only included in the `RoutingGraph` if it's an endpoint of at
least one active edge. A physical input that's never patched anywhere, or a
channel that's fully off (`in.conn.grp == "OFF"` and no active
`main`/`send`), is omitted entirely rather than shown as a disconnected
box -- this keeps the diagram legible given how many physical I/O
instances a real console has (e.g. 48 AES50-A inputs, most unused in any
given snapshot). If a future pass wants an "show everything" mode, this is
the rule to make configurable.

## Group-code display labels are resolved via propmap, not hardcoded

`wing_diagram.routing._group_label` resolves a group code (e.g. `"LCL"`,
`"MON"`) to its on-console label (e.g. `"LOCAL IN"`, `"MONITOR"`) by
calling `PropMap.resolve()` against a fixed path
(`io/out/LCL/1/grp`) chosen because its enum happens to be the superset of
every group code the routing/render code needs a label for (physical I/O
groups plus `BUS`/`MAIN`/`MTX`/`SEND`/`MON`/`OFF`). This is a bit of an
implicit assumption -- that this one path's enum `items` list is
representative of the shared `grp` vocabulary used elsewhere -- which held
for the one snapshot/propmap pairing inspected so far. If a future
model/firmware's propmap ever turns out to vary this enum per-path (unlike
the "Model-dependent sub-blocks" case above, nothing currently suggests it
does), this helper would need a fallback.
