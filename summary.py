import asyncio
import time
import logging
import json
import re
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

# Set up logger
logger = logging.getLogger(__name__)

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

def detect_gender_from_document(document: DocumentRequest) -> tuple[str, str]:
    """
    Detect gender clues from the entire document content.
    
    Returns:
        tuple: (target_gender, reason) where target_gender is 'm', 'f', or None
    """
    # Build full document text
    document_words = []
    for page in document.pages:
        for paragraph in page.paragraphs:
            for word in paragraph.words:
                word_text = word.text.strip() if word.text else ""
                if word_text:
                    document_words.append(word_text)
    
    full_text = ' '.join(document_words)
    
    # Check for gender markers
    if "Subsemnatul" in full_text:
        return ("m", "Subsemnatul")
    elif "Subsemnata" in full_text:
        return ("f", "Subsemnata")
    
    return (None, None)

def apply_gender_heuristic_to_reclamant(formatted_json: str, target_gender: str, reason: str, isreclamant_text: str) -> str:
    """
    Apply gender heuristic to isReclamant JSON response.
    
    Args:
        formatted_json: The generated JSON response
        target_gender: Target gender to set ('m' or 'f')
        reason: Reason for gender change
        isreclamant_text: The original isReclamant text for logging
        
    Returns:
        Updated JSON with corrected gender
    """
    try:
        # Parse the JSON response
        reclamants = json.loads(formatted_json)
        
        # Check if it's a list or single object
        if isinstance(reclamants, dict):
            reclamants = [reclamants]
        
        for reclamant in reclamants:
            original_gender = reclamant.get("gen_substantiv", "unknown")
            
            if "gen_substantiv" in reclamant and reclamant["gen_substantiv"] != target_gender:
                logger.info(f"Gender heuristic applied for: {reclamant.get('nume', 'unknown')}")
                logger.info(f"  Original gender: {original_gender} (changed to {target_gender} due to '{reason}')")
                logger.info(f"  IsReclamant text: {isreclamant_text[:100]}...")
            
            # Set gender to target gender
            reclamant["gen_substantiv"] = target_gender
        
        # Return updated JSON (preserve list format if it was a list)
        return json.dumps(reclamants, ensure_ascii=False, indent=2)
        
    except json.JSONDecodeError as e:
        logger.warning(f"Could not parse JSON to apply gender heuristic: {str(e)}")
        return formatted_json

def apply_company_gender_heuristic_to_reclamant(formatted_json: str, isreclamant_text: str) -> str:
    """
    Apply gender heuristic for company names (S.R.L., SRL, S.C., SC -> feminine).
    
    Args:
        formatted_json: The generated JSON response
        isreclamant_text: The original isReclamant text
        
    Returns:
        Updated JSON with corrected gender for companies
    """
    try:
        # Parse the JSON response
        reclamants = json.loads(formatted_json)
        
        # Check if it's a list or single object
        is_single = isinstance(reclamants, dict)
        if is_single:
            reclamants = [reclamants]
        
        for reclamant in reclamants:
            nume = reclamant.get("nume", "")
            original_gender = reclamant.get("gen_substantiv", "unknown")
            
            # Check for company indicators
            nume_upper = nume.upper()
            is_company = False
            company_indicator = ""
            
            # Check if name ends with S.R.L. or SRL
            if nume_upper.endswith("S.R.L.") or nume_upper.endswith("SRL"):
                is_company = True
                company_indicator = "ends with S.R.L./SRL"
            # Check if name starts with S.C. or SC
            elif nume_upper.startswith("S.C.") or nume_upper.startswith("SC ") or nume_upper.startswith("SC."):
                is_company = True
                company_indicator = "starts with S.C./SC"
            
            if is_company and original_gender != "f":
                logger.info(f"Company gender heuristic applied for: {nume}")
                logger.info(f"  Original gender: {original_gender} (changed to f - {company_indicator})")
                logger.info(f"  IsReclamant text: {isreclamant_text[:100]}...")
                reclamant["gen_substantiv"] = "f"
        
        # Return updated JSON (preserve list format if it was a list)
        if is_single:
            return json.dumps(reclamants[0], ensure_ascii=False, indent=2)
        else:
            return json.dumps(reclamants, ensure_ascii=False, indent=2)
        
    except json.JSONDecodeError as e:
        logger.warning(f"Could not parse JSON to apply company gender heuristic: {str(e)}")
        return formatted_json

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

