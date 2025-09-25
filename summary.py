import asyncio
from utils import (
    SUPPORTED_DOCUMENT_TYPES, 
    make_openai_request_async,
    get_prompts_for_task_type,
    get_system_prompt_for_task_type,
    get_model_for_task_type,
    build_user_prompt_for_task_type
)

from models import (
    TaskStatus, DocumentRequest, DocumentSummary
)

# Mapping of annotation types to summary field names in DocumentSummary
ANNOTATION_TO_SUMMARY_FIELD = {
    'isTemei': 'Temei',
    'isProba': 'Proba', 
    'isSelected': 'Selected',
    'isCerere': 'Cerere',
    'isReclamant': 'Reclamant',
    'isParat': 'Parat'
}

def _post_process_iscerere_result(result: str) -> str:
    """Post-process isCerere results to return in the format expected by the
    system.  Specifically, we return a string starting with "a solicitat" or "au
    solicitat" followed by text returned by the model."""
    import re
    
    pattern = r'.*?([aA]u?\s+solicitat.*)'
    
    match = re.search(pattern, result, re.DOTALL)
    if match:
        solicitation_part = match.group(1).strip()
        solicitation_part = re.sub(r'^[aA]u?\s+solicitat', 
                                 lambda m: m.group(0).lower(), 
                                 solicitation_part)
        return solicitation_part
    
    return result

def extract_category_text_from_words(document: DocumentRequest, annotation_type: str) -> str:
    """Extract text for a specific category by iterating through document words directly"""
    category_words = []
    
    for page in document.pages:
        for paragraph in page.paragraphs:
            for word in paragraph.words:
                word_text = word.text.strip() if word.text else ""
                
                if not word_text:
                    continue
                
                is_category_match = hasattr(word, annotation_type) and getattr(word, annotation_type, False)
                
                if is_category_match:
                    category_words.append(word_text)
    
    extracted_text = ' '.join(category_words)
    return extracted_text

async def generate_category_summary(category_text: str, annotation_type: str, document_type: str = "subpoena", additional_context: dict = None) -> str:
    """Generate a summary for a specific category using the extracted category text"""
    try:
        if not category_text.strip():
            return ""
        
        summary_prompts = get_prompts_for_task_type(document_type, "summary")
        
        if annotation_type not in summary_prompts:
            return f"Tip de categorie necunoscut: {annotation_type}"
        
        system_prompt = get_system_prompt_for_task_type(document_type, "summary")
        
        model_name = get_model_for_task_type(document_type, annotation_type, "summary")
        
        user_content = build_user_prompt_for_task_type(category_text, annotation_type, "summary", document_type, additional_context)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        
        completion = await make_openai_request_async(
            model=model_name,
            temperature=0.2,
            max_tokens=3000,
            messages=messages
        )
        
        result = completion.choices[0].message.content.strip()
        
        # Post-process isCerere results for subpoena documents
        if annotation_type == 'isCerere' and document_type == "subpoena":
            result = _post_process_iscerere_result(result)
        
        return result
        
    except Exception as e:
        return f"Error generating summary: {str(e)}"

async def summarize_document_categories(task_id: str, document: DocumentRequest, update_task_status_callback):
    """Background task to process a document and generate category summaries."""
    try:
        summary_annotation_types = ['isTemei', 'isProba', 'isSelected', 'isCerere', 'isReclamant', 'isParat']
        
        if document.extraction_type is not None:
            invalid_types = [t for t in document.extraction_type if t not in summary_annotation_types]
            if invalid_types:
                raise ValueError(f"Invalid extraction types: {invalid_types}. Valid types are: {summary_annotation_types}")
            annotation_types = document.extraction_type
        else:
            annotation_types = summary_annotation_types
        
        update_task_status_callback(task_id, TaskStatus.SUMMARIZING, "Generating category summaries")
        
        doc_type = SUPPORTED_DOCUMENT_TYPES[document.documentTypeName]
        
        # Extract isReclamant text once for potential use in isCerere
        isReclamant_text = extract_category_text_from_words(document, 'isReclamant') if 'isCerere' in annotation_types else None
        
        async def process_category_summary(annotation_type: str):
            """Process summary for a single category"""
            try:
                category_text = extract_category_text_from_words(document, annotation_type)
                
                # Is cerere uses some extra information
                additional_context = None
                if annotation_type == 'isCerere' and isReclamant_text:
                    additional_context = {'isReclamant': isReclamant_text}
                
                summary_text = await generate_category_summary(category_text, annotation_type, doc_type, additional_context)

                return annotation_type, summary_text
            except Exception as e:
                return annotation_type, f"Eroare la procesare: {str(e)}"
        
        update_task_status_callback(
            task_id, 
            TaskStatus.SUMMARIZING, 
            f"Processing summaries for: {', '.join(annotation_types)}"
        )
        
        # Create tasks for annotation types that need summarization and run them in parallel
        summary_tasks = [process_category_summary(annotation_type) for annotation_type in annotation_types]
        
        summary_results_list = await asyncio.gather(*summary_tasks, return_exceptions=True)
        
        # Process results and build the document summary
        summary_fields = {}
        for result in summary_results_list:
            if isinstance(result, Exception):
                print(f"Error in parallel processing: {str(result)}")
                continue
            elif isinstance(result, tuple) and len(result) == 2:
                annotation_type, summary_content = result
                # Map annotation type to DocumentSummary field name
                field_name = ANNOTATION_TO_SUMMARY_FIELD.get(annotation_type)
                if field_name:
                    summary_fields[field_name] = summary_content
        
        document_summary = DocumentSummary(
            id=document.id,
            userId=document.userId,
            email=document.email,
            caseNumber=document.caseNumber,
            entityId=document.entityId,
            documentTypeId=document.documentTypeId,
            documentTypeName=document.documentTypeName,
            attachmentId=document.attachmentId,
            extractedPages=document.extractedPages,
            isGold=document.isGold,
            isManuallyAdnotated=document.isManuallyAdnotated,
            lastSaved=document.lastSaved,
            Temei=summary_fields.get('Temei', ''),
            Proba=summary_fields.get('Proba', ''),
            Selected=summary_fields.get('Selected', ''),
            Cerere=summary_fields.get('Cerere', ''),
            Reclamant=summary_fields.get('Reclamant', ''),
            Parat=summary_fields.get('Parat', '')
        )
        
        update_task_status_callback(
            task_id, 
            TaskStatus.COMPLETED, 
            "Document summarization completed", 
            summary=document_summary
        )
        
    except Exception as e:
        update_task_status_callback(task_id, TaskStatus.FAILED, error=str(e))
