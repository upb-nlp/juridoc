import asyncio
import re
import time
import logging
from utils import (
    build_user_prompt_for_task_type, extract_combined_text,
    SUPPORTED_DOCUMENT_TYPES, make_openai_request_async, 
    get_model_for_task_type, get_system_prompt_for_task_type
)

from models import (
    TaskStatus, DocumentRequest
)

# Set up logger
logger = logging.getLogger(__name__)

def find_contiguous_matches(annotated_text, original_words):
    """Find contiguous word sequences that match between annotated and original text"""
    matches = []
    annotated_words = annotated_text.split()
    
    # Find all possible contiguous subsequences in the annotated text
    for start_idx in range(len(annotated_words)):
        for end_idx in range(start_idx + 1, len(annotated_words) + 1):
            # Get the subsequence
            subseq = ' '.join(annotated_words[start_idx:end_idx])
            
            # Find the word positions in the original paragraph
            word_positions = find_word_positions_in_paragraph(subseq, original_words)
            if word_positions:
                matches.extend(word_positions)
    
    return matches


def find_word_positions_in_paragraph(target_text, paragraph_words):
    """Find contiguous word positions that match the target text"""
    target_words = target_text.strip().split()
    if not target_words:
        return []
    
    matches = []
    # Sliding window to find contiguous matches
    for start_pos in range(len(paragraph_words) - len(target_words) + 1):
        # Check if the sequence matches
        match_found = True
        for i, target_word in enumerate(target_words):
            actual_word = paragraph_words[start_pos + i].text.strip()
            # Case-insensitive comparison, also handle punctuation
            if not words_match(actual_word, target_word):
                match_found = False
                break
        
        if match_found:
            # Return the range of word indices that match
            matches.extend(range(start_pos, start_pos + len(target_words)))
    
    return matches


def words_match(word1, word2):
    """Check if two words match, handling punctuation and case"""
    import re
    # Remove common punctuation and convert to lowercase
    clean1 = re.sub(r'[^\w\s]', '', word1.lower())
    clean2 = re.sub(r'[^\w\s]', '', word2.lower())
    return clean1 == clean2


def remove_duplicate_paragraphs_from_end(matches):
    """Remove duplicate paragraphs from the end of the matches list"""
    if len(matches) < 2:
        return matches
    
    i = len(matches) - 1
    while i > 1:
        current = matches[i].strip()
        previous = matches[i-1].strip()
        
        if current == previous:
            matches.pop(i)
        else:
            break
        i -= 1
    
    return matches


def calculate_match_score(annotated_content, paragraph_words, annotated_text_normalized):
    """Calculate normalized match score between annotated content and paragraph"""
    if not paragraph_words:
        return 0
    

    paragraph_text = ' '.join([word.text.strip() for word in paragraph_words]).strip()

    # Quick checks to avoid unnecessary processing
    if len(paragraph_text) < len(annotated_content):
        return 0

    if annotated_text_normalized in paragraph_text:
        return 1.0
    
    # TODO: Improve the logic here, it's a bit itchy, and longer paragraphs
    # are penalized too much
    matching_positions = find_contiguous_matches(annotated_text_normalized, paragraph_words)
    
    unique_matches = len(set(matching_positions))
    total_words = len(paragraph_words)
    
    return unique_matches / total_words if total_words > 0 else 0


def find_best_matching_paragraph(cleaned_content, paragraph_mapping, annotated_document):
    """Find the paragraph with the highest match score for the given content"""
    best_match_score = 0
    best_paragraph_info = None


    annotated_text_normalized = ' '.join(cleaned_content.strip().split()).strip()
    
    for actual_para_num, (page_idx, para_idx) in paragraph_mapping.items():
        page = annotated_document.pages[page_idx]
        paragraph = page.paragraphs[para_idx]
        
        # Get all non-empty words from the paragraph in order
        paragraph_words = [word for word in paragraph.words if word.text.strip()]

        if not paragraph_words:
            continue
        
        # Calculate match score for this paragraph
        match_score = calculate_match_score(cleaned_content, paragraph_words, annotated_text_normalized)

        # End early if a perfect match is found
        if match_score == 1.0:
            return match_score, (page_idx, para_idx, paragraph_words)

        if match_score > best_match_score:
            best_match_score = match_score
            best_paragraph_info = (page_idx, para_idx, paragraph_words)
    
    return best_match_score, best_paragraph_info


