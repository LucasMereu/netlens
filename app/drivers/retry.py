import time
from typing import Callable, List, Type, Any
from app.drivers.errors import NetworkDriverError, TimeoutError, ConnectionError

class OperationSafety:
    READ = "READ"
    SAFE_WRITE = "SAFE_WRITE"
    NON_IDEMPOTENT_WRITE = "NON_IDEMPOTENT_WRITE"

class RetryPolicy:
    def __init__(self, max_attempts: int = 3, initial_backoff: float = 1.0, retryable_exceptions: Optional[List[Type[Exception]]] = None):
        self.max_attempts = max_attempts
        self.initial_backoff = initial_backoff
        self.retryable_exceptions = retryable_exceptions or [TimeoutError, ConnectionError]

    def execute(self, operation_safety: str, func: Callable[..., Any], *args, **kwargs) -> Any:
        attempts = 0
        backoff = self.initial_backoff
        
        while True:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                attempts += 1
                
                # Determine if the exception is retryable
                is_retryable = any(isinstance(e, exc_type) for exc_type in self.retryable_exceptions)
                
                # Determine safety
                if operation_safety == OperationSafety.NON_IDEMPOTENT_WRITE:
                    # Never retry non-idempotent write operations automatically to prevent duplicates/corrupt state
                    raise e
                    
                if not is_retryable or attempts >= self.max_attempts:
                    raise e
                    
                time.sleep(backoff)
                backoff *= 2.0
