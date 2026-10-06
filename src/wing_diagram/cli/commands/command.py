import sys
from abc import ABC, abstractmethod
from argparse import ArgumentParser
from typing import List

from wing_diagram.config import ClanStatsConfig


class Command(ABC):
    name: str  # Naem of this command on the command line.
    help: str  # Help message for the usage and help describing this command.
    subcommands: List['Command'] = []

    def configure_parsers_and_sub_parsers(self, parser: ArgumentParser, config: ClanStatsConfig) -> None:
        """Configure given argument parser for this command and all associated sub commands."""
        self.configure_arg_parser(parser, config)
        self._add_debug_argument(parser)
        parser.set_defaults(command_executable=self.execute)
        parser.set_defaults(parser=parser)

        self.add_subcommand_parsers(parser, config)

    def add_subcommand_parsers(self, parser: ArgumentParser, config: ClanStatsConfig):
        if len(self.subcommands) == 0:
            return
        subparsers = parser.add_subparsers()
        for sub_command in self.subcommands:
            subparser = subparsers.add_parser(
                name=sub_command.name,
                help=sub_command.help
            )
            sub_command.configure_parsers_and_sub_parsers(subparser, config)

    @abstractmethod
    def configure_arg_parser(self, parser: ArgumentParser, config: ClanStatsConfig) -> None:
        """Override this method to define arguments of this command.
        :param config:
        """
        raise NotImplementedError()

    def execute(self, args, config: ClanStatsConfig):
        """Business logic of this command."""
        args.parser.print_usage(file=sys.stderr)

    def _add_debug_argument(self, parser: ArgumentParser):
        parser.add_argument("--debug",
                            action="store_true",
                            help="Enable debug logging to the console.")
