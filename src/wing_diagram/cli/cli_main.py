import argparse
import logging
import sys
import traceback
from typing import List

from .commands.root_command import RootCommand
from .exit_codes import ExitCode
from .. import log_config
from ..config import read_config, ClanStatsConfig
from ..exceptions import ApplicationError, UserError, ConfigError

log = logging.getLogger(__name__)


def main() -> int:
    exit_code = interrupt_wrapper(_cli_arguments_excluding_command_name())
    return exit_code.value


def interrupt_wrapper(unparsed_arguments: List[str]) -> ExitCode:
    try:
        return main_with_args(unparsed_arguments)
    except KeyboardInterrupt:
        print("Ctrl-C received: Exiting...", file=sys.stderr)
        return ExitCode.USER_INTERRUPT


def main_with_args(unparsed_arguments: List[str]) -> ExitCode:
    try:
        config = read_config()
        parsed_arguments = _parse_args(unparsed_arguments, config)
    except ConfigError as err:
        print("error with configuration: " + str(err), file=sys.stderr)
        return ExitCode.ARGUMENT_ERROR
    except argparse.ArgumentError as err:
        print("argument parsing error: " + str(err), file=sys.stderr)
        return ExitCode.ARGUMENT_ERROR
    except RuntimeError as err:
        print("application startup error: " + str(err), file=sys.stderr)
        return ExitCode.UNEXPECTED_ERROR

    _configure_logging(parsed_arguments, unparsed_arguments)

    return run_application(parsed_arguments, config)


def run_application(parsed_arguments: argparse.Namespace, config: ClanStatsConfig) -> ExitCode:
    """Run the business logic for the command found in the arguments"""
    try:
        parsed_arguments.command_executable(parsed_arguments, config)
    except UserError as err:
        print("User error: " + err.args[0], file=sys.stderr)
        return ExitCode.USER_ERROR
    except ApplicationError as err:
        print("Application error: " + err.args[0], file=sys.stderr)
        return ExitCode.APPLICATION_ERROR
    except Exception as exception:
        if isinstance(exception, InterruptedError):
            raise exception
        log.exception("Unexpected error!", exc_info=exception)
        for line in traceback.format_exception(exception):
            for l in  line.split("\n"):
                log.debug(l.strip("\n"))

        print("Unexpected error: " + str(exception), file=sys.stderr)
        return ExitCode.UNEXPECTED_ERROR

    return ExitCode.OK


def _configure_logging(args, unparsed_arguments):
    if args.debug:
        log_config.configure_logging(log_config.LogLevel.ON)
    else:
        log_config.configure_logging(log_config.LogLevel.OFF)
    log.info("Unparsed CLI Arguments: %s", unparsed_arguments)
    log.info("Parsed CLI Arguments: %s", args)


def _get_arg_parser(config: ClanStatsConfig) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clan-stats", exit_on_error=False)
    root_command = RootCommand()
    root_command.configure_parsers_and_sub_parsers(parser, config)
    parser.set_defaults(global_parser=parser)

    return parser


def _parse_args(unparsed_arguments: List[str], config: ClanStatsConfig) -> argparse.Namespace:
    arg_parser = _get_arg_parser(config)
    return arg_parser.parse_args(unparsed_arguments)


def _cli_arguments_excluding_command_name():
    return sys.argv[1:]
