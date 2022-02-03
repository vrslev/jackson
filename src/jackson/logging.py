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

MODE: Literal["server", "client"] | None = None


class RichMarkupStripFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        return Text.from_markup(msg).plain


def get_configured_logger(name: str, prog_name: str):
    short_name = prog_name.ljust(8)[:8]

    assert MODE
    os.makedirs(f"log/{MODE}", exist_ok=True)

    logger = logging.getLogger(name)

    if sys.stdout.isatty():
        print_handler = RichHandler(
            log_time_format=f"[%X] [{short_name}] ", markup=True, rich_tracebacks=True
        )
        logger.addHandler(print_handler)

    file_handler = RotatingFileHandler(
        f"log/{MODE}/{name}.log", maxBytes=5 * 1024 * 1024, backupCount=5
    )
    formatter = RichMarkupStripFormatter(
        "%(asctime)s  %(levelname)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def silent_jack_stream_handler(message: str):
    pass


class JackClientFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if "CheckRes error" in record.msg:
            return False
        if "JackSocketClientChannel read fail" in record.msg:
            return False
        if "Cannot read socket fd = " and "err = Socket is not connected" in record.msg:
            return False
        return super().filter(record)


class JackServerFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if "JackMachSemaphore::Destroy failed to kill semaphore" in record.msg:
            return False
        if "JackMachSemaphoreServer::Execute" in record.msg:
            return False
        return super().filter(record)


class JackTripFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if "WEAK-JACK: initializing" in record.msg:
            return False
        if "WEAK-JACK: OK." in record.msg:
            return False
        if "mThreadPool default maxThreadCount" in record.msg:
            return False
        if "mThreadPool maxThreadCount previously set" in record.msg:
            return False
        return super().filter(record)
