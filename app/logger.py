import logging
import sentry_sdk
from typing import Any, Dict


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


class SentryContextFilter(logging.Filter):
    """Enhanced logging filter that adds context to Sentry."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Add structured data to Sentry for error events
        if record.levelno >= logging.ERROR and sentry_sdk.is_initialized():
            try:
                # Extract context from log record
                context_data = self._extract_context_data(record)

                # Add breadcrumb to Sentry for better error tracing
                sentry_sdk.add_breadcrumb(
                    message=record.getMessage(),
                    category="log",
                    level=record.levelname.lower(),
                    data=context_data
                )

                # Set tags for easy filtering in Sentry
                if hasattr(record, 'execution_id') and record.execution_id != "-":
                    sentry_sdk.set_tag("execution_id", record.execution_id)
                if hasattr(record, 'status') and record.status != "-":
                    sentry_sdk.set_tag("status", record.status)

            except Exception as e:
                # Don't let logging errors break the application, but log them for debugging
                logger.debug(f"Failed to add Sentry context: {e}")

        return True

    def _extract_context_data(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Extract relevant context data from log record."""
        context = {}

        # Add execution context if available
        for attr in ['execution_id', 'status', 'started', 'finished', 'ok']:
            if hasattr(record, attr) and getattr(record, attr) != "-":
                context[attr] = getattr(record, attr)

        # Add function and module info
        if hasattr(record, 'funcName'):
            context['function'] = record.funcName
        if hasattr(record, 'module'):
            context['module'] = record.module

        return context
