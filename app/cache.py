import json
import logging

from redis import Redis
from redis.exceptions import RedisError

from .config import settings


logger = logging.getLogger("eve.cache")
redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


def get_json(key: str):
    try:
        value = redis_client.get(key)
        return json.loads(value) if value else None
    except RedisError:
        logger.warning("cache_read_failed key=%s", key)
        return None


def set_json(key: str, value, ttl: int = 60) -> None:
    try:
        redis_client.setex(key, ttl, json.dumps(value, default=str))
    except RedisError:
        logger.warning("cache_write_failed key=%s", key)


def invalidate(prefix: str) -> None:
    try:
        keys = list(redis_client.scan_iter(match=f"{prefix}*"))
        if keys:
            redis_client.delete(*keys)
    except RedisError:
        logger.warning("cache_invalidation_failed prefix=%s", prefix)

