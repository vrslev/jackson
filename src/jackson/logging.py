import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Literal

import rich
import rich.traceback
from rich.logging import RichHandler
from rich.text import Text

rich.traceback.install(show_locals=True)
logging.basicConfig(level=logging.INFO, handlers=[], datefmt="%m/%d/%Y %I:%M:%S %p")

_logger_name_to_prog_name: dict[str, str] = {}


def get_logger(name: str, prog_name: str):
    _logger_name_to_prog_name[name] = prog_name.ljust(8)[:8]
    return logging.getLogger(name)


class _RichMarkupStripFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        return Text.from_markup(msg).plain


_Mode = Literal["server", "client", None]


def _configure_logger(mode: _Mode, logger: logging.Logger, prog_name: str):
    if sys.stdout.isatty():
        print_handler = RichHandler(
            log_time_format=f"[%X] [{prog_name}] ", markup=True, rich_tracebacks=True
        )
        logger.addHandler(print_handler)

    if not mode:
        return

    os.makedirs(f"log/{mode}", exist_ok=True)
    file_handler = RotatingFileHandler(
        f"log/{mode}/{logger.name}.log", maxBytes=5 * 1024 * 1024, backupCount=5
    )
    formatter = _RichMarkupStripFormatter(
        "%(asctime)s  %(levelname)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def configure_loggers(mode: _Mode):
    for name, prog_name in _logger_name_to_prog_name.items():
        logger = logging.getLogger(name)
        _configure_logger(mode, logger, prog_name)


def silent_jack_stream_handler(message: str) -> None:
    pass


class MessageFilter(logging.Filter):
    messages: set[str]

    def filter(self, record: logging.LogRecord) -> bool:
        for msg in self.messages:
            if msg in record.msg:
                return False
        return super().filter(record)


class JackClientFilter(MessageFilter):
    messages = {
        "CheckRes error",
        "JackSocketClientChannel read fail",
        "Cannot read socket fd = ",
    }


class JackServerFilter(MessageFilter):
    messages = {
        "JackMachSemaphore::Destroy failed to kill semaphore",
        "JackMachSemaphoreServer::Execute",
        "self-connect-mode is",
        "Input channel = ",
        "JACK output port = ",
        "CoreAudio driver is running...",
    }


class JackTripFilter(MessageFilter):
    messages = {
        "WEAK-JACK: initializing",
        "WEAK-JACK: OK.",
        "mThreadPool default maxThreadCount",
        "mThreadPool maxThreadCount previously set",
    }

    def filter(self, record: logging.LogRecord) -> bool:
        if all(c == "-" for c in record.msg):
            return False

        if all(c == "=" for c in record.msg):
            return False

        return super().filter(record)
