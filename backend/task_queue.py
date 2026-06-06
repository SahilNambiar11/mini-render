import os
from redis import Redis
from rq import Queue

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

redis_conn = Redis.from_url(REDIS_URL)
deployment_queue = Queue("deployments", connection=redis_conn)