"""Akilli loglama — stdlib only, zero dep.
1) logs/ var mi kontrol et
2) yoksa olustur
3) tum loglar logs/ icine
4) real-time flush (buffering=1, flush her satir)
5) isim: DD-MM-YYYY - HH.mm.log  (+ latest.log her zaman en guncel)

Kullanim:  from logger import setup_logging  ->  setup_logging()  (idempotent)
"""

import logging
import sys
import json
import os
import uuid
from pathlib import Path
from datetime import datetime
from contextvars import ContextVar

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
DATE_FMT = "%Y-%m-%d %H:%M:%S"
MAX_KEPT = 30  # eski loglari buda (en az bu kadar tut)

_initialized = False
_dated_path: Path | None = None

# Request ID context for correlation
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    """JSON structured log formatter."""
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Add request_id if present
        rid = request_id_var.get()
        if rid:
            log_data["request_id"] = rid
        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in {"name", "msg", "args", "created", "filename", "funcName",
                           "levelname", "levelno", "lineno", "module", "msecs",
                           "message", "pathname", "process", "processName",
                           "relativeCreated", "thread", "threadName", "exc_info",
                           "exc_text", "stack_info", "getMessage"}:
                log_data[key] = value
        return json.dumps(log_data, ensure_ascii=False)


def _dated_name(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return now.strftime("%d-%m-%Y - %H.%M.log")


def _cleanup_latest_suffix():
    """Onceki ' - latest.log' dosyalarini suffix'siz hale getir."""
    for p in LOG_DIR.glob("* - latest.log"):
        target = p.with_name(p.name.replace(" - latest.log", ".log"))
        if not target.exists():
            try:
                p.rename(target)
            except OSError:
                pass


def _prune_old_logs():
    logs = sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime)
    # latest.log'i sayim disinda tut
    dated = [p for p in logs if p.name != "latest.log"]
    if len(dated) > MAX_KEPT:
        for p in dated[: len(dated) - MAX_KEPT]:
            try:
                p.unlink()
            except OSError:
                pass


def setup_logging(level: int = logging.INFO) -> tuple[Path, Path]:
    """Logger'i kur, (dated_path, latest_path) don. Cagirilmazsa no-op degil; ilk cagri kurar."""
    global _initialized, _dated_path
    if _initialized and _dated_path:
        return _dated_path, LOG_DIR / "latest.log"

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_latest_suffix()

    now = datetime.now()
    dated_name = _dated_name(now)
    # Ayni dakika icinde ikinci setup olursa suffix ekle (collision onle)
    dated_path = LOG_DIR / dated_name
    if dated_path.exists():
        dated_path = LOG_DIR / now.strftime("%d-%m-%Y - %H.%M.%S.log")
    latest_path = LOG_DIR / "latest.log"

    # Choose formatter based on env var
    use_json = os.getenv("LOG_FORMAT", "").lower() == "json"
    formatter = JsonFormatter() if use_json else logging.Formatter(LOG_FMT, datefmt=DATE_FMT)

    # Dated file — her sey buraya, line-buffered
    fh_dated = logging.FileHandler(dated_path, encoding="utf-8", delay=False)
    fh_dated.setLevel(level)
    fh_dated.setFormatter(formatter)

    # latest.log — ayni icerigin aynasi (tek handler degil, iki file handler)
    fh_latest = logging.FileHandler(latest_path, encoding="utf-8", mode="w", delay=False)
    fh_latest.setLevel(level)
    fh_latest.setFormatter(formatter)

    # Console — stdout
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    # Tekrar setup olmasin diye onceki handler'lari temizle (uvicorn reload'da duplicate onle)
    # Sadece bizim eklediklerimizi degil, hepsini resetle — sonra tekrar ekle
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(fh_dated)
    root.addHandler(fh_latest)
    root.addHandler(ch)

    # Uvicorn / fastapi loglari da root'a gitsin
    for lname in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        lg = logging.getLogger(lname)
        lg.handlers.clear()
        lg.propagate = True
        lg.setLevel(level)

    _initialized = True
    _dated_path = dated_path
    _prune_old_logs()

    # Ilk satirlar — dosya olustu mu belli olsun
    logging.getLogger("vitanet.logger").info("Log started — dated=%s latest=%s format=%s", dated_path.name, latest_path.name, "json" if use_json else "text")
    return dated_path, latest_path


def get_log_dir() -> Path:
    return LOG_DIR


def get_dated_path() -> Path | None:
    return _dated_path


def set_request_id(rid: str | None = None) -> str:
    """Set request ID in context var, return the ID used."""
    if rid is None:
        rid = uuid.uuid4().hex[:12]
    request_id_var.set(rid)
    return rid


def get_request_id() -> str | None:
    """Get current request ID from context var."""
    return request_id_var.get()


def clear_request_id():
    """Clear request ID from context var."""
    request_id_var.set(None)
