#!/usr/bin/env python3

import json
import argparse
import sys
from pathlib import Path
import requests

def load_document(document_id: str, validation_dir: str) -> dict:
    validation_path = Path(validation_dir)
    document_file = validation_path / document_id
    
    if not document_file.exists():
        raise FileNotFoundError(f"Document not found: {document_file}")
    
    with open(document_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_document_text(document: dict) -> str:
    """Extract the full text content from a document."""
    if 'pages' not in document:
        return ""
    
    full_text = []
    for page in document['pages']:
        page_text = []
        for paragraph in page.get('paragraphs', []):
            paragraph_text = []
            for word in paragraph.get('words', []):
                word_text = word.get('text', '')
                if word_text:
                    paragraph_text.append(word_text)
            if paragraph_text:
                page_text.append(' '.join(paragraph_text))
        if page_text:
            full_text.append('\n'.join(page_text))
    
    return '\n\n'.join(full_text)

def extract_annotated_words(document: dict, entity_type: str) -> list:
    """Extract the actual words that are annotated for a specific entity type."""
    annotated_words = []
    if 'pages' not in document:
        return annotated_words
    
    for page in document['pages']:
        for paragraph in page.get('paragraphs', []):
            for word in paragraph.get('words', []):
                word_text = word.get('text', '').strip()
                if word_text and word.get(entity_type, False):
                    annotated_words.append(word_text)
    
    return annotated_words

def prepare_document_for_processing(validation_doc: dict) -> dict:
    """Prepare document for processing by keeping existing annotations."""
    import copy
    document = copy.deepcopy(validation_doc)
    
    document['extraction_type'] = ['isTemei', 'isProba', 'isSelected', 'isCerere']
    
    return document

def process_document_with_server(document: dict, server_url: str, timeout: int = 300) -> dict:
    """Process a document through the server summarization API and return the result."""
    try:
        # Submit document for summarization
        response = requests.post(
            f"{server_url}/summarize-document",
            json=document,
            timeout=timeout
        )
        
        if response.status_code != 200:
            print(f"Error submitting document: {response.status_code}")
            print(f"Response: {response.text}")
            return None
        
        task_response = response.json()
        task_id = task_response['task_id']
        print(f"Document submitted for summarization with task ID: {task_id}")
        
        # Poll for completion
        max_polls = 60  # 5 minutes with 5-second intervals
        poll_interval = 5
        
        print("Waiting for summarization to complete...")
        for poll_count in range(max_polls):
            status_response = requests.get(
                f"{server_url}/task-status/{task_id}",
                timeout=30
            )
            
            if status_response.status_code != 200:
                print(f"Error checking task status: {status_response.status_code}")
                return None
            
            status_data = status_response.json()
            status = status_data['status']
            
            if status == 'completed':
                print("Summarization completed!")
                break
            elif status == 'failed':
                print(f"Task failed: {task_id}")
                print(f"Error: {status_data.get('error', 'Unknown error')}")
                return None
            else:
                print(f"Status: {status} (poll {poll_count + 1}/{max_polls})")
            
            import time
            time.sleep(poll_interval)
        else:
            print(f"Task timed out: {task_id}")
            return None
        
        # Get summarized document
        result_response = requests.get(
            f"{server_url}/summarized-document/{task_id}",
            timeout=30
        )
        
        if result_response.status_code != 200:
            print(f"Error retrieving summarized document: {result_response.status_code}")
            return None
        
        result = result_response.json()
        return result.get('summary')
        
    except Exception as e:
        print(f"Error processing document: {e}")
        return None

def main():
    """Main function to test document summarization."""
    parser = argparse.ArgumentParser(description="Test single document summarization")
    parser.add_argument("document_id", 
                       help="Document ID (e.g., 3196_306_2024.json)")
    parser.add_argument("--validation-dir", "-v", 
                       default="../train/subpoena_validation",
                       help="Path to validation directory containing JSON files")
    parser.add_argument("--server-url", "-s", 
                       default="http://localhost:8060",
                       help="URL of the document processing server")
    parser.add_argument("--timeout", "-t", 
                       type=int, default=300,
                       help="Timeout in seconds for API calls")
    
    args = parser.parse_args()
    
    # Test server connection
    try:
        response = requests.get(f"{args.server_url}/health", timeout=30)
        if response.status_code != 200:
            print(f"Warning: Server health check failed with status {response.status_code}")
        else:
            print(f"Server is healthy")
    except Exception as e:
        print(f"Error: Could not connect to server: {e}")
        print("Make sure the server is running before proceeding.")
        sys.exit(1)
    
    try:
        # Load the reference document
        print(f"Loading document: {args.document_id}")
        reference_doc = load_document(args.document_id, args.validation_dir)
        
        # Extract full text
        full_text = extract_document_text(reference_doc)
        
        # All annotation types we want to analyze
        all_annotation_types = ['isTemei', 'isProba', 'isSelected', 'isCerere']
        
        # Mapping from annotation types to summary field names
        annotation_to_summary_field = {
            'isTemei': 'Temei',
            'isProba': 'Proba', 
            'isSelected': 'Selected',
            'isCerere': 'Cerere'
        }
        
        # Category names for display
        category_names = {
            'isTemei': 'Temeiul Legal',
            'isProba': 'Probele și Dovezile',
            'isSelected': 'Descrierea Faptelor',
            'isCerere': 'Cererea'
        }
        
        # Prepare document for processing
        print("Preparing document for server processing...")
        processed_input = prepare_document_for_processing(reference_doc)
        
        # Process through server
        print("Sending document to server for summarization...")
        summary_result = process_document_with_server(processed_input, args.server_url, args.timeout)
        
        if summary_result is None:
            print("Failed to process document through server")
            sys.exit(1)
        
        # Print results
        print("\n" + "="*80)
        print(f"SUMMARY ANALYSIS RESULTS FOR: {args.document_id}")
        print("="*80)
        
        print(f"\nFULL DOCUMENT TEXT:")
        print("-" * 60)
        print(full_text)
        print("\n")
        
        # For each annotation type, show the annotated text and the generated summary
        for annotation_type in all_annotation_types:
            category_name = category_names.get(annotation_type, annotation_type)
            summary_field = annotation_to_summary_field.get(annotation_type)
            
            print("="*80)
            print(f"CATEGORY: {category_name} ({annotation_type})")
            print("="*80)
            
            # Extract annotated words from reference document
            annotated_words = extract_annotated_words(reference_doc, annotation_type)
            
            print(f"\nANNOTATED TEXT IN REFERENCE ({annotation_type}):")
            print("-" * 60)
            if annotated_words:
                annotated_text = ' '.join(annotated_words)
                print(annotated_text)
            else:
                print("(No words annotated in reference for this category)")
            
            # Get the generated summary from the server response
            print(f"\nGENERATED SUMMARY ({summary_field}):")
            print("-" * 60)
            if summary_result and isinstance(summary_result, dict) and summary_field in summary_result:
                summary_content = summary_result.get(summary_field, '')
                if summary_content:
                    print(summary_content)
                else:
                    print("(No summary generated for this category)")
            else:
                print("(Summary not available)")
            
            print("\n")
        
    except Exception as e:
        print(f"Error during processing: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
