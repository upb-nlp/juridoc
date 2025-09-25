import asyncio
import json
from celery_config import celery_app
from models import TaskStatus, DocumentRequest, DocumentSummary
from annotate import annotate_document_with_llm
from summary import summarize_document_categories
import redis
import os


# Redis client for task status updates
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", "6379"))
redis_db = int(os.getenv("REDIS_DB", "0"))
redis_password = os.getenv("REDIS_PASSWORD", None)

redis_client = redis.Redis(
    host=redis_host,
    port=redis_port,
    db=redis_db,
    password=redis_password,
    decode_responses=True
)

TASK_EXPIRATION_SECONDS = 30 * 60  # 30 minutes


def get_task_from_redis(task_id: str):
    """Retrieve task data from Redis."""
    try:
        task_data = redis_client.get(f"task:{task_id}")
        if task_data:
            return json.loads(task_data)
        return None
    except Exception as e:
        print(f"Error retrieving task from Redis: {e}")
        return None


def save_task_to_redis(task_id: str, task_data: dict):
    """Save task data to Redis with expiration."""
    try:
        # Convert Pydantic models to dict for JSON serialization
        serializable_data = {}
        for key, value in task_data.items():
            if hasattr(value, 'dict'):
                serializable_data[key] = value.dict()
            elif hasattr(value, '__dict__'):
                serializable_data[key] = value.__dict__
            else:
                serializable_data[key] = value
        
        redis_client.setex(
            f"task:{task_id}",
            TASK_EXPIRATION_SECONDS,
            json.dumps(serializable_data, default=str)
        )
    except Exception as e:
        print(f"Error saving task to Redis: {e}")


def update_task_status(task_id: str, status: TaskStatus, progress: str = None, error: str = None, document: DocumentRequest = None, summary: DocumentSummary = None):
    """Update task status with timestamp and optional progress/error/document/summary information."""
    from datetime import datetime
    
    task_data = get_task_from_redis(task_id)
    if not task_data:
        return
    
    task_data["status"] = status.value if hasattr(status, 'value') else str(status)
    task_data["updated_at"] = datetime.now().isoformat()
    
    if progress is not None:
        task_data["progress"] = progress
    
    if error is not None:
        task_data["error"] = error
    
    if document is not None:
        task_data["document"] = document.dict() if hasattr(document, 'dict') else document
    
    if summary is not None:
        task_data["summary"] = summary.dict() if hasattr(summary, 'dict') else summary
    
    save_task_to_redis(task_id, task_data)


def run_async_task(coro):
    """Helper function to run async functions in Celery tasks."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(coro)


@celery_app.task(bind=True, name="celery_tasks.annotate_document_task")
def annotate_document_task(self, task_id: str, document_data: dict):
    """Celery task to annotate a document using LLM."""
    try:
        document = DocumentRequest(**document_data)
        
        update_task_status(task_id, TaskStatus.PROCESSING, "Starting document annotation")
        
        run_async_task(annotate_document_with_llm(task_id, document, update_task_status))
        
        return {"status": "completed", "task_id": task_id}
        
    except Exception as e:
        error_msg = str(e)
        print(f"Error in annotate_document_task: {error_msg}")
        update_task_status(task_id, TaskStatus.FAILED, error=error_msg)
        raise self.retry(exc=e, countdown=60, max_retries=3)


@celery_app.task(bind=True, name="celery_tasks.summarize_document_task")
def summarize_document_task(self, task_id: str, document_data: dict):
    """Celery task to summarize a document."""
    try:
        document = DocumentRequest(**document_data)
        
        update_task_status(task_id, TaskStatus.PROCESSING, "Starting document summarization")
        
        run_async_task(summarize_document_categories(task_id, document, update_task_status))
        
        return {"status": "completed", "task_id": task_id}
        
    except Exception as e:
        error_msg = str(e)
        print(f"Error in summarize_document_task: {error_msg}")
        update_task_status(task_id, TaskStatus.FAILED, error=error_msg)
        raise self.retry(exc=e, countdown=60, max_retries=3)