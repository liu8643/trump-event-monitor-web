from __future__ import annotations

import logging
import traceback
import zipfile
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, timezone

_LOGGER_NAME = "trump_monitor"


def configure_logging(output_dir: str | Path, level: int = logging.DEBUG) -> logging.Logger:
    """Configure persistent runtime/debug/error logs once per process."""
    log_dir = Path(output_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    if getattr(logger, "_trump_monitor_configured", False):
        return logger

    formatter = logging.Formatter(
        "%(asctime)sZ | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    for filename, handler_level in [
        ("runtime.log", logging.INFO),
        ("debug.log", logging.DEBUG),
        ("error.log", logging.ERROR),
    ]:
        handler = RotatingFileHandler(log_dir / filename, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler.setLevel(handler_level)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger._trump_monitor_configured = True  # type: ignore[attr-defined]
    logger.info("logging initialized | log_dir=%s", log_dir)
    return logger


def get_logger(component: str = "core") -> logging.Logger:
    return logging.getLogger(f"{_LOGGER_NAME}.{component}")


def log_exception(logger: logging.Logger, message: str, exc: BaseException) -> None:
    logger.error("%s | %s: %s\n%s", message, type(exc).__name__, exc, traceback.format_exc())


def build_debug_bundle(output_dir: str | Path, run_id: str = "") -> Path:
    """Create a downloadable ZIP containing current and rotated engineering logs."""
    output = Path(output_dir)
    log_dir = output / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = f"_{run_id}" if run_id else ""
    bundle = output / f"debug_logs{suffix}_{stamp}.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        files = sorted(p for p in log_dir.glob("*.log*") if p.is_file())
        if not files:
            placeholder = log_dir / "README.txt"
            placeholder.write_text("No runtime logs have been written yet.\n", encoding="utf-8")
            files = [placeholder]
        for path in files:
            zf.write(path, arcname=f"logs/{path.name}")
    return bundle
