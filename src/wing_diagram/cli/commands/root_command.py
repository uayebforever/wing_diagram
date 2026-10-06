import sys
from argparse import ArgumentParser

from . import version
from .command import Command
from .routing_command import RoutingCommand
from .test_command import TestCommand
from .version import VersionCommand


class RootCommand(Command):
    name = "wing_diagram"
    help = "A tool to generate WING mixer routing diagrams."
    subcommands = [VersionCommand(), TestCommand(), RoutingCommand()]

    def configure_arg_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--version",
            action='store_true',
            help="Print version information and exit")

    def execute(self, args):
        if args.version:
            version.print_version()
        else:
            args.parser.print_usage(file=sys.stderr)
