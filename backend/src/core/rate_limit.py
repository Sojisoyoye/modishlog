"""Application-level rate limiter using slowapi (in-memory backend for single-server deployments)."""

from slowapi import Limiter
from slowapi.util import get_remote_address

# In-memory storage: each gunicorn worker maintains independent counters.
# With 2 workers a client can make 2× the configured limit before hitting 429.
# To share state across workers, pass storage_uri="redis://redis:6379" once
# Redis is in the production stack.
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
