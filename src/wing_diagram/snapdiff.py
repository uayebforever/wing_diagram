from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .propmap import PropMap, PropMapEntry
from .snapfile import Snapshot

#: Sections whose numeric 2nd path segment addresses one repeated element
#: instance (`ch/3/...`) rather than a fixed container -- changes under one
#: of these get grouped (and headed) per element, like `routing.py`'s
#: `_SENDING_SECTIONS`/`_SINGLE_SOURCE_SECTIONS` but covering every
#: instanced section, not only the ones `routing.py` models for the diagram.
_INDEXED_SECTIONS = ("ch", "aux", "bus", "main", "mtx", "dca", "mgrp", "fx")

_KIND_LABELS = {
    "ch": "Ch",
    "aux": "Aux",
    "bus": "Bus",
    "main": "Main",
    "mtx": "Mtx",
    "dca": "DCA",
    "mgrp": "Mute Group",
    "fx": "FX",
}


@dataclass(frozen=True)
class ParamChange:
    """One leaf parameter that differs between two snapshots.

    `path` is the full slash path (e.g. `"ch/3/gate/GATE/thr"`), matching
    `Snapshot.get()`'s convention. `old`/`new` are the raw snapshot values,
    `None` for whichever side doesn't have that path at all (`kind` is then
    `"added"`/`"removed"` rather than `"changed"`).
    """

    path: str
    old: Any
    new: Any

    @property
    def kind(self) -> str:
        if self.old is None and self.new is not None:
            return "added"
        if self.old is not None and self.new is None:
            return "removed"
        return "changed"


@dataclass(frozen=True)
class ElementGroup:
    """One mixer element's (or top-level section's) changes, for display.

    `prefix` is the path shared by every change in the group (e.g.
    `"ch/3"`, `"io/in/LCL/7"`, or a bare top-level section like `"cfg"`) --
    `format_change` uses it to show each change's label relative to the
    group rather than repeating the element's own path on every line.
    """

    prefix: str
    heading: str
    changes: list[ParamChange]


def diff_snapshots(old: Snapshot, new: Snapshot) -> list[ParamChange]:
    """Every leaf path that differs between `old.ae_data` and `new.ae_data`,
    added, or removed -- sorted by path for stable output.

    Values are compared as-is, with no propmap-aware tolerance or rounding:
    that belongs to `format_change` at display time, kept separate so this
    stays a precise, lossless diff.
    """
    old_leaves = _flatten(old.ae_data)
    new_leaves = _flatten(new.ae_data)
    changes = []
    for path in sorted(set(old_leaves) | set(new_leaves)):
        old_value = old_leaves.get(path)
        new_value = new_leaves.get(path)
        if old_value != new_value:
            changes.append(ParamChange(path=path, old=old_value, new=new_value))
    return changes