async def generate_category_summary(category_text: str, annotation_type: str, document_type: str = "subpoena", additional_context: dict = None, document: DocumentRequest = None) -> str:
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
        
        start_time = time.time()

        logger.info(f"Sendding LLM request with prompt {messages}")
        
        completion = await make_openai_request_async(
            model=model_name,
            temperature=0.2,
            max_tokens=3000,
            messages=messages
        )
        
        end_time = time.time()
        duration = end_time - start_time
        logger.info(f"LLM request completed for {annotation_type} summary in {duration:.2f} seconds (model: {model_name})")
        
        result = completion.choices[0].message.content.strip()
        
        # Post-process isCerere results for subpoena documents
        if annotation_type == 'isCerere' and document_type == "subpoena":
            result = _post_process_iscerere_result(result)
        
        # Apply gender heuristics for isReclamant
        if annotation_type == 'isReclamant' and document:
            target_gender, reason = detect_gender_from_document(document)
            
            if target_gender:
                result = apply_gender_heuristic_to_reclamant(result, target_gender, reason, category_text)
            
            # Always apply company gender heuristic
            result = apply_company_gender_heuristic_to_reclamant(result, category_text)
        
        return result
        
    except Exception as e:
        logger.error(f"Error generating summary for {annotation_type}: {str(e)}")
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
        
        # Always include isReclamant if isCerere or isSelected is in annotation_types
        if ('isCerere' in annotation_types or 'isSelected' in annotation_types) and 'isReclamant' not in annotation_types:
            annotation_types.insert(0, 'isReclamant')
        elif 'isReclamant' in annotation_types:
            # Ensure isReclamant is first
            annotation_types.remove('isReclamant')
            annotation_types.insert(0, 'isReclamant')
        
        update_task_status_callback(task_id, TaskStatus.SUMMARIZING, "Generating category summaries")
        
        doc_type = SUPPORTED_DOCUMENT_TYPES[document.documentTypeName]
        
        # Process isReclamant first to get the formatted context for isCerere and isSelected
        isReclamant_context_cerere = None
        isReclamant_context_selected = None
        if 'isReclamant' in annotation_types:
            category_text = extract_category_text_from_words(document, 'isReclamant')
            isReclamant_summary = await generate_category_summary(category_text, 'isReclamant', doc_type, None, document)
            
            # Format the isReclamant context for isCerere
            if 'isCerere' in annotation_types:
                isReclamant_context_cerere = format_reclamant_context(isReclamant_summary)
            
            # Format the isReclamant context for isSelected
            if 'isSelected' in annotation_types:
                isReclamant_context_selected = format_reclamant_context_for_selected(isReclamant_summary)
            
            # Store the isReclamant result
            isReclamant_result = ('isReclamant', isReclamant_summary)
        
        async def process_category_summary(annotation_type: str):
            """Process summary for a single category"""
            try:
                category_text = extract_category_text_from_words(document, annotation_type)
                
                # Build additional context for isCerere and isSelected
                additional_context = None
                if annotation_type == 'isCerere' and isReclamant_context_cerere:
                    additional_context = {'isReclamant': isReclamant_context_cerere}
                elif annotation_type == 'isSelected' and isReclamant_context_selected:
                    additional_context = {'isReclamant': isReclamant_context_selected}
                
                summary_text = await generate_category_summary(category_text, annotation_type, doc_type, additional_context, document)

                return annotation_type, summary_text
            except Exception as e:
                logger.error(f"Error processing {annotation_type} summary: {str(e)} [Case: {document.caseNumber}, Entity: {document.entityId}]")
                return annotation_type, f"Eroare la procesare: {str(e)}"
        
        # Remove isReclamant from annotation_types since we already processed it
        remaining_types = [t for t in annotation_types if t != 'isReclamant']
        
        update_task_status_callback(
            task_id, 
            TaskStatus.SUMMARIZING, 
            f"Processing summaries for: {', '.join(annotation_types)}"
        )
        
        # Create tasks for remaining annotation types
        summary_tasks = [process_category_summary(annotation_type) for annotation_type in remaining_types]
        
        logger.info(f"Starting parallel processing of {len(remaining_types)} summary types [Case: {document.caseNumber}, Entity: {document.entityId}]")
        parallel_start_time = time.time()
        
        summary_results_list = await asyncio.gather(*summary_tasks, return_exceptions=True)
        
        # Add isReclamant result to the beginning
        if 'isReclamant' in annotation_types:
            summary_results_list = [isReclamant_result] + list(summary_results_list)
        
        parallel_end_time = time.time()
        total_parallel_duration = parallel_end_time - parallel_start_time
        logger.info(f"All summary LLM requests completed in {total_parallel_duration:.2f} seconds (parallel execution) [Case: {document.caseNumber}, Entity: {document.entityId}]")
        
        summary_fields = {}
        for result in summary_results_list:
            if isinstance(result, Exception):
                logger.warning(f"Summary task failed with exception: {str(result)}")
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
        logger.error(f"Document summarization failed: {str(e)} [Case: {document.caseNumber}, Entity: {document.entityId}]")
        update_task_status_callback(task_id, TaskStatus.FAILED, error=str(e))

