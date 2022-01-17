from functools import partial

from rich.console import Console
from rich.style import Style


def generate_stream_handlers(proc: str):
    console = Console(log_path=False, log_time_format=f"[%X] [{proc}]")
    return console.log, partial(console.log, style=Style(bold=True))
