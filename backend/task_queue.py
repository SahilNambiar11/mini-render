from redis import Redis
from rq import Queue

redis_conn = Redis(host="127.0.0.1", port=6379, decode_responses=False)

deployment_queue = Queue("deployments", connection=redis_conn)