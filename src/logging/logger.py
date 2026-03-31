"""
创建全局日志对象。

Author: Gongmin Wei
Date: 2026-03-31
"""
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler
from rich.logging import RichHandler
from rich.console import Console
from rich.theme import Theme

def get_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent

def setup_global_logging():
    """
    配置根Logger。
    """
    root_dir = get_root()
    log_dir = root_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "educlaw.log"

    root_logger = logging.getLogger("")
    root_logger.setLevel(logging.INFO)

    if root_logger.handlers:
        root_logger.handlers.clear()

    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )
    file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    file_handler.setFormatter(file_formatter)

    custom_theme = Theme({
        "logging.level.debug": "dim white",
        "logging.level.info": "bold cyan",
        "logging.level.warning": "bright_yellow",
        "logging.level.error": "orange1",
        "logging.level.critical": "reverse white",
    })
    console = Console(stderr=True, theme=custom_theme)
    console_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        markup=True,
        log_time_format="[%X]",
        rich_tracebacks=True
    )

    console_formatter = logging.Formatter("[%(name)s] %(message)s")
    console_handler.setFormatter(console_formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

setup_global_logging()

def get_logger(module_name: str):
    return logging.getLogger(module_name.upper())

logger = get_logger("CORE")