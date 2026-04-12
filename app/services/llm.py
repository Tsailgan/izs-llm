import os
import time
from functools import wraps
from langchain_mistralai import ChatMistralAI
from langchain_openai import ChatOpenAI
from app.core.config import settings

def get_llm():
    """Returns the configured Mistral LLM instance."""
    # Use os.environ directly to ensure we get the latest values after dotenv load
    api_key = os.environ.get("MISTRAL_API_KEY", "").strip()
    
    if not api_key:
        print("❌ CRITICAL ERROR: MISTRAL_API_KEY is missing from environment variables!")
        raise ValueError("MISTRAL_API_KEY is not set.")
    
    # Debug: verify key length without exposing the key
    print(f"[LLM] Initializing Mistral with key length: {len(api_key)}")
    
    return ChatMistralAI(
        model=settings.LLM_MODEL,
        api_key=api_key,
        temperature=0.2,
        max_tokens=128000, 
        top_p=0.9,
    )

def get_judge_llm(temperature=0.0):
    """Returns the configured LLM instance for judging/evaluations."""
    base_url = os.environ.get("JUDGE_BASE_URL", "").strip()
    
    return ChatOpenAI(
        base_url=base_url,
        model="Qwen3-Coder-30B",
        temperature=temperature,
        api_key="empty",
        max_retries=6,
        timeout=240
    )

def rate_limit_pause(seconds=20):
    """Manually pause execution to respect Groq's strict free-tier rate limits."""
    print(f"\n⏳ [Rate Limit Protection] Pausing for {seconds} seconds to let Groq reset...")
    time.sleep(seconds)
    print("▶️ Resuming...")

def with_rate_limit_retry(max_attempts=3, delay_seconds=25):
    """
    A decorator to automatically catch Groq rate limit errors (429) 
    and pause before retrying the function.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_str = str(e).lower()
                    if "429" in error_str or "rate limit" in error_str:
                        attempts += 1
                        print(f"\n⚠️ Hit Groq rate limit. Attempt {attempts} of {max_attempts}.")
                        if attempts < max_attempts:
                            rate_limit_pause(delay_seconds)
                        else:
                            print("❌ Max rate limit retries reached. Failing test.")
                            raise e
                    else:
                        raise e
        return wrapper
    return decorator