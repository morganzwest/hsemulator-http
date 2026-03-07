import logging
import re
import subprocess
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)


class SourceCodeConversionError(Exception):
    """Base exception for source code conversion errors"""
    pass


class MainNotFoundError(SourceCodeConversionError):
    """Raised when no main(event) function is found in source code"""
    pass


class InvalidSourceError(SourceCodeConversionError):
    """Raised when source code is invalid or empty"""
    pass


class LintError(SourceCodeConversionError):
    """Raised when converted source code fails linting"""
    pass


class SourceCodeConversionService:
    """
    Service for converting Python source code to include telemetry tracking.
    
    This service wraps user Python code with telemetry helper functions
    and decorates the main(event) entrypoint with @telemetry_track().
    """
    
    # Default telemetry template
    DEFAULT_TELEMETRY_TEMPLATE = '''import sys
import io
import time
import json
import traceback
import uuid
import hmac
import hashlib
import requests

SECRET = b"{secret}"
URL = "https://hsemulator-telemetry-712737660959.europe-west1.run.app/v1/ingest"

VALID_TYPES = {{
    "ExecutionStarted",
    "ExecutionCompleted", 
    "ExecutionFailed",
    "Stdout",
    "Return",
}}

class _TelemetryBuffer(io.StringIO):
    def __init__(self):
        super().__init__()
        self._chunks = []

    def write(self, s):
        self._chunks.append(s)
        return super().write(s)

    def dump(self):
        return "".join(self._chunks)


def _build_signature(portal_id: int, action_id: str, workflow_id: int, timestamp: int) -> str:
    canonical = f"{{portal_id}}.{{action_id}}.{{workflow_id}}.{{timestamp}}"
    return hmac.new(SECRET, canonical.encode(), hashlib.sha256).hexdigest()


def _send_telemetry(portal_id, action_id, workflow_id, execution_uuid, t_type, message=None):
    if t_type not in VALID_TYPES:
        return

    timestamp = int(time.time() * 1000)  # Millisecond precision

    payload = {{
        "portal_id": portal_id,
        "action_id": action_id,
        "workflow_id": workflow_id,
        "execution_uuid": execution_uuid,
        "timestamp": timestamp,
        "type": t_type,
        "message": message,
        "environment": "production",
    }}

    body = json.dumps(payload, separators=(",", ":"))

    signature = _build_signature(
        portal_id,
        action_id,
        workflow_id,
        timestamp,
    )

    headers = {{
        "Content-Type": "application/json",
        "X-Signature": signature,
        "X-Timestamp": str(timestamp),
    }}

    try:
        # Fire-and-forget: minimal timeout to avoid blocking
        requests.post(URL, data=body, headers=headers, timeout=0.1, stream=True)
    except Exception:
        pass  # Silently ignore - telemetry shouldn't break user code


def telemetry_track(action_id: str, workflow_id: int):
    """Decorator to add telemetry tracking to any function"""
    def decorator(fn):
        def wrapper(event):
            portal_id = event.get("origin", {{}}).get("portalId", 12345678)
            execution_uuid = str(uuid.uuid4())

            _send_telemetry(portal_id, action_id, workflow_id, execution_uuid, "ExecutionStarted", json.dumps(event))

            stdout_buf = _TelemetryBuffer()
            stderr_buf = _TelemetryBuffer()

            old_out, old_err = sys.stdout, sys.stderr
            sys.stdout, sys.stderr = stdout_buf, stderr_buf

            result = None
            error = None
            exc = None

            try:
                result = fn(event)
                success = True
            except Exception as e:
                success = False
                exc = e
                error = {{
                    "type": type(e).__name__,
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                }}
            finally:
                sys.stdout, sys.stderr = old_out, old_err

            stdout_value = stdout_buf.dump()
            stderr_value = stderr_buf.dump()

            if stdout_value:
                _send_telemetry(portal_id, action_id, workflow_id, execution_uuid, "Stdout", stdout_value)

            if stderr_value:
                _send_telemetry(portal_id, action_id, workflow_id, execution_uuid, "Stdout", stderr_value)

            if success:
                _send_telemetry(portal_id, action_id, workflow_id, execution_uuid, "Return", str(result))
                _send_telemetry(portal_id, action_id, workflow_id, execution_uuid, "ExecutionCompleted")
                return result

            _send_telemetry(portal_id, action_id, workflow_id, execution_uuid, "ExecutionFailed", json.dumps(error))

            raise exc
        
        return wrapper
    return decorator

# USER CODE BELOW
'''

    def __init__(self):
        self.warnings: List[str] = []
    
    def convert_source_code(
        self,
        source_code: str,
        action_id: Optional[str] = None,
        workflow_id: Optional[int] = None,
        secret: Optional[str] = None,
        skip_lint: bool = False
    ) -> Tuple[str, List[str]]:
        """
        Convert Python source code to include telemetry tracking.
        
        Args:
            source_code: Raw Python source code
            action_id: Optional action ID for telemetry
            workflow_id: Optional workflow ID for telemetry  
            secret: Optional secret for telemetry
            skip_lint: Skip linting validation (default: False)
            
        Returns:
            Tuple of (converted_source_code, warnings)
            
        Raises:
            InvalidSourceError: If source code is invalid
            MainNotFoundError: If no main(event) function found
            LintError: If converted code fails linting validation
        """
        self.warnings = []
        
        # Validate input
        if not source_code or not source_code.strip():
            raise InvalidSourceError("Source code cannot be empty")
        
        # Set defaults
        action_id = action_id or "default-action-id"
        workflow_id = workflow_id or 0
        secret = secret or "default-secret"
        
        # Check if telemetry already exists
        telemetry_already_present = self._has_telemetry(source_code)
        if telemetry_already_present:
            self.warnings.append("Telemetry code already detected in source")
        
        # Find main function
        main_match = self._find_main_function(source_code)
        if not main_match:
            raise MainNotFoundError("No main(event) or async def main(event) function found")
        
        # Process the source code
        converted_code = self._process_source_code(
            source_code,
            action_id,
            workflow_id,
            secret,
            main_match,
            telemetry_already_present
        )
        
        # Run lint check if not skipped
        if not skip_lint:
            lint_passed, lint_errors = self._lint_source_code(converted_code)
            if not lint_passed:
                raise LintError(f"Converted code failed linting: {'; '.join(lint_errors)}")
        
        return converted_code, self.warnings
    
    def _has_telemetry(self, source_code: str) -> bool:
        """Check if telemetry code already exists in source"""
        telemetry_indicators = [
            r'def telemetry_track',
            r'@telemetry_track',
            r'SECRET\s*=',
            r'# USER CODE BELOW'
        ]
        
        for indicator in telemetry_indicators:
            if re.search(indicator, source_code, re.MULTILINE):
                return True
        return False
    
    def _find_main_function(self, source_code: str) -> Optional[re.Match]:
        """Find the main(event) function definition"""
        # Look for both sync and async main functions
        main_patterns = [
            r'^(\s*)def\s+main\s*\(\s*event\s*\)\s*:',
            r'^(\s*)async\s+def\s+main\s*\(\s*event\s*\s*\)\s*:'
        ]
        
        for pattern in main_patterns:
            match = re.search(pattern, source_code, re.MULTILINE)
            if match:
                return match
        return None
    
    def _process_source_code(
        self,
        source_code: str,
        action_id: str,
        workflow_id: int,
        secret: str,
        main_match: re.Match,
        telemetry_already_present: bool
    ) -> str:
        """Process source code to add telemetry"""
        
        if telemetry_already_present:
            # If telemetry already exists, just ensure decorator is present
            return self._ensure_decorator_exists(source_code, action_id, workflow_id, main_match)
        
        # Add telemetry template at the top
        telemetry_template = self.DEFAULT_TELEMETRY_TEMPLATE.format(
            secret=secret,
            action_id=action_id,
            workflow_id=workflow_id
        )
        
        # Add decorator to main function
        lines = source_code.split('\n')
        main_line_num = source_code[:main_match.start()].count('\n')
        indent = main_match.group(1) if main_match.group(1) else ""
        
        # Insert decorator before main function
        decorator_line = f"{indent}@telemetry_track(action_id=\"{action_id}\", workflow_id={workflow_id})"
        lines.insert(main_line_num, decorator_line)
        
        # Combine telemetry template with modified user code
        converted_code = telemetry_template + '\n' + '\n'.join(lines)
        
        return converted_code
    
    def _ensure_decorator_exists(
        self,
        source_code: str,
        action_id: str,
        workflow_id: int,
        main_match: re.Match
    ) -> str:
        """Ensure @telemetry_track decorator exists above main function"""
        
        # Check if decorator already exists above main
        lines = source_code.split('\n')
        main_line_num = source_code[:main_match.start()].count('\n')
        
        # Look for decorator in lines before main
        decorator_found = False
        for i in range(max(0, main_line_num - 5), main_line_num):
            if '@telemetry_track' in lines[i]:
                decorator_found = True
                # Update existing decorator with new parameters
                lines[i] = f"    @telemetry_track(action_id=\"{action_id}\", workflow_id={workflow_id})"
                break
        
        if not decorator_found:
            # Add decorator
            indent = main_match.group(1) if main_match.group(1) else ""
            decorator_line = f"{indent}@telemetry_track(action_id=\"{action_id}\", workflow_id={workflow_id})"
            lines.insert(main_line_num, decorator_line)
            self.warnings.append("Added telemetry decorator to existing main function")
        
        return '\n'.join(lines)
    
    def _lint_source_code(self, source_code: str) -> Tuple[bool, List[str]]:
        """
        Run linting on Python source code using ruff.
        
        Args:
            source_code: Python source code to lint
            
        Returns:
            Tuple of (passed, error_messages)
        """
        try:
            # Run ruff check on the source code
            result = subprocess.run(
                ['ruff', 'check', '--output-format', 'json', '-'],
                input=source_code,
                text=True,
                capture_output=True,
                timeout=30  # 30 second timeout
            )
            
            if result.returncode == 0:
                return True, []
            else:
                # Parse ruff JSON output for error messages
                import json
                try:
                    ruff_output = json.loads(result.stdout)
                    error_messages = [
                        f"Line {error.get('location', {}).get('row', '?')}: {error.get('message', 'Unknown error')}"
                        for error in ruff_output
                    ]
                    return False, error_messages
                except json.JSONDecodeError:
                    # Fallback to stderr if JSON parsing fails
                    return False, [result.stderr.strip() or "Linting failed with unknown error"]
                    
        except subprocess.TimeoutExpired:
            logger.error("Linting timed out")
            return False, ["Linting timed out after 30 seconds"]
        except FileNotFoundError:
            logger.warning("Ruff not found, skipping linting")
            return True, []  # Pass if ruff is not available
        except Exception as e:
            logger.error(f"Linting error: {e}")
            return False, [f"Linting error: {str(e)}"]
    
    def lint_python_code(self, source_code: str) -> Tuple[bool, List[str], List[str]]:
        """
        Standalone Python code linting service.
        
        Args:
            source_code: Python source code to lint
            
        Returns:
            Tuple of (passed, errors, warnings)
        """
        # Validate input
        if not source_code or not source_code.strip():
            raise InvalidSourceError("Source code cannot be empty")
        
        # Run linting
        passed, errors = self._lint_source_code(source_code)
        
        # For now, we don't distinguish between errors and warnings in ruff output
        # All linting issues are treated as errors for simplicity
        warnings = []
        
        return passed, errors, warnings
