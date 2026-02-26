import logging
import os
from uuid import UUID
from typing import List, Dict, Any, Optional

from app.services.secret_decrypt_service import decrypt_secret_for_test
from app.services.hubspot_service import (
    get_workflows_list,
    get_workflow,
    get_workflows_batch_read,
    HubSpotAPIError,
    WorkflowNotFoundError,
    HubSpotServiceError,
)
from app.services.action_processing_service import (
    process_custom_action,
    ActionProcessingError,
    ActionAlreadyExistsError,
)
from app.db.secrets import verify_cicd_secret
from app.models.workflows import WorkflowDiscoveryResponse, CustomCodeAction
from app.models.errors import SecretNotFoundError, SecretPersistenceError

logger = logging.getLogger(__name__)


class WorkflowDiscoveryError(Exception):
    """Base exception for workflow discovery errors"""
    pass


class SecretVerificationError(WorkflowDiscoveryError):
    """Raised when CICD secret verification fails"""
    pass


async def get_all_workflows_paginated(token: str) -> List[Dict[str, Any]]:
    """
    Fetch all workflows from HubSpot with pagination support.
    
    Args:
        token: HubSpot API token
        
    Returns:
        List of all workflow objects
        
    Raises:
        WorkflowDiscoveryError: If pagination fails or API errors occur
    """
    all_workflows = []
    after = None
    page_count = 0
    
    while True:
        try:
            response = await get_workflows_list(token, limit=100, after=after)
            page_count += 1
            
            workflows = response.get("results", [])
            if not workflows:
                logger.info(f"No workflows found on page {page_count}")
                break
                
            all_workflows.extend(workflows)
            logger.info(f"Retrieved {len(workflows)} workflows from page {page_count}")
            
            # Check if there are more pages
            paging = response.get("paging")
            if not paging or "next" not in paging:
                logger.info(f"No more pages after page {page_count}")
                break
                
            next_page = paging["next"]
            after = next_page.get("after")
            if not after:
                logger.info(f"No 'after' token found, ending pagination at page {page_count}")
                break
                
            # Safety check to prevent infinite loops
            if page_count > 100:  # Arbitrary reasonable limit
                logger.warning(f"Stopping pagination after {page_count} pages to prevent infinite loop")
                break
                
        except HubSpotAPIError as e:
            raise WorkflowDiscoveryError(f"Failed to fetch workflows page {page_count}: {e}")
        except Exception as e:
            raise WorkflowDiscoveryError(f"Unexpected error during pagination on page {page_count}: {e}")
    
    logger.info(f"Total workflows retrieved: {len(all_workflows)} across {page_count} pages")
    return all_workflows


