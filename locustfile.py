#!/usr/bin/env python3
"""
Locust load testing file for rate limiting stress test.

This test will verify:
- Acceptance of up to 1000 requests per second
- Processing rate throttled to 200 requests per second
- Queue behavior when requests exceed processing rate
- Proper 503 responses when queue is full

Usage:
    locust -f locustfile.py --host=http://localhost:8000
"""

import time
import random
from locust import HttpUser, task, between, events
from locust.env import Environment
from locust.stats import stats_printer, stats_history
import gevent
import uuid

class RateLimitTestUser(HttpUser):
    """User class for testing rate limiting with mixed endpoints."""
    
    wait_time = between(0.1, 0.5)  # Wait between requests
    
    @task(2)  # 20% weight for health checks
    def health_check(self):
        """Test the health endpoint."""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
                # Log rate limiting headers
                max_rps = response.headers.get("X-Rate-Limit-Max-RPS")
                process_rps = response.headers.get("X-Rate-Limit-Process-RPS")
                queue_size = response.headers.get("X-Rate-Limit-Queue-Size")
                active_connections = response.headers.get("X-Rate-Limit-Active-Connections")
                status = response.headers.get("X-Rate-Limit-Status")
                
                if max_rps:
                    print(f"Health check - Max RPS: {max_rps}, Process RPS: {process_rps}, Queue: {queue_size}, Connections: {active_connections}, Status: {status}")
            elif response.status_code == 503:
                response.success()  # 503 is expected under load
                print(f"Health rate limited (503): {response.text}")
            else:
                response.failure(f"Health unexpected status: {response.status_code}")
    
    @task(8)  # 80% weight for execute endpoint
    def execute_workflow(self):
        """Test the execute endpoint with workflow payload."""
        payload = {
            "mode": "execute",
            "execution_id": f"5af74795-6d39-4379-a51c-8687b471a472",
            "config": {
                "action": {
                    "language": "python",
                    "entry": "action.py",
                    "source": "def main(event):\n    print('hello world')\n    return {'ok': True}"
                },
                "fixtures": [
                    {
                        "name": "event.json",
                        "source": '{ "inputFields": { "name": "Morgan" } }'
                    }
                ],
                "env": {
                    "MODE": "test"
                },
                "repeat": 1
            }
        }
        
        with self.client.post("/execute", json=payload, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
                # Log rate limiting headers
                max_rps = response.headers.get("X-Rate-Limit-Max-RPS")
                process_rps = response.headers.get("X-Rate-Limit-Process-RPS")
                queue_size = response.headers.get("X-Rate-Limit-Queue-Size")
                active_connections = response.headers.get("X-Rate-Limit-Active-Connections")
                status = response.headers.get("X-Rate-Limit-Status")
                
                if max_rps:
                    print(f"Execute success - Max RPS: {max_rps}, Process RPS: {process_rps}, Queue: {queue_size}, Connections: {active_connections}, Status: {status}")
            elif response.status_code == 503:
                response.success()  # 503 is expected under load
                print(f"Execute rate limited (503): {response.text}")
            elif response.status_code == 202:
                response.success()  # Accepted for processing
                print(f"Execute accepted (202) with status code {response.status_code}")
            else:
                response.failure(f"Execute unexpected status: {response.status_code} - {response.text}")


# Custom event handlers for detailed logging
@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Log detailed request information."""
    if exception:
        print(f"Request failed: {name} - {exception}")
    else:
        status_code = kwargs.get('context', {}).get('response', {}).get('status_code')
        if status_code == 503:
            print(f"Rate limited: {name} - Response time: {response_time}ms with status code {status_code}")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts."""
    print("=" * 60)
    print("RATE LIMITING LOAD TEST STARTING")
    print("=" * 60)
    print("Test Configuration:")
    print("- Target: Accept up to 1000 RPS")
    print("- Processing: Throttle to 200 RPS")
    print("- Queue: Hold excess requests in memory")
    print("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment: Environment, **kwargs):
    """Print detailed statistics after test completion."""
    stats = environment.stats
    
    print(f"\n{'='*60}")
    print(f"RATE LIMITING LOAD TEST COMPLETED")
    print(f"{'='*60}")
    
    print(f"\nTotal requests: {stats.total.num_requests}")
    print(f"Total failures: {stats.total.num_failures}")
    print(f"Success rate: {((stats.total.num_requests - stats.total.num_failures) / stats.total.num_requests * 100):.2f}%")
    
    # Check health endpoint statistics
    if "/health" in stats.entries:
        entry = stats.entries["/health"]
        print(f"\n/health (20% of traffic):")
        print(f"  Requests: {entry.num_requests}")
        print(f"  Failures: {entry.num_failures}")
        print(f"  Avg response time: {entry.avg_response_time:.2f}ms")
        print(f"  Max response time: {entry.max_response_time:.2f}ms")
        
        # Check for 503 responses (rate limiting)
        if hasattr(entry, 'status_code_counts'):
            rate_limited = entry.status_code_counts.get(503, 0)
            print(f"  Rate limited (503): {rate_limited}")
    
    # Check execute endpoint statistics
    if "/execute" in stats.entries:
        entry = stats.entries["/execute"]
        print(f"\n/execute (80% of traffic):")
        print(f"  Requests: {entry.num_requests}")
        print(f"  Failures: {entry.num_failures}")
        print(f"  Avg response time: {entry.avg_response_time:.2f}ms")
        print(f"  Max response time: {entry.max_response_time:.2f}ms")
        
        # Check for different response codes
        if hasattr(entry, 'status_code_counts'):
            rate_limited = entry.status_code_counts.get(503, 0)
            accepted = entry.status_code_counts.get(202, 0)
            success = entry.status_code_counts.get(200, 0)
            print(f"  Success (200): {success}")
            print(f"  Accepted (202): {accepted}")
            print(f"  Rate limited (503): {rate_limited}")
    
    print(f"\n{'='*60}")


if __name__ == "__main__":
    # Allow running directly for quick testing
    import sys
    if len(sys.argv) > 1:
        host = sys.argv[1]
    else:
        host = "http://localhost:8000"
    
    print(f"Starting Locust test against {host}")
    print("Run with: locust -f locustfile.py --host={host}")
    print("Or visit http://localhost:8089 for web interface")
