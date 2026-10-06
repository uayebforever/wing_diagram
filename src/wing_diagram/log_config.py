import enum
import logging
import logging.config
from logging import LogRecord
from pathlib import Path

from . import __package_name__

PACKAGE_DIRECTORY = Path(__file__).parent


class PackageLogFormatter(logging.Formatter):

    def format(self, record: LogRecord) -> str:
        path = Path(record.pathname).relative_to(PACKAGE_DIRECTORY)
        header = f"{path}::{record.funcName}({record.lineno})"
        trunc_header = header if len(header) < 50 else "..." + header[-47:]
        return f"{record.levelname[0]} {trunc_header:<50s} {record.getMessage()}"


DEFAULT_LOGGING_CONFIG = {
    "version": 1,
    "formatters": {
        "default": {
            "format": "LOG: %(message)s",
        },
        "package_formatter": {
            "()": "wing_diagram.log_config.PackageLogFormatter"
        }
    },
    "handlers": {
        "stderr": {
            "class": "logging.StreamHandler",
            "formatter": "package_formatter",
            "stream": "ext://sys.stderr",
            # TODO: Turned off because it interfers with interactive interface. Should just disable if interactive.
            "level": "CRITICAL"
        },
    },
    "loggers": {
        __package_name__: {
            "level": "NOTSET",
            "handlers": ["stderr"],
            "propagate": False,
        },
    },
}

PACKAGE_LOGGERS = (__package_name__,)


class LogLevel(enum.Enum):
    OFF = logging.CRITICAL + 1
    ON = logging.DEBUG


def configure_logging(level: LogLevel) -> None:
    logging.config.dictConfig(DEFAULT_LOGGING_CONFIG)

    for logger_name in PACKAGE_LOGGERS:
        logger = logging.getLogger(logger_name)
        logger.setLevel(level.value)
        if level is LogLevel.ON:
            file_handler_path = Path(".").joinpath("clan-stats.log")
            file_handler = logging.FileHandler(file_handler_path)
            file_handler.setFormatter(PackageLogFormatter())
            file_handler.setLevel(level.value)
            logger.addHandler(file_handler)
            logger.debug("Logging to file %s", file_handler_path)

    log = logging.getLogger(__name__)
    log.debug("Logging has been configured.")