def format_reclamant_context(isReclamant_json_str: str) -> str:
    """Format the isReclamant JSON response into context text for isCerere prompt"""
    import json
    
    try:
        reclamanti = json.loads(isReclamant_json_str)
        
        if not isinstance(reclamanti, list) or len(reclamanti) == 0:
            return ""
        
        if len(reclamanti) == 1:
            # Single claimant
            reclamant = reclamanti[0]
            nume = reclamant.get('nume', '')
            gen = reclamant.get('gen_substantiv', 'm')
            
            if gen == 'm':
                return f"""Reclamantul este: {nume}
Textul corectat va incepe cu „a solicitat". Subiectul este la singular, masculin (reclamant)."""
            else:  # 'f' or 'n'
                return f"""Reclamanta este: {nume}
Textul corectat va incepe cu „a solicitat". Subiectul este la singular, feminin (reclamanta)."""
        else:
            # Multiple claimants
            nume_list = [r.get('nume', '') for r in reclamanti]
            nume_str = '; '.join(nume_list)
            return f"""Reclamanții sunt: {nume_str}
Textul corectat va incepe cu „au solicitat". Subiectul este la plural (reclamanții)."""
    
    except json.JSONDecodeError:
        logger.error(f"Failed to parse isReclamant JSON: {isReclamant_json_str}")
        return ""
    except Exception as e:
        logger.error(f"Error formatting reclamant context: {str(e)}")
        return ""

def format_reclamant_context_for_selected(isReclamant_json_str: str) -> str:
    """Format the isReclamant JSON response into context text for isSelected prompt"""
    import json
    
    try:
        reclamanti = json.loads(isReclamant_json_str)
        
        if not isinstance(reclamanti, list) or len(reclamanti) == 0:
            return ""
        
        if len(reclamanti) == 1:
            # Single claimant
            reclamant = reclamanti[0]
            gen = reclamant.get('gen_substantiv', 'm')
            
            if gen == 'm':
                return """Subiectul este SINGULAR, masculin (reclamantul).
Formule juridice directe (singular): „A susținut că", „A arătat că", „A învederat că", „A menționat că", „A invocat faptul că", „A expus faptul că", „A relatat că", „A precizat că"
Construcții cu pronume de politeță (singular): „Acesta a susținut că", „Acesta a menționat că", „Acesta a precizat că", „Acesta a arătat că"
Conectori de continuitate: „Mai susține că" (singular)
Expresii raportative indirecte: „Potrivit acestuia" (singular), „Astfel cum a expus" (singular)"""
            else:  # 'f' or 'n'
                return """Subiectul este SINGULAR, feminin (reclamanta).
Formule juridice directe (singular): „A susținut că", „A arătat că", „A învederat că", „A menționat că", „A invocat faptul că", „A expus faptul că", „A relatat că", „A precizat că"
Construcții cu pronume de politeță (singular): „Aceasta a susținut că", „Aceasta a menționat că", „Aceasta a precizat că", „Aceasta a arătat că"
Conectori de continuitate: „Mai susține că" (singular)
Expresii raportative indirecte: „Potrivit acesteia" (singular), „Astfel cum a expus" (singular)"""
        else:
            # Multiple claimants
            return """Subiectul este PLURAL (reclamanții).
Formule juridice directe (plural): „Au susținut că", „Au arătat că", „Au învederat că", „Au menționat că", „Au invocat faptul că", „Au expus faptul că", „Au relatat că", „Au precizat că"
Construcții cu pronume de politeță (plural): „Aceștia au susținut că", „Aceștia au menționat că", „Aceștia au precizat că", „Aceștia au arătat că"
Conectori de continuitate: „Mai susțin că" (plural)
Expresii raportative indirecte: „Potrivit acestora" (plural), „Astfel cum au expus" (plural)"""
    
    except json.JSONDecodeError:
        logger.error(f"Failed to parse isReclamant JSON: {isReclamant_json_str}")
        return ""
    except Exception as e:
        logger.error(f"Error formatting reclamant context for selected: {str(e)}")
        return ""
