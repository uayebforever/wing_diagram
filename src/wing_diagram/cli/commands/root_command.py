import sys
from argparse import ArgumentParser

from . import version
from .clan_command import ClanCommand
from .command import Command
from .player_command import PlayerCommand
from .test_command import TestCommand
from .version import VersionCommand
from ...config import ClanStatsConfig
from ...data.retrieval.default_data_retriever import DataRetrieverType
from ...util.itertools import first


class RootCommand(Command):
    name = "constellation"
    help = "A tool to manage constellations of nebulae sandboxes."
    subcommands = [ClanCommand(), VersionCommand(), TestCommand(), PlayerCommand()]

    def configure_arg_parser(self, parser: ArgumentParser, config: ClanStatsConfig) -> None:
        parser.add_argument(
            "--version",
            action='store_true',
            help="Print version information and exit")

        parser.add_argument('--backend',
                            choices=list(DataRetrieverType),
                            default=first(DataRetrieverType),
                            help="Which python library to use to access the Bungie API")

    def execute(self, args, config):
        if args.version:
            version.print_version()
        else:
            args.parser.print_usage(file=sys.stderr)
