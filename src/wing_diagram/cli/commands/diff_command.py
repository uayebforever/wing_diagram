from argparse import ArgumentParser
from logging import getLogger
from pathlib import Path

from .command import Command
from ...propmap import PropMap, default_propmap_path
from ...snapdiff import build_diff_report
from ...snapfile import load_snapshot

log = getLogger(__name__)


class DiffCommand(Command):
    name = "diff"
    help = "Summarize the parameter differences between two Wing .snap snapshot files."

    def configure_arg_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument("old_snapfile", type=Path, help="Path to the earlier Wing .snap file")
        parser.add_argument("new_snapfile", type=Path, help="Path to the later Wing .snap file")
        parser.add_argument(
            "-o",
            "--out",
            type=Path,
            default=None,
            help="Output path for the diff report (default: print to stdout)",
        )
        parser.add_argument(
            "--propmap",
            type=Path,
            default=None,
            help="Path to propmap.jsonl (default: the copy bundled with this package)",
        )
        parser.add_argument(
            "--title",
            default=None,
            help="Title shown at the top of the report "
            "(default: '<old snapfile> → <new snapfile>')",
        )

    def execute(self, args) -> None:
        old = load_snapshot(args.old_snapfile)
        new = load_snapshot(args.new_snapfile)
        propmap = PropMap.load(args.propmap or default_propmap_path())
        title = args.title or f"{args.old_snapfile.stem} → {args.new_snapfile.stem}"

        report = build_diff_report(old, new, propmap, title=title)

        if args.out:
            args.out.write_text(report)
            log.info("Wrote diff report to %s", args.out)
            print(f"Wrote diff report to {args.out}")
        else:
            print(report)
