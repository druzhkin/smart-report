from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from loguru import logger
import httpx


def llm_retry(max_attempts: int = 3):
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, TimeoutError, ConnectionError)),
        before_sleep=lambda state: logger.warning(
            f"Retry {state.attempt_number}/{max_attempts} after error: {state.outcome.exception()}"
        ),
        reraise=True,
    )


def api_retry(max_attempts: int = 5):
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        retry=retry_if_exception_type((httpx.HTTPError, TimeoutError, ConnectionError)),
        before_sleep=lambda state: logger.warning(
            f"API retry {state.attempt_number}/{max_attempts} after error: {state.outcome.exception()}"
        ),
        reraise=True,
    )
