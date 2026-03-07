import hashlib
import logging
from typing import Optional, Dict, Any, List
import json

import httpx

from app.models.errors import SecretPersistenceError

logger = logging.getLogger(__name__)

HUBSPOT_BASE_URL = "https://api.hubapi.com"


class HubSpotServiceError(Exception):
    """Base exception for HubSpot service errors"""
    pass


class WorkflowNotFoundError(HubSpotServiceError):
    """Raised when a workflow is not found"""
    pass


class ActionNotFoundError(HubSpotServiceError):
    """Raised when the target action is not found"""
    pass


class HubSpotAPIError(HubSpotServiceError):
    """Raised when HubSpot API returns an error"""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


async def get_workflow(token: str, workflow_id: str) -> Dict[str, Any]:
    """Fetch a workflow from HubSpot API"""
    url = f"{HUBSPOT_BASE_URL}/automation/v4/flows/{workflow_id}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)

        if response.status_code == 404:
            raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")
        elif not response.is_success:
            raise HubSpotAPIError(
                f"HubSpot GET workflow failed: {response.status_code} {response.text}",
                response.status_code
            )

        try:
            return response.json()
        except json.JSONDecodeError as e:
            raise HubSpotAPIError(f"Invalid JSON response from HubSpot: {e}")


async def get_portal_info(token: str) -> Dict[str, Any]:
    """Fetch portal/account information from HubSpot API"""
    url = f"{HUBSPOT_BASE_URL}/account-info/v3/details"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)

        if not response.is_success:
            raise HubSpotAPIError(
                f"HubSpot GET portal info failed: {response.status_code} {response.text}",
                response.status_code
            )

        try:
            return response.json()
        except json.JSONDecodeError as e:
            raise HubSpotAPIError(f"Invalid JSON response from HubSpot: {e}")


async def get_workflows_list(token: str, limit: int = 100, after: Optional[str] = None) -> Dict[str, Any]:
    """Fetch a list of workflows from HubSpot API with pagination support"""
    url = f"{HUBSPOT_BASE_URL}/automation/v4/flows"
    params = {"limit": str(limit)}

    if after:
        params["after"] = after

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers, params=params)

        if not response.is_success:
            raise HubSpotAPIError(
                f"HubSpot GET workflows list failed: {response.status_code} {response.text}",
                response.status_code
            )

        try:
            return response.json()
        except json.JSONDecodeError as e:
            raise HubSpotAPIError(f"Invalid JSON response from HubSpot: {e}")


async def get_workflows_batch_read(token: str, workflow_ids: List[str]) -> Dict[str, Any]:
    """Fetch multiple workflows in a single batch request"""
    url = f"{HUBSPOT_BASE_URL}/automation/v4/flows/batch/read"

    # Prepare inputs for batch request
    inputs = [{"flowId": flow_id, "type": "FLOW_ID"}
              for flow_id in workflow_ids]

    payload = {"inputs": inputs}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Longer timeout for batch
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)

        if not response.is_success:
            raise HubSpotAPIError(
                f"HubSpot batch read workflows failed: {response.status_code} {response.text}",
                response.status_code
            )

        try:
            return response.json()
        except json.JSONDecodeError as e:
            raise HubSpotAPIError(f"Invalid JSON response from HubSpot: {e}")


def find_action_by_action_id(workflow: Dict[str, Any], action_id: str) -> int:
    """Find the target action index by searching for the HubSpot actionId"""
    actions = workflow.get("actions", [])
    if not isinstance(actions, list):
        raise HubSpotServiceError("Workflow missing 'actions' array")

    matches: List[int] = []

    for idx, action in enumerate(actions):
        if action.get("type") != "CUSTOM_CODE":
            continue

        # Match by HubSpot's actionId field
        current_action_id = action.get("actionId")
        if current_action_id == action_id:
            matches.append(idx)

    if not matches:
        raise ActionNotFoundError(
            f"No CUSTOM_CODE action found with actionId '{action_id}'"
        )

    if len(matches) != 1:
        raise HubSpotServiceError(
            f"Action ID '{action_id}' matched {len(matches)} actions. Expected exactly 1 match."
        )

    return matches[0]


