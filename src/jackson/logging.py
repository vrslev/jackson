import logging

import rich.traceback
from rich.logging import RichHandler

rich.traceback.install(show_locals=True)
logging.basicConfig(level=logging.INFO, handlers=[])


def get_configured_logger(name: str, prog_name: str):
    logger = logging.getLogger(name)
    short_name = prog_name.ljust(8)[:8]
    handler = RichHandler(
        log_time_format=f"[%X] [{short_name}] ", markup=True, rich_tracebacks=True
    )
    logger.addHandler(handler)
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
