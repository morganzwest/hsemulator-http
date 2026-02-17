import logging
import json
import re
from uuid import UUID
from typing import Dict, Any, Optional

from app.db import get_supabase

logger = logging.getLogger(__name__)


class StorageServiceError(Exception):
    """Base exception for storage service errors"""
    pass


class FileUploadError(StorageServiceError):
    """Raised when file upload fails"""
    pass


class FileDownloadError(StorageServiceError):
    """Raised when file download fails"""
    pass


def generate_action_filepath(portal_id: UUID, action_id: UUID, language: str) -> str:
    """Generate the storage path for an action file"""
    file_ext = "py" if language == "python" else "js"
    return f"{portal_id}/{action_id}/action.{file_ext}"


def generate_event_filepath(portal_id: UUID, action_id: UUID) -> str:
    """Generate the storage path for an event file"""
    return f"{portal_id}/{action_id}/event.json"


def extract_input_fields_from_source(source_code: str, language: str) -> Dict[str, Any]:
    """
    Extract input fields from source code by looking for common patterns.
    
    This is a basic implementation that looks for common patterns in HubSpot
    custom code actions. In a production environment, you might want to use
    more sophisticated parsing or have the input fields defined explicitly.
    """
    input_fields = {}
    
    if language.lower() == "python":
        # Look for patterns like event.get('inputFields', {}).get('field_name')
        pattern = r"event\.get\(['\"]inputFields['\"],\s*\{\}\)\.get\(['\"]([^'\"]+)['\"]"
        matches = re.findall(pattern, source_code)
        
        for field_name in matches:
            # Try to extract default values
            default_pattern = rf"event\.get\(['\"]inputFields['\"],\s*\{{\}}\)\.get\(['\"]{field_name}['\"],\s*([^,\)]+)"
            default_match = re.search(default_pattern, source_code)
            
            if default_match:
                try:
                    # Try to evaluate the default value
                    default_value = eval(default_match.group(1).strip())
                    input_fields[field_name] = default_value
                except:
                    input_fields[field_name] = None
            else:
                input_fields[field_name] = None
                
    elif language.lower() in ["javascript", "js"]:
        # Look for patterns like event.inputFields?.fieldName
        pattern = r"event\.inputFields\?\.([a-zA-Z_][a-zA-Z0-9_]*)"
        matches = re.findall(pattern, source_code)
        
        for field_name in matches:
            input_fields[field_name] = None
    
    return input_fields


def generate_event_json(input_fields: Dict[str, Any], portal_id: int, object_id: int = 123456) -> Dict[str, Any]:
    """Generate event JSON structure based on input fields"""
    event = {
        "object": {
            "objectType": "CONTACT",
            "objectId": object_id
        },
        "inputFields": input_fields,
        "fields": {},
        "portalId": portal_id
    }
    
    return event


async def upload_source_code(portal_id: UUID, action_id: UUID, source_code: str, language: str) -> str:
    """
    Upload source code to Supabase storage.
    
    Args:
        portal_id: Portal UUID
        action_id: Action UUID  
        source_code: The source code content
        language: Programming language (python or javascript)
        
    Returns:
        The file path in storage
        
    Raises:
        FileUploadError: If upload fails
    """
    try:
        supabase = get_supabase()
        filepath = generate_action_filepath(portal_id, action_id, language)
        
        # Upload to Supabase Storage
        result = supabase.storage.from_("actions").upload(
            path=filepath,
            file=source_code.encode('utf-8'),
            file_options={"content-type": "text/plain"}
        )
        
        # Check for errors
        if hasattr(result, 'error') and result.error:
            raise FileUploadError(f"Storage upload failed: {result.error}")
        
        logger.info(f"Uploaded source code to {filepath}")
        return filepath
        
    except FileUploadError:
        raise
    except Exception as e:
        logger.exception(
            "Failed to upload source code",
            extra={
                "portal_id": str(portal_id),
                "action_id": str(action_id),
                "language": language,
            }
        )
        raise FileUploadError(f"Failed to upload source code: {e}")


async def upload_event_file(portal_id: UUID, action_id: UUID, input_fields: Dict[str, Any], portal_id_int: int) -> str:
    """
    Upload event JSON file to Supabase storage.
    
    Args:
        portal_id: Portal UUID
        action_id: Action UUID
        input_fields: Dictionary of input fields and their values
        portal_id_int: Portal ID as integer for the event data
        
    Returns:
        The file path in storage
        
    Raises:
        FileUploadError: If upload fails
    """
    try:
        supabase = get_supabase()
        filepath = generate_event_filepath(portal_id, action_id)
        
        # Generate event JSON
        event_data = generate_event_json(input_fields, portal_id_int)
        event_json = json.dumps(event_data, indent=2)
        
        # Upload to Supabase Storage
        result = supabase.storage.from_("actions").upload(
            path=filepath,
            file=event_json.encode('utf-8'),
            file_options={"content-type": "application/json"}
        )
        
        # Check for errors
        if hasattr(result, 'error') and result.error:
            raise FileUploadError(f"Storage upload failed: {result.error}")
        
        logger.info(f"Uploaded event file to {filepath}")
        return filepath
        
    except FileUploadError:
        raise
    except Exception as e:
        logger.exception(
            "Failed to upload event file",
            extra={
                "portal_id": str(portal_id),
                "action_id": str(action_id),
                "input_fields": input_fields,
            }
        )
        raise FileUploadError(f"Failed to upload event file: {e}")


async def download_file(filepath: str) -> str:
    """
    Download a file from Supabase storage.
    
    Args:
        filepath: Path to the file in storage
        
    Returns:
        File content as string
        
    Raises:
        FileDownloadError: If download fails
    """
    try:
        supabase = get_supabase()
        
        # Download from Supabase Storage
        result = supabase.storage.from_("actions").download(filepath)
        
        if hasattr(result, 'error') and result.error:
            raise FileDownloadError(f"Storage download failed: {result.error}")
        
        content = result.decode('utf-8') if isinstance(result, bytes) else result
        logger.info(f"Downloaded file from {filepath}")
        return content
        
    except FileDownloadError:
        raise
    except Exception as e:
        logger.exception(
            "Failed to download file",
            extra={"filepath": filepath}
        )
        raise FileDownloadError(f"Failed to download file: {e}")


async def create_action_files(
    portal_id: UUID,
    action_id: UUID, 
    source_code: str,
    language: str,
    portal_id_int: int
) -> tuple[str, str, Dict[str, Any]]:
    """
    Create both source code and event files for an action.
    
    Args:
        portal_id: Portal UUID
        action_id: Action UUID
        source_code: Source code content
        language: Programming language
        portal_id_int: Portal ID as integer for event data
        
    Returns:
        Tuple of (source_filepath, event_filepath, input_fields)
        
    Raises:
        FileUploadError: If any upload fails
    """
    try:
        # Extract input fields from source code
        input_fields = extract_input_fields_from_source(source_code, language)
        
        # Upload source code
        source_filepath = await upload_source_code(portal_id, action_id, source_code, language)
        
        # Upload event file
        event_filepath = await upload_event_file(portal_id, action_id, input_fields, portal_id_int)
        
        return source_filepath, event_filepath, input_fields
        
    except Exception as e:
        logger.exception(
            "Failed to create action files",
            extra={
                "portal_id": str(portal_id),
                "action_id": str(action_id),
                "language": language,
            }
        )
        raise FileUploadError(f"Failed to create action files: {e}")
