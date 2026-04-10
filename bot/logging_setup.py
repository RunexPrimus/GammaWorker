from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: str, log_level: str = "INFO") -> None:
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | job=%(job_id)s user=%(user_id)s stage=%(stage)s | %(message)s"
    )

    class ContextFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if not hasattr(record, "job_id"):
                record.job_id = None
            if not hasattr(record, "user_id"):
                record.user_id = None
            if not hasattr(record, "stage"):
                record.stage = None
            return True

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root.handlers.clear()

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    stream.addFilter(ContextFilter())
    root.addHandler(stream)

    app_log = RotatingFileHandler(path / "bot.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    app_log.setFormatter(formatter)
    app_log.addFilter(ContextFilter())
    root.addHandler(app_log)

    err_log = RotatingFileHandler(path / "error.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    err_log.setLevel(logging.ERROR)
    err_log.setFormatter(formatter)
    err_log.addFilter(ContextFilter())
    root.addHandler(err_log)
