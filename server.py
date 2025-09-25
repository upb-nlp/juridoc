from fastapi import FastAPI, HTTPException
from typing import Dict, Optional, Any
import uuid
from datetime import datetime
import uvicorn
import argparse
import redis
import json
import os
from utils import (
    SUPPORTED_DOCUMENT_TYPES
)

from models import (
    TaskStatus, DocumentRequest, DocumentSummary,
    TaskResponse, TaskStatusResponse, AnnotatedDocumentResponse, SummarizedDocumentResponse
)

from celery_tasks import annotate_document_task, summarize_document_task

app = FastAPI(title="JuriDoc", version="1.0.0")

@app.on_event("startup")
async def startup_event():
    """Test Redis connectivity on startup."""
    try:
        redis_client.ping()
        print("Successfully connected to Redis")
    except Exception as e:
        print(f"Failed to connect to Redis: {e}")
        exit(0)

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

# Task cache expiration time (30 minutes)
TASK_EXPIRATION_SECONDS = 30 * 60  # 30 minutes

def get_task_from_redis(task_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve task data from Redis."""
    try:
        task_data = redis_client.get(f"task:{task_id}")
        if task_data:
            return json.loads(task_data)
        return None
    except Exception as e:
        print(f"Error retrieving task from Redis: {e}")
        return None

def save_task_to_redis(task_id: str, task_data: Dict[str, Any]):
    """Save task data to Redis with expiration."""
    try:
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

def create_initial_task(task_id: str, document: DocumentRequest) -> None:
    initial_task_data = {
        "task_id": task_id,
        "document_id": document.id,
        "created_at": datetime.now().isoformat(),
        "original_document": document.dict(),
        "document": None,
        "summary": None,
        "error": None
    }
    save_task_to_redis(task_id, initial_task_data)

def update_task_status(task_id: str, status: TaskStatus, progress: Optional[str] = None, error: Optional[str] = None, document: Optional[DocumentRequest] = None, summary: Optional[DocumentSummary] = None):
    """Update task status with timestamp and optional progress/error/document/summary information."""
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

@app.post("/annotate-document", response_model=TaskResponse)
async def annotate_document(document: DocumentRequest):
    """
    Submit a document for annotation. Returns a task_id for tracking progress.
    """
    if document.documentTypeName not in SUPPORTED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400, 
            detail=f"Document type '{document.documentTypeName}' is not yet supported. "
                   f"Supported document types: {list(SUPPORTED_DOCUMENT_TYPES.keys())}"
        )
    
    task_id = str(uuid.uuid4())
    
    create_initial_task(task_id, document)
    update_task_status(task_id, TaskStatus.PENDING, progress="Task created")
    
    annotate_document_task.delay(task_id, document.dict())
    
    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message="Document annotation task created successfully"
    )

@app.post("/summarize-document", response_model=TaskResponse)
async def summarize_document(document: DocumentRequest):
    """
    Submit a document for summarization. Returns a task_id for tracking progress.
    """
    if document.documentTypeName not in SUPPORTED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400, 
            detail=f"Document type '{document.documentTypeName}' is not yet supported. "
                   f"Supported document types: {list(SUPPORTED_DOCUMENT_TYPES.keys())}"
        )
    
    task_id = str(uuid.uuid4())
    
    create_initial_task(task_id, document)
    update_task_status(task_id, TaskStatus.PENDING, progress="Task created")
    
    summarize_document_task.delay(task_id, document.dict())
    
    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message="Document summarization task created successfully"
    )

@app.get("/task-status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """Get the current status of a processing task."""
    task = get_task_from_redis(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    status = task["status"]
    if isinstance(status, str):
        try:
            status = TaskStatus(status)
        except ValueError:
            status = TaskStatus.FAILED
    
    return TaskStatusResponse(
        task_id=task_id,
        status=status,
        progress=task.get("progress"),
        created_at=task["created_at"],
        updated_at=task["updated_at"]
    )

@app.get("/annotated-document/{task_id}", response_model=AnnotatedDocumentResponse)
async def get_annotated_document(task_id: str):
    """Retrieve the annotated document when processing is complete."""
    task = get_task_from_redis(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    status = task["status"]
    if isinstance(status, str):
        try:
            status = TaskStatus(status)
        except ValueError:
            status = TaskStatus.FAILED
    
    if status == TaskStatus.FAILED:
        return AnnotatedDocumentResponse(
            task_id=task_id,
            status=status,
            document=None,
            error=task.get("error", "Processing failed")
        )
    
    if status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=202, 
            detail=f"Task {status.value if hasattr(status, 'value') else status} not ready."
        )
    
    result = AnnotatedDocumentResponse(
        task_id=task_id,
        status=status,
        document=task["document"],
        error=None
    )

    try:
        redis_client.delete(f"task:{task_id}")
    except Exception as e:
        print(f"Error deleting task from Redis: {e}")

    return result

@app.get("/summarized-document/{task_id}", response_model=SummarizedDocumentResponse)
async def get_summarized_document(task_id: str):
    """
    Retrieve the summarized document when processing is complete.
    """
    task = get_task_from_redis(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    status = task["status"]
    if isinstance(status, str):
        try:
            status = TaskStatus(status)
        except ValueError:
            status = TaskStatus.FAILED
    
    if status == TaskStatus.FAILED:
        return SummarizedDocumentResponse(
            task_id=task_id,
            status=status,
            summary=None,
            error=task.get("error", "Processing failed")
        )
    
    if status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=202, 
            detail=f"Task {status.value if hasattr(status, 'value') else status} not ready."
        )
    
    result = SummarizedDocumentResponse(
        task_id=task_id,
        status=status,
        summary=task["summary"],
        error=None
    )

    try:
        redis_client.delete(f"task:{task_id}")
    except Exception as e:
        print(f"Error deleting task from Redis: {e}")

    return result

@app.get("/health")
async def health_check():
    """
    Health check endpoint that also verifies Redis connectivity.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {}
    }
    
    try:
        redis_client.ping()
        health_status["services"]["redis"] = "healthy"
    except Exception as e:
        health_status["services"]["redis"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    return health_status

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JuriDoc API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind the server to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8060, help="Port to bind the server to (default: 8060)")
    
    args = parser.parse_args()
    
    uvicorn.run(app, host=args.host, port=args.port)
