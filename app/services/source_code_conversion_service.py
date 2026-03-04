import logging
import re
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


class SourceCodeConversionService:
    """
    Service for converting Python source code to include telemetry tracking.
    
    This service wraps user Python code with telemetry helper functions
    and decorates the main(event) entrypoint with @telemetry_track().
    """
    
    # Default telemetry template
    DEFAULT_TELEMETRY_TEMPLATE = '''import json
import time
import traceback
from typing import Dict, Any, Callable
from functools import wraps

SECRET = "{secret}"

def telemetry_track(action_id: str = "{action_id}", workflow_id: int = {workflow_id}):
    """
    Decorator to add telemetry tracking to HubSpot workflow actions.
    
    Args:
        action_id: HubSpot action ID for tracking
        workflow_id: HubSpot workflow ID for tracking
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(event: Dict[str, Any]) -> Dict[str, Any]:
            start_time = time.time()
            
            telemetry_data = {{
                "action_id": action_id,
                "workflow_id": workflow_id,
                "start_time": start_time,
                "secret": SECRET
            }}
            
            try:
                result = func(event)
                telemetry_data.update({{
                    "status": "success",
                    "end_time": time.time(),
                    "duration": time.time() - start_time,
                    "result": result
                }})
                
                # Send telemetry data (implement your telemetry endpoint)
                _send_telemetry(telemetry_data)
                
                return result
                
            except Exception as e:
                telemetry_data.update({{
                    "status": "error",
                    "end_time": time.time(),
                    "duration": time.time() - start_time,
                    "error": str(e),
                    "traceback": traceback.format_exc()
                }})
                
                # Send telemetry data for errors
                _send_telemetry(telemetry_data)
                
                raise
                
        return wrapper
    return decorator

def _send_telemetry(data: Dict[str, Any]) -> None:
    """
    Send telemetry data to monitoring service.
    
    Args:
        data: Telemetry data to send
    """
    try:
        # Implement your telemetry sending logic here
        # For now, just log the data
        logger.info(f"Telemetry: {{json.dumps(data)}}")
    except Exception as e:
        logger.error(f"Failed to send telemetry: {{e}}")

# USER CODE BELOW
'''

    def __init__(self):
        self.warnings: List[str] = []
    
    def convert_source_code(
        self,
        source_code: str,
        action_id: Optional[str] = None,
        workflow_id: Optional[int] = None,
        secret: Optional[str] = None
    ) -> Tuple[str, List[str]]:
        """
        Convert Python source code to include telemetry tracking.
        
        Args:
            source_code: Raw Python source code
            action_id: Optional action ID for telemetry
            workflow_id: Optional workflow ID for telemetry  
            secret: Optional secret for telemetry
            
        Returns:
            Tuple of (converted_source_code, warnings)
            
        Raises:
            InvalidSourceError: If source code is invalid
            MainNotFoundError: If no main(event) function found
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
