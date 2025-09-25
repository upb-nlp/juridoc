import os
from celery import Celery

# Redis configuration from environment variables
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", "6379"))
redis_db = int(os.getenv("REDIS_DB", "0"))
redis_password = os.getenv("REDIS_PASSWORD", None)

# Build Redis URL
if redis_password:
    redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
else:
    redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"

# Create Celery instance
celery_app = Celery(
    "juridoc",
    broker=redis_url,
    backend=redis_url,
    include=["celery_tasks"]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    result_expires=3600,  # Results expire after 1 hour
    task_routes={
        "celery_tasks.annotate_document_task": {"queue": "document_processing"},
        "celery_tasks.summarize_document_task": {"queue": "document_processing"},
    },
)

if __name__ == "__main__":
    celery_app.start()