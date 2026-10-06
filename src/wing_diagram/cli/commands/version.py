from argparse import ArgumentParser

from wing_diagram import __version__ as package_version
from .command import Command


class VersionCommand(Command):
    name = "version"
    help = "Print version information"

    def configure_arg_parser(self, parser: ArgumentParser) -> None:
        # No arguments
        pass

    def execute(self, args):
        print_version()


def print_version():
    print(f"wing_diagram version: {package_version}")
