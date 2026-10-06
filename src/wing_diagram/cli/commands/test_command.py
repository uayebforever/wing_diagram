from argparse import ArgumentParser
from logging import getLogger

from .command import Command
from ...exceptions import ApplicationError, UserError

log = getLogger(__name__)

class TestErrorsCommand(Command):
    name = "errors"
    help = "Test error handling"

    def configure_arg_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument("--user-error", action="store_true")
        parser.add_argument("--application-error", action="store_true")

    def execute(self, args):
        if args.user_error:
            raise UserError("Test user error")
        elif args.application_error:
            raise ApplicationError("Test application error")
        else:
            raise RuntimeError("Test unexpected error")


class TestLoggingCommand(Command):
    name = "logging"
    help = "Test logging configurations"

    def configure_arg_parser(self, parser: ArgumentParser) -> None:
        pass

    def execute(self, args):
        log.debug("A debug message")
        log.info("A info message")
        log.warning("A warning message")
        log.error("A error message")
        log.critical("A critical message")


class TestCommand(Command):
    name = "test"
    help = "Internal tests of the tool."
    hidden = True
    subcommands = [TestErrorsCommand(), TestLoggingCommand()]

    def configure_arg_parser(self, parser: ArgumentParser) -> None:
        pass
