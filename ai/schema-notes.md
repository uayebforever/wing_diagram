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