def get_action_source_code(workflow: Dict[str, Any], action_index: int) -> str:
    """Extract source code from a specific action"""
    actions = workflow.get("actions", [])
    if not isinstance(actions, list):
        raise HubSpotServiceError("Workflow missing 'actions' array")

    if action_index >= len(actions):
        raise HubSpotServiceError(f"Action index {action_index} out of bounds")

    action = actions[action_index]
    source_code = action.get("sourceCode")

    if not isinstance(source_code, str):
        raise HubSpotServiceError("Target action missing 'sourceCode'")

    return source_code


def generate_source_hash(source_code: str) -> str:
    """Generate SHA256 hash of canonical source code"""
    canonical = strip_hash_marker(source_code)
    return hashlib.sha256(canonical.encode()).hexdigest()


def inject_hash_marker(source_code: str, hash_value: str) -> str:
    """Inject hash marker at the top of the source code"""
    # Detect language style for comment format
    is_pythonish = ("def " in source_code or "import " in source_code or
                    "from " in source_code)

    comment = f"# novocode-sha: {hash_value}\n" if is_pythonish else f"// novocode-sha: {hash_value}\n"

    # Check if marker already exists
    existing_hash = extract_hash_marker(source_code)
    if existing_hash == hash_value:
        return source_code

    # Replace existing marker or add new one
    if existing_hash:
        return replace_hash_marker(source_code, comment)

    return comment + source_code


def extract_hash_marker(source_code: str) -> Optional[str]:
    """Extract hash marker from source code"""
    for line in source_code.split('\n')[:10]:
        line = line.strip()
        if line.startswith("# novocode-sha: "):
            return line[len("# novocode-sha: "):].strip()
        elif line.startswith("// novocode-sha: "):
            return line[len("// novocode-sha: "):].strip()
    return None


def strip_hash_marker(source_code: str) -> str:
    """Remove hash marker from source code"""
    lines = source_code.split('\n')
    filtered_lines = [
        line for line in lines
        if not (line.strip().startswith("# novocode-sha: ") or
                line.strip().startswith("// novocode-sha: "))
    ]
    return '\n'.join(filtered_lines)


def replace_hash_marker(source_code: str, new_marker: str) -> str:
    """Replace existing hash marker with new one"""
    lines = source_code.split('\n')
    result_lines = []
    replaced = False

    for i, line in enumerate(lines):
        if not replaced and i < 10:
            stripped = line.strip()
            if stripped.startswith("# novocode-sha: ") or stripped.startswith("// novocode-sha: "):
                result_lines.append(new_marker.rstrip())
                replaced = True
                continue
        result_lines.append(line)

    return '\n'.join(result_lines)


def build_updated_workflow_payload(
    workflow: Dict[str, Any],
    action_index: int,
    new_source: str,
    runtime_override: Optional[str] = None
) -> Dict[str, Any]:
    """Build the payload for updating a workflow"""
    # Clone workflow to avoid modifying original
    updated_workflow = workflow.copy()
    actions = updated_workflow.get("actions", [])

    if not isinstance(actions, list) or action_index >= len(actions):
        raise HubSpotServiceError(f"Invalid action index {action_index}")

    # Update the action
    action = actions[action_index].copy()
    action["sourceCode"] = new_source

    if runtime_override:
        action["runtime"] = runtime_override

    actions[action_index] = action
    updated_workflow["actions"] = actions

    # Build sanitized payload with required fields
    payload = {}

    required_fields = [
        "revisionId", "type", "name", "isEnabled", "actions", "startActionId"
    ]

    for field in required_fields:
        if field not in updated_workflow:
            raise HubSpotServiceError(
                f"Workflow missing required field '{field}'")
        payload[field] = updated_workflow[field]

    # Include optional fields if present
    optional_fields = [
        "enrollmentCriteria", "enrollmentSchedule", "goalFilterBranch",
        "suppressionListIds", "timeWindows", "blockedDates",
        "unEnrollmentSetting", "customProperties", "canEnrollFromSalesforce",
        "description"
    ]

    for field in optional_fields:
        if field in updated_workflow:
            payload[field] = updated_workflow[field]

    return payload


async def put_workflow(token: str, workflow_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Update a workflow in HubSpot API"""
    url = f"{HUBSPOT_BASE_URL}/automation/v4/flows/{workflow_id}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.put(url, headers=headers, json=payload)

        if not response.is_success:
            raise HubSpotAPIError(
                f"HubSpot PUT workflow failed: {response.status_code} {response.text}",
                response.status_code
            )

        try:
            return response.json()
        except json.JSONDecodeError as e:
            raise HubSpotAPIError(f"Invalid JSON response from HubSpot: {e}")
