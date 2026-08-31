import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL")
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")

# In-memory storage fallback for local development or when Redis is unconfigured
_memory_user_states: Dict[int, str] = {}
_memory_submissions: Dict[int, Dict[str, Any]] = {}

_redis_client = None


def get_redis_client():
    """Initializes and returns the async Upstash Redis client if credentials are configured."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    if UPSTASH_URL and UPSTASH_TOKEN:
        try:
            from upstash_redis.asyncio import Redis

            _redis_client = Redis(url=UPSTASH_URL, token=UPSTASH_TOKEN)
            logger.info("Connected to Upstash Redis for persistent storage.")
        except Exception as e:
            logger.error(f"Failed to initialize Upstash Redis client: {e}")
            _redis_client = None

    return _redis_client


async def get_user_state(user_id: int) -> Optional[str]:
    """Retrieves the active conversation state for a given user."""
    redis = get_redis_client()
    if redis:
        try:
            val = await redis.get(f"user_state:{user_id}")
            return val if isinstance(val, str) else (val.decode("utf-8") if val else None)
        except Exception as e:
            logger.error(f"Redis get_user_state error: {e}")

    return _memory_user_states.get(user_id)


async def set_user_state(user_id: int, state: Optional[str]) -> None:
    """Sets or clears the conversation state for a given user."""
    redis = get_redis_client()
    if redis:
        try:
            key = f"user_state:{user_id}"
            if state is None:
                await redis.delete(key)
            else:
                # State expires after 1 hour (3600 seconds) if inactive
                await redis.set(key, state, ex=3600)
            return
        except Exception as e:
            logger.error(f"Redis set_user_state error: {e}")

    if state is None:
        _memory_user_states.pop(user_id, None)
    else:
        _memory_user_states[user_id] = state


async def save_feedback_submission(
    message_id: int, sender_chat_id: int, sender_name: str
) -> None:
    """Saves a forwarded admin-group message mapping to the original user."""
    data = {
        "sender_chat_id": sender_chat_id,
        "sender_name": sender_name,
    }
    redis = get_redis_client()
    if redis:
        try:
            # Retain feedback mapping for 30 days (2592000 seconds)
            await redis.set(f"feedback:{message_id}", json.dumps(data), ex=2592000)
            return
        except Exception as e:
            logger.error(f"Redis save_feedback_submission error: {e}")

    _memory_submissions[message_id] = data


async def get_feedback_submission(message_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves the original sender data for a forwarded admin-group message."""
    redis = get_redis_client()
    if redis:
        try:
            raw = await redis.get(f"feedback:{message_id}")
            if raw:
                return json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode("utf-8"))
        except Exception as e:
            logger.error(f"Redis get_feedback_submission error: {e}")

    return _memory_submissions.get(message_id)


async def delete_feedback_submission(message_id: int) -> None:
    """Deletes a feedback submission mapping after the reply is processed."""
    redis = get_redis_client()
    if redis:
        try:
            await redis.delete(f"feedback:{message_id}")
            return
        except Exception as e:
            logger.error(f"Redis delete_feedback_submission error: {e}")

    _memory_submissions.pop(message_id, None)


def reset_memory_store():
    """Helper to reset in-memory storage during automated testing."""
    _memory_user_states.clear()
    _memory_submissions.clear()
