from typing import List, Dict
import asyncio
import os
from openai import OpenAI, AsyncOpenAI
from doc_types.subpoena import (
    get_subpoena_annotation_prompts, 
    get_subpoena_summary_prompts,
    get_subpoena_annotation_model_config, 
    get_subpoena_summary_model_config,
    get_subpoena_annotation_system_prompt,
    get_subpoena_summary_system_prompt
)
from doc_types.counterclaim import (
    get_counterclaim_annotation_prompts,
    get_counterclaim_summary_prompts,
    get_counterclaim_annotation_model_config,
    get_counterclaim_summary_model_config,
    get_counterclaim_annotation_system_prompt,
    get_counterclaim_summary_system_prompt
)

# Supported document types
SUPPORTED_DOCUMENT_TYPES = {
    "Cerere de chemare în judecată": "subpoena",
    "Întâmpinare": "counterclaim"
}

# Task types
TASK_TYPES = ["annotation", "summary"]

ANNOTATION_PROMPTS = {
    "subpoena": get_subpoena_annotation_prompts(),
    "counterclaim": get_counterclaim_annotation_prompts()
}

SUMMARY_PROMPTS = {
    "subpoena": get_subpoena_summary_prompts(),
    "counterclaim": get_counterclaim_summary_prompts()
}

ANNOTATION_MODEL_CONFIGS = {
    "subpoena": get_subpoena_annotation_model_config(),
    "counterclaim": get_counterclaim_annotation_model_config()
}

SUMMARY_MODEL_CONFIGS = {
    "subpoena": get_subpoena_summary_model_config(),
    "counterclaim": get_counterclaim_summary_model_config()
}

ANNOTATION_SYSTEM_PROMPTS = {
    "subpoena": get_subpoena_annotation_system_prompt(),
    "counterclaim": get_counterclaim_annotation_system_prompt()
}

SUMMARY_SYSTEM_PROMPTS = {
    "subpoena": get_subpoena_summary_system_prompt(),
    "counterclaim": get_counterclaim_summary_system_prompt()
}

# Backwards compatibility
REQUEST_PROMPTS = ANNOTATION_PROMPTS
MODEL_CONFIGS = ANNOTATION_MODEL_CONFIGS
SYSTEM_PROMPTS = ANNOTATION_SYSTEM_PROMPTS

# Get VLLM endpoint from environment variable, default to localhost:9020
VLLM_ENDPOINT = os.getenv("VLLM_ENDPOINT", "http://localhost:9020/v1")

VLLM_TIMEOUT = int(os.getenv("VLLM_TIMEOUT", "500"))  # 8.3 minutes default

# Keep the sync client for backwards compatibility
client = OpenAI(
    base_url=VLLM_ENDPOINT,
    api_key="EMPTY",
)

# Async client for better performance
async_client = AsyncOpenAI(
    base_url=VLLM_ENDPOINT,
    api_key="EMPTY",
    timeout=VLLM_TIMEOUT
)

def get_prompts_for_task_type(document_type: str, task_type: str) -> dict:
    """Get prompts for a specific document type and task type"""
    if task_type == "annotation":
        if document_type not in ANNOTATION_PROMPTS:
            raise ValueError(f"Unsupported document type: {document_type}. Supported types: {list(ANNOTATION_PROMPTS.keys())}")
        return ANNOTATION_PROMPTS[document_type]
    elif task_type == "summary":
        if document_type not in SUMMARY_PROMPTS:
            raise ValueError(f"Unsupported document type: {document_type}. Supported types: {list(SUMMARY_PROMPTS.keys())}")
        return SUMMARY_PROMPTS[document_type]
    else:
        raise ValueError(f"Unsupported task type: {task_type}. Supported types: {TASK_TYPES}")

def get_model_for_task_type(document_type: str, annotation_type: str, task_type: str) -> str:
    """Get model name for a specific document type, annotation type, and task type"""
    if task_type == "annotation":
        if document_type not in ANNOTATION_MODEL_CONFIGS:
            raise ValueError(f"Unsupported document type: {document_type}. Supported types: {list(ANNOTATION_MODEL_CONFIGS.keys())}")
        model_config = ANNOTATION_MODEL_CONFIGS[document_type]
    elif task_type == "summary":
        if document_type not in SUMMARY_MODEL_CONFIGS:
            raise ValueError(f"Unsupported document type: {document_type}. Supported types: {list(SUMMARY_MODEL_CONFIGS.keys())}")
        model_config = SUMMARY_MODEL_CONFIGS[document_type]
    else:
        raise ValueError(f"Unsupported task type: {task_type}. Supported types: {TASK_TYPES}")
    
    if annotation_type not in model_config:
        raise ValueError(f"Unknown annotation type '{annotation_type}' for document type '{document_type}' and task type '{task_type}'. Available types: {list(model_config.keys())}")
    
    return model_config[annotation_type]

def get_system_prompt_for_task_type(document_type: str, task_type: str) -> str:
    """Get system prompt for a specific document type and task type"""
    if task_type == "annotation":
        if document_type not in ANNOTATION_SYSTEM_PROMPTS:
            raise ValueError(f"Unsupported document type: {document_type}. Supported types: {list(ANNOTATION_SYSTEM_PROMPTS.keys())}")
        return ANNOTATION_SYSTEM_PROMPTS[document_type]
    elif task_type == "summary":
        if document_type not in SUMMARY_SYSTEM_PROMPTS:
            raise ValueError(f"Unsupported document type: {document_type}. Supported types: {list(SUMMARY_SYSTEM_PROMPTS.keys())}")
        return SUMMARY_SYSTEM_PROMPTS[document_type]
    else:
        raise ValueError(f"Unsupported task type: {task_type}. Supported types: {TASK_TYPES}")

def extract_combined_text(document):
    """Extract and combine text content from the list of words of a document.
    Append <p> tags for each paragraph."""
    paragraph_texts = []
    
    for page in document.pages:
        for paragraph in page.paragraphs:
            paragraph_words = []
            for word in paragraph.words:
                word_text = word.text

                if not word_text:
                    continue

                paragraph_words.append(word_text)
            
            if paragraph_words:
                paragraph_content = ' '.join(paragraph_words)
                paragraph_texts.append(f"<p> {paragraph_content} </p>")
    
    return ' '.join(paragraph_texts)


def build_user_prompt_for_task_type(document_text: str, annotation_type: str, task_type: str, document_type: str = "subpoena", additional_context: Dict[str, str] = None) -> str:
    """Build user prompt for LLM based on document text, annotation type, task type and document type"""
    prompts = get_prompts_for_task_type(document_type, task_type)
    
    if annotation_type not in prompts:
        raise ValueError(f"Unknown annotation type '{annotation_type}' for document type '{document_type}' and task type '{task_type}'. Available types: {list(prompts.keys())}")
    
    prompt_template = prompts[annotation_type]
    
    # Format the prompt with additional context if provided
    if additional_context:
        try:
            prompt_template = prompt_template.format(**additional_context)
        except KeyError as e:
            # If formatting fails, use original template
            pass
    
    return f"""## Document Text

{document_text}

## Request
{prompt_template}"""

async def make_openai_request_async(model: str, messages: List[Dict], temperature: float, max_tokens):
    """Async wrapper for OpenAI API calls with proper timeout handling"""
    try:
        completion = await asyncio.wait_for(
            async_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            ),
            timeout=VLLM_TIMEOUT
        )
        return completion
    except asyncio.TimeoutError:
        raise Exception(f"Request to VLLM endpoint timed out after {VLLM_TIMEOUT} seconds")
    except Exception as e:
        raise Exception(f"VLLM request failed: {str(e)}")