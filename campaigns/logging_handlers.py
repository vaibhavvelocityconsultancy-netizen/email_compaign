import logging
import os
from contextlib import contextmanager
from logging.handlers import TimedRotatingFileHandler


class DatabaseLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.levelno < logging.INFO:
                return
            from django.apps import apps
            from django.db import connection
            from django.db.utils import OperationalError, ProgrammingError

            SystemLog = apps.get_model("campaigns", "SystemLog")
            if SystemLog is None:
                return
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM django_migrations WHERE app = %s LIMIT 1", ["campaigns"])

            tenant = getattr(record, "tenant", None)
            tenant_id = getattr(record, "tenant_id", None)
            if tenant_id in (None, "none", "unknown", ""):
                tenant_id = None
            else:
                try:
                    tenant_id = int(tenant_id)
                except (TypeError, ValueError):
                    tenant_id = None

            message = self.format(record)
            level = record.levelname.upper()
            SystemLog.objects.create(
                level=level[:10],
                logger_name=(record.name or "unknown")[:255],
                module=(record.module or record.pathname.rsplit("\\", 1)[-1].rsplit("/", 1)[-1])[:255],
                message=message[:10000],
                source=(record.funcName or record.pathname)[:255],
                tenant_id=tenant_id,
                is_notification=record.levelno >= logging.ERROR,
            )
        except (OperationalError, ProgrammingError):
            pass
        except Exception:
            self.handleError(record)


class LatestFirstTimedRotatingFileHandler(TimedRotatingFileHandler):
    @contextmanager
    def _file_lock(self):
        lock_path = f"{self.baseFilename}.lock"
        with open(lock_path, "a+b") as lock_file:
            if os.name == "nt":
                import msvcrt

                if os.path.getsize(lock_path) == 0:
                    lock_file.write(b"\0")
                    lock_file.flush()
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            with self._file_lock():
                if self.shouldRollover(record):
                    self.doRollover()

                if not os.path.exists(self.baseFilename):
                    with open(
                        self.baseFilename,
                        "w",
                        encoding=self.encoding,
                        errors=self.errors,
                    ):
                        pass

                formatted_record = f"{self.format(record)}\n"
                with open(
                    self.baseFilename,
                    "r+",
                    encoding=self.encoding,
                    errors=self.errors,
                    newline="",
                ) as log_file:
                    existing_content = log_file.read()
                    log_file.seek(0)
                    log_file.write(formatted_record)
                    log_file.write(existing_content)
                    log_file.truncate()
        except Exception:
            self.handleError(record)
