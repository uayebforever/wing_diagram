from argparse import ArgumentParser
from logging import getLogger
from pathlib import Path

from .command import Command
from ...propmap import PropMap, default_propmap_path
from ...render import GraphvizRenderer, MermaidRenderer, Renderer
from ...routing import build_routing_graph
from ...snapfile import load_snapshot

log = getLogger(__name__)

#: Default output path per `--renderer` choice, used when `--out` isn't
#: given -- Graphviz renders straight to an image, Mermaid writes its own
#: diagram source (see `MermaidRenderer`).
_DEFAULT_OUT_BY_RENDERER = {
    "graphviz": Path("routing.svg"),
    "mermaid": Path("routing.mmd"),
}


class RoutingCommand(Command):
    name = "routing"
    help = "Generate a routing diagram from a Wing .snap snapshot file."

    def configure_arg_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument("snapfile", type=Path, help="Path to a Wing .snap file")
        parser.add_argument(
            "-o",
            "--out",
            type=Path,
            default=None,
            help="Output path for the rendered diagram "
            "(default: routing.svg for --renderer graphviz, routing.mmd for --renderer mermaid)",
        )
        parser.add_argument(
            "--renderer",
            choices=sorted(_DEFAULT_OUT_BY_RENDERER),
            default="mermaid",
            help="Diagram renderer to use (default: mermaid)",
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

        renderer: Renderer = (
            GraphvizRenderer() if args.renderer == "graphviz" else MermaidRenderer()
        )
        out = args.out or _DEFAULT_OUT_BY_RENDERER[args.renderer]
        out_path = renderer.render(graph, out)
        log.info("Routing graph: %d nodes, %d edges", len(graph.nodes), len(graph.edges))
        print(f"Wrote routing diagram to {out_path}")