async def get_workflow_details_batch(token: str, workflow_ids: List[str], batch_size: int = 10, use_batch: bool = True) -> List[Dict[str, Any]]:
    """
    Fetch workflow details using batch API for better efficiency.
    
    Args:
        token: HubSpot API token
        workflow_ids: List of workflow IDs to fetch
        batch_size: Number of workflows to fetch per batch request
        use_batch: Whether to use batch processing (default: True)
        
    Returns:
        List of detailed workflow objects
        
    Raises:
        WorkflowDiscoveryError: If batch requests fail
    """
    all_workflow_details = []
    
    # If batch processing is disabled, use individual requests
    if not use_batch:
        logger.info(f"Batch processing disabled, using individual requests for {len(workflow_ids)} workflows")
        for workflow_id in workflow_ids:
            try:
                workflow_detail = await get_workflow(token, workflow_id)
                all_workflow_details.append(workflow_detail)
            except (WorkflowNotFoundError, HubSpotAPIError) as e:
                logger.warning(f"Failed to fetch workflow {workflow_id} individually: {e}")
                continue
            except Exception as e:
                logger.warning(f"Unexpected error fetching workflow {workflow_id}: {e}")
                continue
        return all_workflow_details
    
    # Process workflows in batches to avoid API limits
    for i in range(0, len(workflow_ids), batch_size):
        batch_ids = workflow_ids[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        
        try:
            logger.info(f"Fetching batch {batch_num} with {len(batch_ids)} workflows")
            batch_response = await get_workflows_batch_read(token, batch_ids)
            
            # Debug: Log the actual batch response structure
            logger.debug(f"Batch response structure: {batch_response}")
            
            # Extract results from batch response
            results = batch_response.get("results", [])
            if not results:
                logger.warning(f"No results returned for batch {batch_num}")
                logger.debug(f"Full batch response: {batch_response}")
                logger.info(f"Switching to individual requests for batch {batch_num} due to no batch results")
                # Fall back to individual requests
                for workflow_id in batch_ids:
                    try:
                        workflow_detail = await get_workflow(token, workflow_id)
                        all_workflow_details.append(workflow_detail)
                    except (WorkflowNotFoundError, HubSpotAPIError) as e:
                        logger.warning(f"Failed to fetch workflow {workflow_id} individually: {e}")
                        continue
                    except Exception as e:
                        logger.warning(f"Unexpected error fetching workflow {workflow_id}: {e}")
                        continue
                continue
            
            logger.info(f"Batch {batch_num} returned {len(results)} results")
            
            # Batch response contains workflow objects directly in results array
            # No status/result wrapper like I expected
            for workflow_detail in results:
                if workflow_detail and workflow_detail.get("id"):
                    logger.debug(f"Successfully parsed workflow {workflow_detail.get('id')}")
                    all_workflow_details.append(workflow_detail)
                else:
                    logger.warning(f"Invalid workflow data in batch result")
            
            logger.info(f"Batch {batch_num} completed: {len(results)} results processed, {len(all_workflow_details)} workflows collected")
            
        except HubSpotAPIError as e:
            logger.error(f"Batch {batch_num} failed: {e}")
            # Fall back to individual requests for this batch
            logger.info(f"Falling back to individual requests for batch {batch_num}")
            for workflow_id in batch_ids:
                try:
                    workflow_detail = await get_workflow(token, workflow_id)
                    all_workflow_details.append(workflow_detail)
                except (WorkflowNotFoundError, HubSpotAPIError) as e:
                    logger.warning(f"Failed to fetch workflow {workflow_id} individually: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Unexpected error fetching workflow {workflow_id}: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Unexpected error in batch {batch_num}: {e}")
            raise WorkflowDiscoveryError(f"Batch processing failed: {e}")
    
    logger.info(f"Retrieved {len(all_workflow_details)} workflow details using batch processing")
    return all_workflow_details


def find_custom_code_actions(workflow: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Find all custom code actions in a workflow.
    
    Args:
        workflow: HubSpot workflow object
        
    Returns:
        List of custom code action objects
    """
    actions = workflow.get("actions", [])
    if not isinstance(actions, list):
        logger.warning(f"Workflow {workflow.get('id')} has no valid actions array")
        return []
    
    custom_actions = []
    for action in actions:
        if action.get("type") == "CUSTOM_CODE":
            custom_actions.append(action)
    
    return custom_actions


async def discover_workflows(secret_id: UUID, portal_id: UUID, owner_id: UUID, portal_id_int: int, process_actions: bool = True) -> WorkflowDiscoveryResponse:
    """
    Discover all workflows with custom code actions in a portal.
    
    Args:
        secret_id: ID of the CICD secret containing HubSpot token
        portal_id: Portal ID to scan
        owner_id: UUID of the action owner
        portal_id_int: Portal ID as integer for event data
        process_actions: Whether to process and store actions (default: True)
        
    Returns:
        WorkflowDiscoveryResponse with discovered actions
        
    Raises:
        SecretVerificationError: If secret verification fails
        WorkflowDiscoveryError: If discovery process fails
    """
    # Step 1: Verify the CICD secret exists and matches the portal
    try:
        is_valid = verify_cicd_secret(secret_id, portal_id)
        if not is_valid:
            raise SecretVerificationError("CICD secret verification failed")
    except SecretNotFoundError as e:
        raise SecretVerificationError(f"CICD secret not found: {e}")
    except SecretPersistenceError as e:
        raise SecretVerificationError(f"Database error during secret verification: {e}")
    
    # Step 2: Decrypt the secret to get HubSpot token
    try:
        secret_data = decrypt_secret_for_test(secret_id)
        token = secret_data["value"]
    except Exception as e:
        raise WorkflowDiscoveryError(f"Failed to decrypt CICD secret: {e}")
    
    # Step 3: Get all workflows with pagination
    try:
        all_workflows = await get_all_workflows_paginated(token)
    except WorkflowDiscoveryError:
        raise
    except Exception as e:
        raise WorkflowDiscoveryError(f"Failed to retrieve workflows: {e}")
    
    # Step 4: Extract workflow IDs and fetch details using batch processing
    workflow_ids = []
    for workflow_summary in all_workflows:
        workflow_id = workflow_summary.get("id")
        if workflow_id:
            workflow_ids.append(workflow_id)
    
    if not workflow_ids:
        logger.warning("No valid workflow IDs found")
        return WorkflowDiscoveryResponse(
            ok=True,
            portal_id=portal_id,
            total_workflows=0,
            total_code_actions=0,
            actions=[],
        )
    
    logger.info(f"Fetching details for {len(workflow_ids)} workflows")
    
    # Check if batch processing is disabled via environment variable
    use_batch = os.getenv("USE_BATCH_PROCESSING", "true").lower() != "false"
    if not use_batch:
        logger.info("Batch processing disabled via USE_BATCH_PROCESSING=false")
    else:
        logger.info("Using batch processing for improved efficiency")
    
    try:
        workflow_details_list = await get_workflow_details_batch(token, workflow_ids, batch_size=10, use_batch=use_batch)
    except WorkflowDiscoveryError:
        raise
    except Exception as e:
        raise WorkflowDiscoveryError(f"Failed to retrieve workflow details: {e}")
    
    # Step 5: Process each workflow to find custom code actions
    custom_code_actions = []
    
    for workflow_details in workflow_details_list:
        workflow_id = workflow_details.get("id")
        if not workflow_id:
            logger.warning("Found workflow without ID, skipping")
            continue
        
        try:
            # Find custom code actions
            custom_actions = find_custom_code_actions(workflow_details)
            
            for action in custom_actions:
                # Create basic CustomCodeAction object first
                custom_action = CustomCodeAction(
                    name=workflow_details.get("name", "Unknown Workflow"),
                    id=workflow_id,
                    language=action.get("runtime"),
                    action_id=action.get("actionId", "unknown"),
                )
                
                if process_actions:
                    try:
                        # Process the action (create database record, store files, etc.)
                        result = await process_custom_action(
                            workflow_name=workflow_details.get("name", "Unknown Workflow"),
                            workflow_id=workflow_id,
                            action_id=action.get("actionId", "unknown"),
                            language=action.get("runtime", "unknown"),
                            source_code=action.get("sourceCode", ""),
                            portal_id=portal_id,
                            owner_id=owner_id,
                            portal_id_int=portal_id_int,
                        )
                        
                        # Update the custom action with processing results
                        try:
                            custom_action.database_action_id = UUID(result["action_id"])
                        except (ValueError, TypeError) as uuid_error:
                            custom_action.processed = False
                            custom_action.error = f"Invalid action ID format: {uuid_error}"
                            logger.error(f"Invalid UUID format for action ID: {result.get('action_id')}")
                            continue
                        
                        custom_action.filepath = result["filepath"]
                        custom_action.event_filepath = result["event_filepath"]
                        custom_action.input_fields = result["input_fields"]
                        custom_action.processed = True
                        
                        logger.info(
                            f"Successfully processed action from workflow {workflow_id}",
                            extra={
                                "workflow_id": workflow_id,
                                "action_id": result["action_id"],
                            }
                        )
                        
                    except (ActionProcessingError, ActionAlreadyExistsError) as e:
                        custom_action.processed = False
                        custom_action.error = str(e)
                        if isinstance(e, ActionAlreadyExistsError):
                            logger.info(f"Action already exists for workflow {workflow_id}: {e}")
                        else:
                            logger.error(f"Failed to process action from workflow {workflow_id}: {e}")
                        
                    except (ValueError, TypeError) as e:
                        custom_action.processed = False
                        custom_action.error = f"Data validation error: {str(e)}"
                        logger.error(f"Validation error processing action from workflow {workflow_id}: {e}")
                        
                    except Exception as e:
                        custom_action.processed = False
                        custom_action.error = f"Unexpected error: {str(e)}"
                        logger.exception(f"Unexpected error processing action from workflow {workflow_id}")
                else:
                    # Legacy behavior: just print the action details
                    print(f"\n=== CUSTOM CODE ACTION FOUND ===")
                    print(f"Workflow ID: {workflow_id}")
                    print(f"Workflow Name: {workflow_details.get('name', 'Unknown')}")
                    print(f"Action ID: {action.get('actionId', 'unknown')}")
                    print(f"Action Type: {action.get('type', 'CUSTOM_CODE')}")
                    print(f"Language: {action.get('runtime', 'unknown')}")
                    print(f"Source Code:")
                    print(action.get("sourceCode", ""))
                    print("=" * 30)
                
                custom_code_actions.append(custom_action)
                
        except Exception as e:
            logger.warning(f"Unexpected error processing workflow {workflow_id}: {e}")
            continue
    
    # Step 6: Return results
    total_workflows = len(all_workflows)
    total_code_actions = len(custom_code_actions)
    
    logger.info(f"Discovery complete: Found {total_code_actions} custom code actions across {total_workflows} workflows")
    
    return WorkflowDiscoveryResponse(
        ok=True,
        portal_id=portal_id,
        total_workflows=total_workflows,
        total_code_actions=total_code_actions,
        actions=custom_code_actions,
    )
