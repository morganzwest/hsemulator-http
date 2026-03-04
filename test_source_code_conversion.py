#!/usr/bin/env python3
"""
Simple test script to verify the Source Code Conversion endpoint works.
Run this script to test the new functionality.
"""

import requests
import json

def test_source_code_conversion():
    """Test the source code conversion endpoint"""
    
    # Test data
    test_cases = [
        {
            "name": "Basic conversion",
            "data": {
                "source_code": "def main(event):\n    return {'message': 'Hello World'}",
                "action_id": "test-action-123",
                "workflow_id": 456789,
                "secret": "test-secret"
            }
        },
        {
            "name": "Async main function",
            "data": {
                "source_code": "async def main(event):\n    return {'message': 'Async Hello'}",
                "action_id": "async-action-123"
            }
        },
        {
            "name": "Missing main function (should fail)",
            "data": {
                "source_code": "def hello_world():\n    print('Hello')",
                "action_id": "no-main-action"
            }
        },
        {
            "name": "Empty source code (should fail)",
            "data": {
                "source_code": "",
                "action_id": "empty-action"
            }
        }
    ]
    
    base_url = "http://localhost:8080"  # Updated to match run.py port
    
    for test_case in test_cases:
        print(f"\n--- Testing: {test_case['name']} ---")
        
        try:
            response = requests.post(
                f"{base_url}/convert-source-code",
                json=test_case["data"],
                headers={"Content-Type": "application/json"}
            )
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print("✅ Success!")
                print(f"Warnings: {result.get('warnings', [])}")
                print("Converted code preview:")
                print(result['converted_source_code'][:500] + "..." if len(result['converted_source_code']) > 500 else result['converted_source_code'])
            else:
                print("❌ Failed!")
                print(f"Error: {response.text}")
                
        except requests.exceptions.ConnectionError:
            print("❌ Connection failed - make sure the server is running")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    print("Testing Source Code Conversion Endpoint")
    print("=" * 50)
    test_source_code_conversion()