async def annotate_document_with_llm(task_id: str, document: DocumentRequest, update_task_status_callback):
    """Background task to annotate a document using an LLM."""
    try:
        update_task_status_callback(task_id, TaskStatus.EXTRACTING_CONTENT, "Extracting text content from pages")
        
        combined_text = extract_combined_text(document)
        
                                    
        all_annotation_types = ['isTemei', 'isProba', 'isSelected', 'isCerere', 'isReclamant', 'isParat']
        
        if document.extraction_type is not None:
            invalid_types = [t for t in document.extraction_type if t not in all_annotation_types]
            if invalid_types:
                raise ValueError(f"Invalid extraction types: {invalid_types}. Valid types are: {all_annotation_types}")
            annotation_types = document.extraction_type
        else:
            annotation_types = all_annotation_types
        
        update_task_status_callback(task_id, TaskStatus.ANNOTATING, f"Annotating document using LLM for types: {', '.join(annotation_types)}")

        doc_type = SUPPORTED_DOCUMENT_TYPES[document.documentTypeName]
        
        async def process_annotation_type(annotation_type):
            try:
                user_content = build_user_prompt_for_task_type(combined_text, annotation_type, "annotation", doc_type)
                model_name = get_model_for_task_type(doc_type, annotation_type, "annotation")
                system_prompt = get_system_prompt_for_task_type(doc_type, "annotation")

                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ]

                # There's a small chance, that the model will loop
                # and generate the maximum number of tokens. We limit
                # it based on the annotation type.
                max_tokens_map = {
                    'isReclamant': 150,
                    'isParat': 150,
                    'isTemei': 400,
                    'isProba': 300,
                    'isCerere': 700,
                    'isSelected': 2300
                }
                max_tokens = max_tokens_map.get(annotation_type, 2300)

                start_time = time.time()

                completion = await make_openai_request_async(
                    model=model_name,
                    temperature=0.2,
                    max_tokens=max_tokens,
                    messages=messages
                )

                end_time = time.time()
                duration = end_time - start_time
                logger.info(f"LLM request completed for {annotation_type} in {duration:.2f} seconds (model: {model_name}) [Case: {document.caseNumber}, Entity: {document.entityId}]")

                response_content = completion.choices[0].message.content
                return annotation_type, response_content

            except Exception as e:
                logger.error(f"Error processing {annotation_type}: {str(e)} [Case: {document.caseNumber}, Entity: {document.entityId}]")
                # We return None for the result to indicate failure, but do not raise
                # an error to allow other tasks to continue.
                return annotation_type, None

        # Run all annotation tasks in parallel
        logger.info(f"Starting parallel processing of {len(annotation_types)} annotation types [Case: {document.caseNumber}, Entity: {document.entityId}]")
        parallel_start_time = time.time()

        annotation_tasks = [process_annotation_type(annotation_type) for annotation_type in annotation_types]
        annotation_results_list = await asyncio.gather(*annotation_tasks, return_exceptions=True)

        parallel_end_time = time.time()
        total_parallel_duration = parallel_end_time - parallel_start_time
        logger.info(f"All LLM requests completed in {total_parallel_duration:.2f} seconds (parallel execution) [Case: {document.caseNumber}, Entity: {document.entityId}]")

        # Filter out any exceptions and convert successful results to dictionary
        annotation_results = {}
        failed_types = []

        for result in annotation_results_list:
            if isinstance(result, Exception):
                logger.warning(f"Task failed with exception: {str(result)}")
                continue
            elif result[1] is None:
                failed_types.append(result[0])
                continue
            else:
                annotation_results[result[0]] = result[1]

        if failed_types:
            logger.warning(f"Failed to process annotation types: {failed_types}")
            # Optionally update status to indicate partial failure
            update_task_status_callback(task_id, TaskStatus.ANNOTATING,
                f"Some annotation types failed: {failed_types}. Processing remaining types: {list(annotation_results.keys())}")
        
        update_task_status_callback(task_id, TaskStatus.ANNOTATING, f"Updating JSON based on LLM output for annotation types: {', '.join(annotation_types)}")
        annotated_document = document.copy(deep=True)
        
        # Process annotations for each page/paragraph/word
        # Create a mapping from paragraph numbers to document structure for efficient lookup
        paragraph_mapping = {}
        current_para_num = 1
        
        for page_idx, page in enumerate(annotated_document.pages):
            for para_idx, paragraph in enumerate(page.paragraphs):
                # Only count paragraphs that have content (non-empty words)
                paragraph_words = [word for word in paragraph.words if word.text.strip()]
                if paragraph_words:
                    paragraph_mapping[current_para_num] = (page_idx, para_idx)
                    current_para_num += 1
        
        # Start timing the annotation processing
        annotation_processing_start_time = time.time()

        for annotation_type, result_text in annotation_results.items():
            if not result_text:
                continue

            para_pattern = r'<p>(.*?)</p>'
            matches = re.findall(para_pattern, result_text, re.DOTALL)
            
            # The model may sometime loop and repeat the same paragraphs at the end.
            # We handle this by removing duplicate paragraphs from the end.
            matches = remove_duplicate_paragraphs_from_end(matches)
            
            # For each paragraph in the model output, we try to find the matching paragraph
            # in the original document and then mark the corresponding words.
            for para_content in matches:
                cleaned_content = para_content.strip()
                if not cleaned_content:
                    continue
                

                best_match_score, best_paragraph_info = find_best_matching_paragraph(
                    cleaned_content, paragraph_mapping, annotated_document
                )

                # If we found a good match (score > 0.1 to avoid random matches), apply annotations
                if best_paragraph_info and best_match_score > 0.1:
                    page_idx, para_idx, paragraph_words = best_paragraph_info
                    
                    # Find all matching word positions for the best paragraph
                    annotated_text_normalized = ' '.join(cleaned_content.split())
                    matching_positions = find_contiguous_matches(annotated_text_normalized, paragraph_words)
                    
                    unique_positions = set(matching_positions)
                    
                    for pos in unique_positions:
                        if pos < len(paragraph_words):
                            word = paragraph_words[pos]
                            if annotation_type == 'isTemei':
                                word.isTemei = True
                            elif annotation_type == 'isProba':
                                word.isProba = True
                            elif annotation_type == 'isSelected':
                                word.isSelected = True
                            elif annotation_type == 'isCerere':
                                word.isCerere = True
                            elif annotation_type == 'isReclamant':
                                word.isReclamant = True
                            elif annotation_type == 'isParat':
                                word.isParat = True
        
        annotation_processing_end_time = time.time()
        annotation_processing_duration = annotation_processing_end_time - annotation_processing_start_time
        logger.info(f"Annotation processing completed in {annotation_processing_duration:.2f} seconds [Case: {document.caseNumber}, Entity: {document.entityId}]")

        update_task_status_callback(task_id, TaskStatus.COMPLETED, "Document processing completed", document=annotated_document)
        
    except Exception as e:
        update_task_status_callback(task_id, TaskStatus.FAILED, error=str(e))
