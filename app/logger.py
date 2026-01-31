import logging


class ExecutionContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Ensure required structured fields always exist
        if not hasattr(record, "execution_id"):
            record.execution_id = "-"
        if not hasattr(record, "status"):
            record.status = "-"
        if not hasattr(record, "started"):
            record.started = "-"
        if not hasattr(record, "finished"):
            record.finished = "-"
        if not hasattr(record, "ok"):
            record.ok = "-"
        return True
