from argparse import ArgumentParser
from logging import getLogger

from .command import Command
from ...config import ClanStatsConfig
from ...data.retrieval.default_data_retriever import get_data_retriever, DataRetrieverType
from ...exceptions import ApplicationError, UserError

log = getLogger(__name__)

class TestErrorsCommand(Command):
    name = "errors"
    help = "Test error handling"

    def configure_arg_parser(self, parser: ArgumentParser, config: ClanStatsConfig) -> None:
        parser.add_argument("--user-error", action="store_true")
        parser.add_argument("--application-error", action="store_true")

    def execute(self, args, config):
        if args.user_error:
            raise UserError("Test user error")
        elif args.application_error:
            raise ApplicationError("Test application error")
        else:
            raise RuntimeError("Test unexpected error")


class TestLoggingCommand(Command):
    name = "logging"
    help = "Test logging configurations"

    def configure_arg_parser(self, parser: ArgumentParser, config: ClanStatsConfig) -> None:
        pass

    def execute(self, args, config: ClanStatsConfig):
        log.debug("A debug message")
        log.info("A info message")
        log.warning("A warning message")
        log.error("A error message")
        log.critical("A critical message")


class RetrieveManifest(Command):
    name = "manifest"
    help = "Pull the manifest"

    def configure_arg_parser(self, parser: ArgumentParser, config: ClanStatsConfig) -> None:
        pass

    def execute(self, args, config: ClanStatsConfig):
        data_retriever = get_data_retriever(DataRetrieverType(args.backend), config)
        data_retriever.get_manifest()


class TestCommand(Command):
    name = "test"
    help = "Internal tests of the tool."
    hidden = True
    subcommands = [TestErrorsCommand(), TestLoggingCommand(), RetrieveManifest()]

    def configure_arg_parser(self, parser: ArgumentParser, config: ClanStatsConfig) -> None:
        pass
