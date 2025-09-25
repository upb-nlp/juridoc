from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    EXTRACTING_CONTENT = "extracting_content"
    ANNOTATING = "annotating"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"

# Pydantic models for request/response
class Word(BaseModel):
    id: str
    text: str
    left: int
    top: int
    width: int
    height: int
    isSelected: bool = False
    isProba: bool = False
    isExceptie: bool = False
    isTemei: bool = False
    isCerere: bool = False
    isReclamant: bool = False
    isParat: bool = False

class Paragraph(BaseModel):
    id: str
    words: List[Word]

class Page(BaseModel):
    width: int
    height: int
    pageNumber: int
    paragraphs: List[Paragraph]

class DocumentRequest(BaseModel):
    id: str
    userId: str
    email: str
    caseNumber: str
    entityId: int
    documentTypeId: int
    documentTypeName: str
    attachmentId: int
    extractedPages: List[int]
    extractedContent: str
    content: str
    pages: List[Page]
    isGold: bool = False
    isManuallyAdnotated: bool = False
    lastSaved: str
    extraction_type: Optional[List[str]] = None

class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    message: str

class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress: Optional[str] = None
    created_at: str
    updated_at: str

class ProcessedDocumentResponse(BaseModel):
    task_id: str
    status: TaskStatus
    document: Optional[DocumentRequest] = None
    error: Optional[str] = None

class DocumentSummary(BaseModel):
    id: str
    userId: str
    email: str
    caseNumber: str
    entityId: int
    documentTypeId: int
    documentTypeName: str
    attachmentId: int
    extractedPages: List[int]
    isGold: bool
    isManuallyAdnotated: bool
    lastSaved: str
    # Summary fields
    Temei: str = ""
    Proba: str = ""
    Selected: str = ""
    Cerere: str = ""
    Reclamant: str = ""
    Parat: str = ""

class SummarizedDocumentResponse(BaseModel):
    task_id: str
    status: TaskStatus
    summary: Optional[DocumentSummary] = None
    error: Optional[str] = None

class AnnotatedDocumentResponse(BaseModel):
    task_id: str
    status: TaskStatus
    document: Optional[DocumentRequest] = None
    error: Optional[str] = None
