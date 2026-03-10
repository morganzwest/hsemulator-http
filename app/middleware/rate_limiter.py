"""
In-memory rate limiting middleware with queue system.

This middleware implements a token bucket algorithm for rate limiting
with an asyncio queue to hold excess requests for gradual processing.
"""

import asyncio
import time
import logging
from typing import Dict, Optional
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class TokenBucket:
    """Token bucket implementation for rate limiting."""
    
    def __init__(self, max_tokens: int, refill_rate: float):
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate  # tokens per second
        self.tokens = max_tokens
        self.last_refill = time.time()
        self._lock = asyncio.Lock()
    
    async def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if successful, False otherwise."""
        async with self._lock:
            now = time.time()
            time_passed = now - self.last_refill
            
            # Refill tokens based on time passed
            tokens_to_add = time_passed * self.refill_rate
            self.tokens = min(self.max_tokens, self.tokens + tokens_to_add)
            self.last_refill = now
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False


class RequestQueue:
    """Async queue for holding excess requests."""
    
    def __init__(self, max_size: int):
        self.queue = asyncio.Queue(maxsize=max_size)
        self.max_size = max_size
        self.processing_rate = 1.0 / 200  # 200 requests per second
    
    async def add_request(self, request_id: str) -> bool:
        """Add request to queue. Returns True if added, False if queue is full."""
        try:
            self.queue.put_nowait(request_id)
            return True
        except asyncio.QueueFull:
            return False
    
    async def process_requests(self):
        """Background task to process requests from queue."""
        while True:
            try:
                # Wait for processing rate timing
                await asyncio.sleep(self.processing_rate)
                
                # Get request from queue (blocking)
                request_id = await self.queue.get()
                
                # Here we would normally process the request
                # For our use case, just removing from queue is enough
                logger.debug(f"Processed queued request: {request_id}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing queued request: {e}")
    
    def size(self) -> int:
        """Get current queue size."""
        return self.queue.qsize()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware with token bucket and queue system."""
    
    def __init__(self, app, max_rps: int, process_rps: int, queue_size: int):
        super().__init__(app)
        self.max_rps = max_rps
        self.process_rps = process_rps
        self.queue_size = queue_size
        
        # Initialize token bucket for rate limiting
        self.token_bucket = TokenBucket(
            max_tokens=max_rps,
            refill_rate=max_rps  # Refill at max rate per second
        )
        
        # Initialize request queue
        self.request_queue = RequestQueue(max_size=queue_size)
        
        # Start background processing task
        self.processing_task = None
        
        logger.info(f"Rate limiting initialized: {max_rps} RPS max, {process_rps} RPS processed, queue size {queue_size}")
    
    async def dispatch(self, request: Request, call_next):
        """Process request through rate limiting system."""
        request_id = f"{request.method}:{request.url.path}:{id(request)}"
        
        # Try to consume a token from the bucket
        if await self.token_bucket.consume():
            # Token available, process request immediately
            return await self._process_request(request, call_next, request_id)
        
        # No token available, try to add to queue
        if await self.request_queue.add_request(request_id):
            # Request queued, wait for processing
            return await self._wait_for_processing(request, call_next, request_id)
        
        # Queue is full, reject request
        return self._reject_request()
    
    async def _process_request(self, request: Request, call_next, request_id: str):
        """Process request immediately."""
        try:
            response = await call_next(request)
            
            # Add rate limiting headers
            response.headers["X-Rate-Limit-Max-RPS"] = str(self.max_rps)
            response.headers["X-Rate-Limit-Process-RPS"] = str(self.process_rps)
            response.headers["X-Rate-Limit-Queue-Size"] = str(self.request_queue.size())
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing request {request_id}: {e}")
            raise
    
    async def _wait_for_processing(self, request: Request, call_next, request_id: str):
        """Wait for queued request to be processed."""
        # For simplicity, we'll process it immediately but respect the rate limit
        # In a more complex implementation, we'd wait for the background processor
        await asyncio.sleep(1.0 / self.process_rps)
        
        try:
            response = await call_next(request)
            
            # Add rate limiting headers
            response.headers["X-Rate-Limit-Max-RPS"] = str(self.max_rps)
            response.headers["X-Rate-Limit-Process-RPS"] = str(self.process_rps)
            response.headers["X-Rate-Limit-Queue-Size"] = str(self.request_queue.size())
            response.headers["X-Rate-Limit-Queued"] = "true"
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing queued request {request_id}: {e}")
            raise
    
    def _reject_request(self):
        """Reject request when queue is full."""
        return JSONResponse(
            status_code=503,
            content={
                "error": "Service temporarily unavailable - rate limit exceeded",
                "message": f"Request queue is full. Maximum {self.queue_size} requests can be queued.",
                "retry_after": "1"
            },
            headers={
                "Retry-After": "1",
                "X-Rate-Limit-Max-RPS": str(self.max_rps),
                "X-Rate-Limit-Process-RPS": str(self.process_rps),
                "X-Rate-Limit-Queue-Size": str(self.queue_size)
            }
        )
    
    async def startup(self):
        """Start background processing task."""
        self.processing_task = asyncio.create_task(self.request_queue.process_requests())
        logger.info("Rate limiting middleware started")
    
    async def shutdown(self):
        """Stop background processing task."""
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
        logger.info("Rate limiting middleware stopped")
