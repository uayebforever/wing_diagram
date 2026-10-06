from argparse import ArgumentParser
from logging import getLogger
from pathlib import Path

from .command import Command
from ...propmap import PropMap, default_propmap_path
from ...render import GraphvizRenderer
from ...routing import build_routing_graph
from ...snapfile import load_snapshot

log = getLogger(__name__)


class RoutingCommand(Command):
    name = "routing"
    help = "Generate a routing diagram from a Wing .snap snapshot file."

    def configure_arg_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument("snapfile", type=Path, help="Path to a Wing .snap file")
        parser.add_argument(
            "-o",
            "--out",
            type=Path,
            default=Path("routing.svg"),
            help="Output path for the rendered diagram (default: routing.svg)",
        )
        parser.add_argument(
            "--propmap",
            type=Path,
            default=None,
            help="Path to propmap.jsonl (default: the copy bundled with this package)",
        )

    def execute(self, args) -> None:
        snapshot = load_snapshot(args.snapfile)
        propmap = PropMap.load(args.propmap or default_propmap_path())
        graph = build_routing_graph(snapshot, propmap)

        renderer = GraphvizRenderer()
        out_path = renderer.render(graph, args.out)
        log.info("Routing graph: %d nodes, %d edges", len(graph.nodes), len(graph.edges))
        print(f"Wrote routing diagram to {out_path}")
