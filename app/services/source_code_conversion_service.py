import logging
import re
import subprocess
import json
from typing import Optional, List, Tuple, Literal

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
    Service for converting Python and JavaScript source code to include telemetry tracking.
    
    This service wraps user code with telemetry helper functions
    and decorates the main(event) entrypoint with appropriate telemetry tracking.
    Supports both Python (@telemetry_track decorator) and JavaScript (function wrapper).
    """
    
    # Default telemetry templates
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
URL = "https://telemetry.novocode.novocy.com/v1/ingest"

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

    DEFAULT_JAVASCRIPT_TELEMETRY_TEMPLATE = '''const crypto = require("crypto");
const https = require("https");
const { randomUUID } = require("crypto");

const SECRET = "{secret}";

const VALID_TYPES = new Set([
    "ExecutionStarted",
    "ExecutionCompleted",
    "ExecutionFailed",
    "Stdout",
    "Return",
]);

class TelemetryBuffer {
    constructor() {
        this.chunks = [];
    }

    write(s) {
        this.chunks.push(s);
    }

    dump() {
        return this.chunks.join("");
    }
}

function buildSignature(portalId, actionId, workflowId, timestamp) {
    const canonical = `${String(portalId)}.${String(actionId)}.${String(workflowId)}.${String(timestamp)}`;

    return crypto
        .createHmac("sha256", SECRET)
        .update(canonical)
        .digest("hex");
}

function sendTelemetry(portalId, actionId, workflowId, executionUuid, tType, message = null) {
    if (!VALID_TYPES.has(tType)) {
        return Promise.resolve({ skipped: true, reason: "invalid_type" });
    }

    const timestamp = Date.now();

    const payload = {
        portal_id: String(portalId),
        action_id: String(actionId),
        workflow_id: String(workflowId),
        execution_uuid: executionUuid,
        timestamp,
        type: tType,
        message,
        environment: "production",
    };

    const body = JSON.stringify(payload);

    const signature = buildSignature(
        payload.portal_id,
        payload.action_id,
        payload.workflow_id,
        timestamp
    );

    const options = {
        hostname: "telemetry.novocode.novocy.com",
        port: 443,
        path: "/v1/ingest",
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Content-Length": Buffer.byteLength(body),
            "X-Signature": signature,
            "X-Timestamp": String(timestamp),
        },
    };

    return new Promise((resolve, reject) => {
        try {
            const req = https.request(options, (res) => {
                res.on("data", () => {});
                res.on("end", () => {
                    resolve({ ok: true });
                });
            });

            req.setTimeout(5000, () => {
                req.destroy();
                resolve({ timeout: true });
            });

            req.on("error", () => {
                resolve({ error: true });
            });

            req.write(body);
            req.end();
        } catch {
            resolve({ error: true });
        }
    });
}

function fireAndForget(...args) {
    try {
        sendTelemetry(...args).catch(() => {});
    } catch {
        // swallow all errors
    }
}

async function wrapFunctionWithTelemetry(originalFn, event, actionId, workflowId) {
    const portalId = event?.origin?.portalId || 12345678;
    const executionUuid = randomUUID();

    fireAndForget(
        portalId,
        actionId,
        workflowId,
        executionUuid,
        "ExecutionStarted",
        JSON.stringify(event)
    );

    const stdoutBuf = new TelemetryBuffer();
    const stderrBuf = new TelemetryBuffer();

    const originalConsoleLog = console.log;
    const originalConsoleError = console.error;

    console.log = (...args) => {
        stdoutBuf.write(args.join(" ") + "\\n");
        originalConsoleLog.apply(console, args);
    };

    console.error = (...args) => {
        stderrBuf.write(args.join(" ") + "\\n");
        originalConsoleError.apply(console, args);
    };

    let result = null;
    let originalError = null;
    let serializedError = null;
    let success = false;

    try {
        result = await originalFn(event);
        success = true;
    } catch (e) {
        originalError = e;

        serializedError = {
            type: e?.constructor?.name || "Error",
            message: e?.message || String(e),
            stack: e?.stack || null,
        };
    } finally {
        console.log = originalConsoleLog;
        console.error = originalConsoleError;
    }

    const stdoutValue = stdoutBuf.dump();
    const stderrValue = stderrBuf.dump();

    const combinedOutput = stdoutValue + stderrValue;

    if (combinedOutput) {
        fireAndForget(
            portalId,
            actionId,
            workflowId,
            executionUuid,
            "Stdout",
            combinedOutput
        );
    }

    if (success) {
        fireAndForget(
            portalId,
            actionId,
            workflowId,
            executionUuid,
            "Return",
            JSON.stringify(result)
        );

        fireAndForget(
            portalId,
            actionId,
            workflowId,
            executionUuid,
            "ExecutionCompleted",
            null
        );

        return result;
    }

    fireAndForget(
        portalId,
        actionId,
        workflowId,
        executionUuid,
        "ExecutionFailed",
        JSON.stringify(serializedError)
    );

    throw originalError;
}

function createTelemetryWrapper(actionId, workflowId) {
    return (originalFn) => {
        return async (event) => {
            return await wrapFunctionWithTelemetry(originalFn, event, actionId, workflowId);
        };
    };
}

// USER CODE BELOW
'''

    def __init__(self):
        self.warnings: List[str] = []
    
    def _detect_language(self, source_code: str) -> Literal["python", "javascript"]:
        """
        Detect whether the source code is Python or JavaScript.
        
        Args:
            source_code: Source code to analyze
            
        Returns:
            "python" or "javascript"
        """
        # JavaScript indicators
        js_patterns = [
            r'export\s+async\s+function\s+main\s*\(',
            r'export\s+function\s+main\s*\(',
            r'import\s+.*\s+from\s+["\'].*["\']',
            r'const\s+\w+\s*=',
            r'let\s+\w+\s*=',
            r'console\.(log|error)',
            # CommonJS patterns
            r'exports\.',
            r'module\.exports',
            r'require\(',
        ]
        
        # Python indicators
        py_patterns = [
            r'def\s+main\s*\(',
            r'async\s+def\s+main\s*\(',
            r'import\s+\w+',
            r'from\s+\w+\s+import',
            r'print\s*\(',
        ]
        
        js_score = 0
        py_score = 0
        
        for pattern in js_patterns:
            if re.search(pattern, source_code, re.MULTILINE | re.IGNORECASE):
                js_score += 1
        
        for pattern in py_patterns:
            if re.search(pattern, source_code, re.MULTILINE | re.IGNORECASE):
                py_score += 1
        
        # If scores are equal or both zero, default to Python for backward compatibility
        return "javascript" if js_score > py_score else "python"
    
    def convert_source_code(
        self,
        source_code: str,
        action_id: Optional[str] = None,
        workflow_id: Optional[int] = None,
        secret: Optional[str] = None,
        skip_lint: bool = False
    ) -> Tuple[str, List[str]]:
        """
        Convert Python or JavaScript source code to include telemetry tracking.
        
        Args:
            source_code: Raw Python or JavaScript source code
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
        
        # Detect language
        language = self._detect_language(source_code)
        
        # Set defaults
        action_id = action_id or "default-action-id"
        workflow_id = workflow_id or 0
        secret = secret or "default-secret"
        
        # Route to appropriate processor
        if language == "javascript":
            return self._convert_javascript_source_code(
                source_code, action_id, workflow_id, secret, skip_lint
            )
        else:  # Python
            return self._convert_python_source_code(
                source_code, action_id, workflow_id, secret, skip_lint
            )
    
    def _convert_python_source_code(
        self,
        source_code: str,
        action_id: str,
        workflow_id: int,
        secret: str,
        skip_lint: bool
    ) -> Tuple[str, List[str]]:
        """Convert Python source code with telemetry"""
        # Check if telemetry already exists
        telemetry_already_present = self._has_python_telemetry(source_code)
        if telemetry_already_present:
            self.warnings.append("Telemetry code already detected in source")
        
        # Find main function
        main_match = self._find_python_main_function(source_code)
        if not main_match:
            raise MainNotFoundError("No main(event) or async def main(event) function found")
        
        # Process the source code
        converted_code = self._process_python_source_code(
            source_code,
            action_id,
            workflow_id,
            secret,
            main_match,
            telemetry_already_present
        )
        
        # Run lint check if not skipped
        if not skip_lint:
            lint_passed, lint_errors = self._lint_python_source_code(converted_code)
            if not lint_passed:
                raise LintError(f"Converted code failed linting: {'; '.join(lint_errors)}")
        
        return converted_code, self.warnings
    
    def _convert_javascript_source_code(
        self,
        source_code: str,
        action_id: str,
        workflow_id: int,
        secret: str,
        skip_lint: bool
    ) -> Tuple[str, List[str]]:
        """Convert JavaScript source code with telemetry"""
        # Check if telemetry already exists
        telemetry_already_present = self._has_javascript_telemetry(source_code)
        if telemetry_already_present:
            self.warnings.append("Telemetry code already detected in source")
        
        # Find main function
        main_match = self._find_javascript_main_function(source_code)
        if not main_match:
            raise MainNotFoundError("No export async function main(event) or export function main(event) found")
        
        # Process the source code
        converted_code = self._process_javascript_source_code(
            source_code,
            action_id,
            workflow_id,
            secret,
            main_match,
            telemetry_already_present
        )
        
        # Run lint check if not skipped
        if not skip_lint:
            lint_passed, lint_errors = self._lint_javascript_source_code(converted_code)
            if not lint_passed:
                raise LintError(f"Converted code failed linting: {'; '.join(lint_errors)}")
        
        return converted_code, self.warnings
    
    def _has_python_telemetry(self, source_code: str) -> bool:
        """Check if Python telemetry code already exists in source"""
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
    
    def _has_javascript_telemetry(self, source_code: str) -> bool:
        """Check if JavaScript telemetry code already exists in source"""
        telemetry_indicators = [
            r'function telemetryTrack',
            r'@telemetryTrack',
            r'const SECRET\s*=',
            r'// USER CODE BELOW',
            r'TelemetryBuffer',
            r'sendTelemetry'
        ]
        
        for indicator in telemetry_indicators:
            if re.search(indicator, source_code, re.MULTILINE | re.IGNORECASE):
                return True
        return False
    
    def _find_python_main_function(self, source_code: str) -> Optional[re.Match]:
        """Find the Python main(event) function definition"""
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
    
    def _find_javascript_main_function(self, source_code: str) -> Optional[re.Match]:
        """Find the JavaScript main function definition"""
        # Look for both ES6 exports and CommonJS exports, sync and async
        main_patterns = [
            # ES6 exports
            r'^(\s*)export\s+async\s+function\s+main\s*\(\s*event\s*\)\s*{{?',
            r'^(\s*)export\s+function\s+main\s*\(\s*event\s*\)\s*{{?',
            # CommonJS exports
            r'^(\s*)exports\.main\s*=\s*async\s*\(?\s*event\s*\)?\s*=>',
            r'^(\s*)exports\.main\s*=\s*\(?\s*event\s*\)?\s*=>',
            r'^(\s*)module\.exports\s*=\s*async\s*\(?\s*event\s*\)?\s*=>',
            r'^(\s*)module\.exports\s*=\s*\(?\s*event\s*\)?\s*=>',
            # Function assignment
            r'^(\s*)exports\.main\s*=\s*async\s+function\s*\(?\s*event\s*\)?',
            r'^(\s*)exports\.main\s*=\s*function\s*\(?\s*event\s*\)?',
            r'^(\s*)module\.exports\s*=\s*async\s+function\s*\(?\s*event\s*\)?',
            r'^(\s*)module\.exports\s*=\s*function\s*\(?\s*event\s*\)?'
        ]
        
        for pattern in main_patterns:
            match = re.search(pattern, source_code, re.MULTILINE)
            if match:
                return match
        return None
    
    def _process_python_source_code(
        self,
        source_code: str,
        action_id: str,
        workflow_id: int,
        secret: str,
        main_match: re.Match,
        telemetry_already_present: bool
    ) -> str:
        """Process Python source code to add telemetry"""
        
        if telemetry_already_present:
            # If telemetry already exists, just ensure decorator is present
            return self._ensure_python_decorator_exists(source_code, action_id, workflow_id, main_match)
        
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
    
    def _process_javascript_source_code(
        self,
        source_code: str,
        action_id: str,
        workflow_id: int,
        secret: str,
        main_match: re.Match,
        telemetry_already_present: bool
    ) -> str:
        """Process JavaScript source code to add telemetry"""
        
        if telemetry_already_present:
            # If telemetry already exists, just ensure decorator is present
            return self._ensure_javascript_decorator_exists(source_code, action_id, workflow_id, main_match)
        
        # Add telemetry template at the top
        telemetry_template = self.DEFAULT_JAVASCRIPT_TELEMETRY_TEMPLATE
        telemetry_template = telemetry_template.replace("{secret}", secret)
        telemetry_template = telemetry_template.replace("{action_id}", action_id)
        telemetry_template = telemetry_template.replace("{workflow_id}", str(workflow_id))
        telemetry_template = telemetry_template.replace("{{ randomUUID }}", "{ randomUUID }")
        
        lines = source_code.split('\n')
        main_line_num = source_code[:main_match.start()].count('\n')
        
        # Check if this is a CommonJS export (function assignment) or ES6 export
        matched_line = lines[main_line_num]
        is_commonjs = any(pattern in matched_line for pattern in [
            'exports.main', 'module.exports'
        ])
        
        if is_commonjs:
            # For CommonJS, wrap function with telemetry using wrapper function
            # Handle multi-line function definitions
            lines = source_code.split('\n')
            main_line_num = source_code[:main_match.start()].count('\n')
            
            # Get the complete function definition (might span multiple lines)
            function_lines = []
            brace_count = 0
            i = main_line_num
            
            while i < len(lines):
                line = lines[i]
                function_lines.append(line)
                
                # Count braces to find the end of the function
                brace_count += line.count('{')
                brace_count -= line.count('}')
                
                if brace_count <= 0 and i > main_line_num:
                    break
                    
                i += 1
            
            # Join the complete function definition
            complete_function = '\n'.join(function_lines)
            
            # Extract the function part (everything after =)
            if '=' in complete_function:
                prefix, function_part = complete_function.split('=', 1)
                prefix = prefix.strip()
                function_part = function_part.strip()
                
                # Create wrapped function using the telemetry wrapper
                wrapped_function = f"{prefix} = createTelemetryWrapper(\"{action_id}\", {workflow_id})({function_part})"
                
                # Replace the original function lines with the wrapped version
                lines[main_line_num:i+1] = [wrapped_function]
        else:
            # Convert ES6 export to CommonJS and use wrapper
            # Get the complete function definition
            lines = source_code.split('\n')
            main_line_num = source_code[:main_match.start()].count('\n')
            
            function_lines = []
            brace_count = 0
            i = main_line_num
            
            while i < len(lines):
                line = lines[i]
                function_lines.append(line)
                
                # Count braces to find the end of the function
                brace_count += line.count('{')
                brace_count -= line.count('}')
                
                if brace_count <= 0 and i > main_line_num:
                    break
                    
                i += 1
            
            # Join the complete function definition
            complete_function = '\n'.join(function_lines)
            
            # Remove "export" and convert to CommonJS assignment
            if complete_function.strip().startswith('export '):
                function_part = complete_function.strip()[7:]  # Remove "export "
                function_part = function_part.strip()
                
                # Create CommonJS export with telemetry wrapper
                wrapped_function = f"exports.main = createTelemetryWrapper(\"{action_id}\", {workflow_id})({function_part})"
                
                # Replace the original function lines with the wrapped version
                lines[main_line_num:i+1] = [wrapped_function]
        
        # Combine telemetry template with modified user code
        converted_code = telemetry_template + '\n' + '\n'.join(lines)
        
        return converted_code
    
    def _ensure_python_decorator_exists(
        self,
        source_code: str,
        action_id: str,
        workflow_id: int,
        main_match: re.Match
    ) -> str:
        """Ensure @telemetry_track decorator exists above Python main function"""
        
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
            self.warnings.append("Added telemetry decorator to existing Python main function")
        
        return '\n'.join(lines)
    
    def _ensure_javascript_decorator_exists(
        self,
        source_code: str,
        action_id: str,
        workflow_id: int,
        main_match: re.Match
    ) -> str:
        """Ensure @telemetryTrack decorator exists above JavaScript main function"""
        
        # Check if decorator already exists above main
        lines = source_code.split('\n')
        main_line_num = source_code[:main_match.start()].count('\n')
        
        # Look for decorator in lines before main
        decorator_found = False
        for i in range(max(0, main_line_num - 5), main_line_num):
            if '@telemetryTrack' in lines[i]:
                decorator_found = True
                # Update existing decorator with new parameters
                lines[i] = f"    @telemetryTrack(\"{action_id}\", {workflow_id})"
                break
        
        if not decorator_found:
            # Add decorator
            indent = main_match.group(1) if main_match.group(1) else ""
            decorator_line = f"{indent}@telemetryTrack(\"{action_id}\", {workflow_id})"
            lines.insert(main_line_num, decorator_line)
            self.warnings.append("Added telemetry decorator to existing JavaScript main function")
        
        return '\n'.join(lines)
    
    def _lint_python_source_code(self, source_code: str) -> Tuple[bool, List[str]]:
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
            logger.error("Python linting timed out")
            return False, ["Python linting timed out after 30 seconds"]
        except FileNotFoundError:
            logger.warning("Ruff not found, skipping Python linting")
            return True, []  # Pass if ruff is not available
        except Exception as e:
            logger.error(f"Python linting error: {e}")
            return False, [f"Python linting error: {str(e)}"]
    
    def _lint_javascript_source_code(self, source_code: str) -> Tuple[bool, List[str]]:
        """
        Run linting on JavaScript source code using ESLint.
        
        Args:
            source_code: JavaScript source code to lint
            
        Returns:
            Tuple of (passed, error_messages)
        """
        try:
            # Run eslint check on the source code
            result = subprocess.run(
                ['npx', 'eslint', '--format', 'json', '--stdin', '--stdin-filename', 'input.js'],
                input=source_code,
                text=True,
                capture_output=True,
                timeout=30  # 30 second timeout
            )
            
            if result.returncode == 0:
                return True, []
            else:
                # Parse ESLint JSON output for error messages
                try:
                    eslint_output = json.loads(result.stdout)
                    error_messages = []
                    for file_result in eslint_output:
                        for message in file_result.get('messages', []):
                            line_num = message.get('line', '?')
                            column_num = message.get('column', '')
                            error_msg = message.get('message', 'Unknown error')
                            rule_id = message.get('ruleId', 'unknown')
                            error_messages.append(f"Line {line_num}:{column_num} - {error_msg} ({rule_id})")
                    return False, error_messages
                except json.JSONDecodeError:
                    # Fallback to stderr if JSON parsing fails
                    return False, [result.stderr.strip() or "JavaScript linting failed with unknown error"]
                    
        except subprocess.TimeoutExpired:
            logger.error("JavaScript linting timed out")
            return False, ["JavaScript linting timed out after 30 seconds"]
        except FileNotFoundError:
            logger.warning("ESLint not found, skipping JavaScript linting")
            return True, []  # Pass if eslint is not available
        except Exception as e:
            logger.error(f"JavaScript linting error: {e}")
            return False, [f"JavaScript linting error: {str(e)}"]
    
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
        passed, errors = self._lint_python_source_code(source_code)
        
        # For now, we don't distinguish between errors and warnings in ruff output
        # All linting issues are treated as errors for simplicity
        warnings = []
        
        return passed, errors, warnings
    
    def lint_javascript_code(self, source_code: str) -> Tuple[bool, List[str], List[str]]:
        """
        Standalone JavaScript code linting service.
        
        Args:
            source_code: JavaScript source code to lint
            
        Returns:
            Tuple of (passed, errors, warnings)
        """
        # Validate input
        if not source_code or not source_code.strip():
            raise InvalidSourceError("Source code cannot be empty")
        
        # Run linting
        passed, errors = self._lint_javascript_source_code(source_code)
        
        # For now, we don't distinguish between errors and warnings in ESLint output
        # All linting issues are treated as errors for simplicity
        warnings = []
        
        return passed, errors, warnings
