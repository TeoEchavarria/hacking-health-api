import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from src._config.logger import get_logger

logger = get_logger("api.middleware")

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Get client IP
        client_host = request.client.host if request.client else "unknown"
        
        # Log Request Start
        logger.info(f"Incoming Request: {request.method} {request.url.path} | Client: {client_host}")
        
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # Log Response details
            log_msg = (
                f"Completed: {request.method} {request.url.path} "
                f"| Status: {response.status_code} "
                f"| Duration: {process_time:.3f}s"
            )
            
            if response.status_code >= 400:
                logger.error(log_msg)
            else:
                logger.info(log_msg)
            
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                f"Failed: {request.method} {request.url.path} "
                f"| Duration: {process_time:.3f}s "
                f"| Error: {str(e)}",
                exc_info=True
            )
            raise