def _flatten(data: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(data, dict):
        return {prefix: data}
    leaves: dict[str, Any] = {}
    for key, value in data.items():
        child_prefix = f"{prefix}/{key}" if prefix else str(key)
        leaves.update(_flatten(value, child_prefix))
    return leaves


def group_changes(
    changes: list[ParamChange], old: Snapshot, new: Snapshot, propmap: PropMap
) -> list[ElementGroup]:
    """Groups a flat change list by the mixer element (or top-level section)
    each path belongs to, in first-seen order, so a report reads "one
    heading per channel/bus/etc." rather than one line per raw path."""
    by_prefix: dict[str, list[ParamChange]] = {}
    order: list[str] = []
    for change in changes:
        prefix = _group_prefix(change.path)
        if prefix not in by_prefix:
            by_prefix[prefix] = []
            order.append(prefix)
        by_prefix[prefix].append(change)
    return [
        ElementGroup(
            prefix=prefix,
            heading=_heading(prefix, old, new, propmap),
            changes=by_prefix[prefix],
        )
        for prefix in order
    ]


def _group_prefix(path: str) -> str:
    segments = path.strip("/").split("/")
    if segments[0] in _INDEXED_SECTIONS and len(segments) > 1 and segments[1].isdigit():
        return "/".join(segments[:2])
    if segments[0] == "io" and len(segments) > 3 and segments[3].isdigit():
        return "/".join(segments[:4])
    return segments[0]


def _heading(prefix: str, old: Snapshot, new: Snapshot, propmap: PropMap) -> str:
    segments = prefix.split("/")
    name = new.get(f"{prefix}/name") or old.get(f"{prefix}/name")

    if segments[0] in _INDEXED_SECTIONS and len(segments) == 2:
        label = f"{_KIND_LABELS.get(segments[0], segments[0].capitalize())} {segments[1]}"
    elif segments[0] == "io" and len(segments) == 4:
        bank = propmap.describe(f"io/{segments[1]}/{segments[2]}")
        bank_label = bank.display_name if bank else segments[2]
        label = f"{bank_label} {segments[3]}"
    else:
        # A non-instanced section (`cfg`, `cards`, `play`, `rec`, ...) has no
        # per-element "name" concept worth surfacing in the heading.
        entry = propmap.describe(prefix)
        label = entry.display_name if entry else segments[0].capitalize()
        name = None

    return f"{label} — {name}" if name else label


def format_change(change: ParamChange, prefix: str, propmap: PropMap) -> str:
    """A one-line human-readable rendering of `change`, e.g.
    `"GATE > THR: -20.0 dB → -18.0 dB"`."""
    entry = propmap.describe(change.path)
    label = _field_label(change.path, prefix, propmap)
    if change.kind == "added":
        return f"{label}: added ({_format_value(change.new, entry)})"
    if change.kind == "removed":
        return f"{label}: removed (was {_format_value(change.old, entry)})"
    return f"{label}: {_format_value(change.old, entry)} → {_format_value(change.new, entry)}"


def _field_label(path: str, prefix: str, propmap: PropMap) -> str:
    """Breadcrumb label for `path` relative to `prefix`, built from each
    remaining segment's own propmap `display_name` -- e.g. `"GATE > THR"`
    for `ch/3/gate/GATE/thr` under prefix `"ch/3"`. Generic across every
    section rather than a per-section label table.

    A numeric segment (an array index, not a named key) is skipped, and a
    segment whose resolved label repeats the previous one is dropped too --
    both the Gate and Comp model-selector segments (`gate.GATE`/`dyn.GATE`)
    share their container's own longname (`"GATE"`), so without this a
    threshold would read "GATE > GATE > THR" instead of "GATE > THR".
    """
    rest = path[len(prefix) :].strip("/")
    if not rest:
        return path
    labels: list[str] = []
    walked = prefix
    for segment in rest.split("/"):
        walked = f"{walked}/{segment}"
        if segment.isdigit():
            continue
        entry = propmap.describe(walked)
        label = entry.display_name if entry else segment
        if not labels or labels[-1].lower() != label.lower():
            labels.append(label)
    return " > ".join(labels) if labels else rest


def _format_value(value: Any, entry: PropMapEntry | None) -> str:
    if entry is not None:
        value = entry.resolve(value)
    if isinstance(value, bool):
        return "On" if value else "Off"
    if isinstance(value, float):
        rounded = round(value, 2)
        text = f"{rounded:+.2f}" if entry is not None and entry.unit == "dB" else f"{rounded:g}"
        return f"{text} {entry.unit}" if entry is not None and entry.unit else text
    if value == "":
        return "(blank)"
    return str(value)


def build_diff_report(
    old: Snapshot, new: Snapshot, propmap: PropMap, title: str | None = None
) -> str:
    """A Markdown report of every parameter that differs between `old` and
    `new`, grouped by mixer element with human-readable labels/values -- see
    `diff_snapshots`/`group_changes`/`format_change`."""
    changes = diff_snapshots(old, new)
    lines = [f"# {title}" if title else "# Snapshot diff", ""]

    if not changes:
        lines.append("No differences.")
        return "\n".join(lines) + "\n"

    groups = group_changes(changes, old, new, propmap)
    element_count = len(groups)
    lines.append(
        f"{len(changes)} parameter{'s' if len(changes) != 1 else ''} changed across "
        f"{element_count} element{'s' if element_count != 1 else ''}."
    )
    lines.append("")

    for group in groups:
        lines.append(f"## {group.heading}")
        lines.append("")
        for change in sorted(group.changes, key=lambda c: c.path):
            lines.append(f"- {format_change(change, group.prefix, propmap)}")
        lines.append("")

    return "\n".join(lines)
