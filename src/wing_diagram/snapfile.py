from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .exceptions import UserError

_PATH_SEP = "/"

_HEADER_KEYS = (
    "type",
    "creator_fw",
    "creator_sn",
    "creator_model",
    "creator_version",
    "creator_name",
    "created",
)


class Snapshot:
    """A parsed Wing `.snap` file.

    `ae_data` is kept as a plain nested dict rather than a typed model: the
    Wing parameter space is large, deeply nested, and the shape of a given
    block depends on runtime selectors elsewhere in the same block (e.g. an
    `eq` node's children change depending on its own `mdl` field) -- a
    rigid schema would fight the data more than it would help. Use `get()`
    to reach into it by slash path, and cross-reference a `PropMap`
    (`wing_diagram.propmap`) to interpret what a path/value means. See
    `ai/schema-notes.md` for what we've learned about the shape so far.
    """

    def __init__(self, header: dict[str, Any], ae_data: dict[str, Any]):
        self.header = header
        self.ae_data = ae_data

    @property
    def type(self) -> str | None:
        return self.header.get("type")

    @property
    def creator_model(self) -> str | None:
        return self.header.get("creator_model")

    @property
    def creator_fw(self) -> str | None:
        return self.header.get("creator_fw")

    @property
    def creator_version(self) -> str | None:
        return self.header.get("creator_version")

    @property
    def created(self) -> str | None:
        return self.header.get("created")

    def get(self, path: str, default: Any = None) -> Any:
        """Look up a value under `ae_data` by slash path.

        `path` uses the same convention as `propmap.jsonl`'s `fullname`
        field, minus its leading slash, e.g. `"ch/1/in/conn/grp"`.
        """
        node: Any = self.ae_data
        for segment in path.strip(_PATH_SEP).split(_PATH_SEP):
            if not isinstance(node, dict) or segment not in node:
                return default
            node = node[segment]
        return node


def load_snapshot(path: str | Path) -> Snapshot:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if "ae_data" not in raw or not isinstance(raw["ae_data"], dict):
        raise UserError(f"{path}: not a recognizable Wing snapshot (missing 'ae_data')")

    header = {key: raw[key] for key in _HEADER_KEYS if key in raw}
    return Snapshot(header=header, ae_data=raw["ae_data"])
