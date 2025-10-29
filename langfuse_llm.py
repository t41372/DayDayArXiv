"""
Asynchronous LLM client with rate limiting and Langfuse tracing.

This module provides an asynchronous wrapper around the OpenAI API with built-in
rate limiting, retries, and Langfuse tracing capabilities.
"""

import os
import time
import asyncio
from typing import Optional

from loguru import logger
from openai import RateLimitError
from openai.types.chat import ChatCompletion
from langfuse.openai import AsyncOpenAI, OpenAI
from langfuse.decorators import observe, langfuse_context

from prompts.tldr_prompt import (
    TLDR_SYSTEM_PROMPT,
    TLDR_USER_EXAMPLE,
    TLDR_ASSISTANT_EXAMPLE,
)
from prompts.translate_title_prompt import (
    TRANSLATE_TITLE_SYSTEM_PROMPT,
    TRANSLATE_TITLE_USER_EXAMPLE,
    TRANSLATE_TITLE_ASSISTANT_EXAMPLE,
)
from prompts.daily_summary_prompt import (
    get_daily_summary_system_prompt,
    DAILY_SUMMARY_USER_INSTRUCTION,
)


class RateLimiter:
    """
    Rate limiter for API calls implementing traffic shaping (smooth request distribution)
    
    This class ensures that API requests are evenly distributed over time rather than sent
    in bursts, which is more respectful to API providers and helps avoid rate limit triggers.
    
    The mechanism works as follows:
    1. Each request must wait at least `interval` seconds since the last request
    2. Multiple concurrent tasks coordinate through a shared lock
    3. This creates a "smooth" request pattern rather than "burst" patterns
    
    Example: With rpm=300, interval=0.2s, so requests are spaced 0.2s apart regardless
    of how many concurrent tasks are waiting.
    """

    def __init__(self, rpm: int = 20):
        """
        Initialize the rate limiter

        Args:
            rpm: Requests per minute (will be smoothly distributed)
        """
        self.rpm = rpm
        self.interval = 60.0 / rpm  # seconds per request - this creates the smooth spacing
        self.last_request_time = 0.0
        # Critical: This lock ensures only one task can "reserve" a time slot at once
        # Without this lock, multiple tasks arriving simultaneously would all see the
        # same last_request_time and proceed together, violating the rate limit
        self.lock = asyncio.Lock()

    async def wait_for_capacity(self) -> None:
        """Wait until there's capacity to make another request"""
        async with self.lock:
            now = time.time()
            time_since_last = now - self.last_request_time

            if time_since_last < self.interval:
                wait_time = self.interval - time_since_last
                logger.debug(f"Rate limiter: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)

            self.last_request_time = time.time()


class AsyncLLM:
    """Asynchronous LLM client with rate limiting and Langfuse tracing"""

    def __init__(
        self,
        model: Optional[str] = None,
        model_strong: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url_strong: Optional[str] = None,
        api_key_strong: Optional[str] = None,
        rpm: int = 20,
        rpm_strong: int = 10,
        max_retries: int = 3,
        retry_delay: int = 2,
    ):
        """
        Initialize the LLM client

        Args:
            model: Default model for standard requests
            model_strong: More capable model for complex tasks
            base_url: Base URL for the OpenAI API (weak model)
            api_key: API key for the OpenAI API (weak model)
            base_url_strong: Base URL for the OpenAI API (strong model)
            api_key_strong: API key for the OpenAI API (strong model)
            rpm: Maximum requests per minute for weak model (rate limit)
            rpm_strong: Maximum requests per minute for strong model (rate limit)
            max_retries: Maximum number of retries for failed requests
            retry_delay: Delay between retries in seconds
        """
        # Use provided values or get from environment for weak model
        self.model = model or os.environ.get("LLM_MODEL")
        base_url = base_url or os.environ.get("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        rpm = rpm or int(os.environ.get("LLM_RPM", 20))

        # Use provided values or get from environment for strong model
        self.model_strong = model_strong or os.environ.get("LLM_MODEL_STRONG")
        base_url_strong = base_url_strong or os.environ.get("OPENAI_API_BASE_URL_STRONG", base_url)
        api_key_strong = api_key_strong or os.environ.get("OPENAI_API_KEY_STRONG", api_key)
        rpm_strong = rpm_strong or int(os.environ.get("LLM_RPM_STRONG", 10))

        # Configuration
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Create AsyncOpenAI client for weak model
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

        # Create AsyncOpenAI client for strong model
        self.client_strong = AsyncOpenAI(
            api_key=api_key_strong,
            base_url=base_url_strong,
        )

        # Sync clients for testing or synchronous fallback
        self.sync_client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

        self.sync_client_strong = OpenAI(
            api_key=api_key_strong,
            base_url=base_url_strong,
        )

        # Initialize session ID with current UTC date
        self.session_id = (
            time.strftime("%Y-%m-%d_%H-%M", time.gmtime())
            + "_"
            + os.environ.get("LANGFUSE_SESSION_NOTE", "dev-1")
            + "_"
            + (self.model or "unknown_model?")
        )

        # Rate limiters for both models
        self.rate_limiter = RateLimiter(rpm=rpm)
        self.rate_limiter_strong = RateLimiter(rpm=rpm_strong)

        logger.info(
            f"Initializing AsyncLLM: weak_model={self.model} (rpm={rpm}), "
            f"strong_model={self.model_strong} (rpm={rpm_strong}), "
            f"max_retries={max_retries}, session_id={self.session_id}"
        )

    @observe()
    async def _create_chat_completion_with_retry(
        self, use_strong_model: bool = False, **kwargs
    ) -> str | None:
        """Helper method that handles retries and rate limiting for API calls

        Args:
            use_strong_model: Whether to use the strong model client
            **kwargs: Arguments to pass to the chat completion API.
                      Must include 'model' and 'messages'.
        Returns:
            The generated text
        """
        langfuse_context.update_current_trace(session_id=self.session_id)
        
        # Select appropriate client and rate limiter
        client = self.client_strong if use_strong_model else self.client
        rate_limiter = self.rate_limiter_strong if use_strong_model else self.rate_limiter
        model_type = "strong" if use_strong_model else "weak"

        last_exception: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                # Wait for rate limiter before making the request
                await rate_limiter.wait_for_capacity()

                # Make the API call
                logger.debug(f"Making API call with {model_type} model (attempt {attempt + 1}/{self.max_retries + 1})")
                response: ChatCompletion = await client.chat.completions.create(**kwargs)
                
                content: Optional[str] = None
                if response.choices and response.choices[0].message:
                    content = response.choices[0].message.content
                
                if content and content.strip():
                    return content # Successfully got content
                
                # Content is None or malformed response from LLM
                last_exception = ValueError(f"LLM ({model_type} model) returned empty content or malformed response.")
                logger.warning(f"{str(last_exception)} Attempt {attempt + 1}/{self.max_retries + 1}.")
                # Fall through to common retry delay logic if not last attempt

            except RateLimitError as e:
                last_exception = e
                logger.warning(
                    f"Rate limit exceeded for {model_type} model (attempt {attempt + 1}/{self.max_retries + 1}): "
                    f"{str(e)}. Retrying if attempts remain..."
                )
            except Exception as e:
                last_exception = e
                logger.warning(
                    f"API call failed for {model_type} model (attempt {attempt + 1}/{self.max_retries + 1}): "
                    f"{str(e)}. Retrying if attempts remain..."
                )

            # If this is the last attempt, break and handle failure outside loop
            if attempt >= self.max_retries:
                break 
            
            # Common retry delay logic
            # Exponential backoff, first retry waits self.retry_delay seconds
            wait_time = self.retry_delay * (2**attempt if attempt > 0 else 1) 
            logger.info(f"Retrying API call for {model_type} model in {wait_time:.2f} seconds...")
            await asyncio.sleep(wait_time)

        # After all attempts, if we are here, it means all attempts failed.
        logger.error(
            f"API call for {model_type} model failed after {self.max_retries + 1} attempts. Last error: {str(last_exception)}"
        )
        
        # If the loop finished due to exhausting retries for None content
        if isinstance(last_exception, ValueError) and "LLM returned None content" in str(last_exception):
            return None # Return None as the final outcome for None content after retries
        
        # If an API/network exception occurred and was the last error
        if isinstance(last_exception, (RateLimitError, Exception)): # Catches other OpenAI errors or general exceptions
             raise last_exception 
        
        return None # Fallback if last_exception was somehow None (should not happen with this logic)

    @observe()
    async def tldr(self, title: str, abstract: str) -> str | None:
        """Generate a TLDR summary in Chinese for a paper

        Args:
            title: Paper title
            abstract: Paper abstract

        Returns:
            TLDR summary in Chinese
        """
        logger.info(f"Generating TLDR for title: {title}")

        messages = [
            {"role": "system", "content": TLDR_SYSTEM_PROMPT},
            {"role": "user", "content": TLDR_USER_EXAMPLE},
            {"role": "assistant", "content": TLDR_ASSISTANT_EXAMPLE},
            {
                "role": "user",
                "content": f"""# Paper Title:
```
{title}
```

# Abstract:
```
{abstract}
```
""",
            },
        ]

        return await self._create_chat_completion_with_retry(
            model=self.model,
            temperature=0.5,
            messages=messages,
            use_strong_model=False,
        )

    @observe()
    async def translate_title(self, title: str, abstract: str) -> str | None:
        """Translate a paper title to Chinese

        Args:
            title: Paper title
            abstract: Paper abstract (for context)

        Returns:
            Translated title in Chinese
        """
        logger.info(f"Translating title: {title}")

        messages = [
            {"role": "system", "content": TRANSLATE_TITLE_SYSTEM_PROMPT},
            {"role": "user", "content": TRANSLATE_TITLE_USER_EXAMPLE},
            {"role": "assistant", "content": TRANSLATE_TITLE_ASSISTANT_EXAMPLE},
            {
                "role": "user",
                "content": f"""# Paper Title:
```
{title}
```

# Abstract:
```
{abstract}
```
""",
            },
        ]

        return await self._create_chat_completion_with_retry(
            model=self.model,
            temperature=0.5,
            messages=messages,
            use_strong_model=False,
        )

    @observe()
    async def tldr_for_all_papers(self, paper_string: str, date_str: str) -> str | None:
        """Generate a daily summary for all papers

        Args:
            paper_string: String containing all paper info
            date_str: Date string for context

        Returns:
            Daily summary in Chinese
        """
        logger.info("Generating daily summary for all papers")

        system_prompt = get_daily_summary_system_prompt(target_date_str=date_str)

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"{paper_string}\n{DAILY_SUMMARY_USER_INSTRUCTION}",
            },
        ]

        return await self._create_chat_completion_with_retry(
            model=self.model_strong,
            temperature=0.5,
            messages=messages,
            use_strong_model=True,
        )
