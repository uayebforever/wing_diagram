from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EnumItem:
    item: str
    longitem: str | None = None

    @property
    def display(self) -> str:
        return self.longitem if self.longitem is not None else self.item


@dataclass(frozen=True)
class PropMapEntry:
    """One parsed `propmap.jsonl` line: metadata for one parameter path.

    `fullname` is the slash-delimited path (e.g. `/ch/1/in/conn/grp`),
    matching `Snapshot.get()`'s path convention (`wing_diagram.snapfile`)
    once you add back the leading slash.

    `name` is absent on entries whose final path segment is a numeric
    array index (e.g. `/io/in/LCL/1`, one of 40-odd near-identical sibling
    entries for each channel/input/etc.) rather than a named key -- for
    those, `name` falls back to that index segment.
    """

    id: int
    fullname: str
    type: str
    name: str
    longname: str | None = None
    items: tuple[EnumItem, ...] = ()

    @property
    def display_name(self) -> str:
        return self.longname if self.longname is not None else self.name

    def resolve(self, raw_value: Any) -> Any:
        """Resolve a raw snapshot value to its human-readable form.

        Looks up the matching `EnumItem`'s display label for `string enum`
        types; falls back to `raw_value` unchanged for every other type, or
        if `raw_value` doesn't match any known item.
        """
        for enum_item in self.items:
            if enum_item.item == raw_value:
                return enum_item.display
        return raw_value


class PropMap:
    """Path -> metadata lookup for the Wing parameter space.

    Built from `propmap.jsonl`: one JSON object per line, one line per
    parameter *instance* in the entire Wing parameter space, not just one
    snapshot and not templated -- `/ch/1/...` through `/ch/40/...` are each
    listed out in full with identical metadata, so this holds on the order
    of tens of thousands of entries for the lifetime of a run. See
    `ai/schema-notes.md` for more on the shape of this file.
    """

    def __init__(self, entries_by_fullname: dict[str, PropMapEntry]):
        self._entries_by_fullname = entries_by_fullname

    @classmethod
    def load(cls, path: str | Path) -> "PropMap":
        entries: dict[str, PropMapEntry] = {}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = _parse_entry(json.loads(line))
                entries[entry.fullname] = entry
        return cls(entries)

    def describe(self, fullname: str) -> PropMapEntry | None:
        if not fullname.startswith("/"):
            fullname = "/" + fullname
        return self._entries_by_fullname.get(fullname)

    def resolve(self, fullname: str, raw_value: Any) -> Any:
        """Resolve `raw_value` found at `fullname` to its human-readable form.

        Falls back to `raw_value` unchanged if `fullname` isn't a known
        path, or isn't an enum type.
        """
        entry = self.describe(fullname)
        if entry is None:
            return raw_value
        return entry.resolve(raw_value)

    def __len__(self) -> int:
        return len(self._entries_by_fullname)


def _parse_entry(data: dict[str, Any]) -> PropMapEntry:
    raw_items = data.get("items")
    items = (
        tuple(EnumItem(item=i["item"], longitem=i.get("longitem")) for i in raw_items)
        if raw_items
        else ()
    )

    fullname = data["fullname"]
    name = data.get("name") or fullname.rsplit("/", 1)[-1]

    return PropMapEntry(
        id=data["id"],
        fullname=fullname,
        type=data["type"],
        name=name,
        longname=data.get("longname"),
        items=items,
    )
