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

def count_annotated_words(document: dict, entity_type) -> int:
    """Count words marked with a specific annotation."""
    count = 0
    if 'pages' not in document:
        return count
    
    for page in document['pages']:
        for paragraph in page.get('paragraphs', []):
            for word in paragraph.get('words', []):
                if word.get(entity_type, False):
                    count += 1
    
    return count

def extract_annotated_words(document: dict, entity_type) -> list:
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

def prepare_document_for_annotation(validation_doc: dict) -> dict:
    """Prepare document for annotation by setting all annotations to False."""
    import copy
    document = copy.deepcopy(validation_doc)
    
    if 'pages' in document:
        for page in document['pages']:
            for paragraph in page.get('paragraphs', []):
                for word in paragraph.get('words', []):
                    word['isTemei'] = False
                    word['isProba'] = False
                    word['isSelected'] = False
                    word['isCerere'] = False
                    word['isReclamant'] = False
                    word['isParat'] = False
    
    return document

def prepare_document_for_summary(validation_doc: dict) -> dict:
    """Prepare document for summarization by keeping existing annotations."""
    import copy
    document = copy.deepcopy(validation_doc)
    
    document['extraction_type'] = ['isTemei', 'isProba', 'isSelected', 'isCerere', 'isReclamant', 'isParat']#['isTemei', 'isProba', 'isSelected', 'isCerere']
    
    return document

def process_annotation_with_server(document: dict, server_url: str, timeout: int = 300) -> dict:
    """Process a document through the server annotation API and return the result."""
    try:
        response = requests.post(
            f"{server_url}/annotate-document",
            json=document,
            timeout=timeout
        )
        
        if response.status_code != 200:
            print(f"Error submitting document: {response.status_code}")
            print(f"Response: {response.text}")
            return None
        
        task_response = response.json()
        task_id = task_response['task_id']
        print(f"Document submitted with task ID: {task_id}")
        print(task_response.get('status', ''))
        
        max_polls = 60  # 5 minutes with 5-second intervals
        poll_interval = 5
        
        print("Waiting for processing to complete...")
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
            print(status)
            
            if status == 'completed':
                print("Processing completed!")
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
        
        result_response = requests.get(
            f"{server_url}/annotated-document/{task_id}",
            timeout=30
        )
        
        if result_response.status_code != 200:
            print(f"Error retrieving annotated document: {result_response.status_code}")
            return None
        
        result = result_response.json()
        return result.get('document')
        
    except Exception as e:
        print(f"Error processing document: {e}")
        return None

def process_summary_with_server(document: dict, server_url: str, timeout: int = 300) -> dict:
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

def run_annotation_task(args, reference_doc, full_text):
    """Run annotation task and display results."""
    ref_count = count_annotated_words(reference_doc, args.entity_type)
    ref_words = extract_annotated_words(reference_doc, args.entity_type)
    
    print("Preparing document for server processing...")
    processed_input = prepare_document_for_annotation(reference_doc)
    
    print("Sending document to server for annotation...")
    processed_doc = process_annotation_with_server(processed_input, args.server_url, args.timeout)
    
    if processed_doc is None:
        print("Failed to process document through server")
        sys.exit(1)
    
    pred_count = count_annotated_words(processed_doc, args.entity_type)
    pred_words = extract_annotated_words(processed_doc, args.entity_type)
    
    print("\n" + "="*80)
    print(f"ANNOTATION ANALYSIS RESULTS FOR: {args.document_id}")
    if hasattr(args, 'document_type'):
        print(f"Document type: {args.document_type}")
    print("="*80)
    
    print(f"\nENTIRE TEXT:")
    print("-" * 40)
    print(full_text)
    
    print(f"\nSTATISTICS FOR {args.entity_type.upper()}:")
    print("-" * 40)
    print(f"Number of words marked in reference: {ref_count}")
    print(f"Number of words marked by server: {pred_count}")
    
    print(f"\nREFERENCE ANNOTATED TEXT ({args.entity_type}):")
    print("-" * 40)
    if ref_words:
        print(' '.join(ref_words))
    else:
        print("(No words annotated in reference)")
    
    print(f"\nSERVER ANNOTATED TEXT ({args.entity_type}):")
    print("-" * 40)
    if pred_words:
        print(' '.join(pred_words))
    else:
        print("(No words annotated by server)")
    
    print(f"\nCOMPARISON:")
    print("-" * 40)
    ref_set = set(ref_words)
    pred_set = set(pred_words)
    
    correctly_identified = ref_set & pred_set
    missed = ref_set - pred_set
    extra = pred_set - ref_set
    
    if correctly_identified:
        print(f"Correctly identified: {' '.join(sorted(correctly_identified))}")
    if missed:
        print(f"Missed by server: {' '.join(sorted(missed))}")
    if extra:
        print(f"Extra annotations by server: {' '.join(sorted(extra))}")
    
    accuracy_stats = {
        'total_reference': len(ref_set),
        'total_predicted': len(pred_set),
        'correctly_identified': len(correctly_identified),
        'missed': len(missed),
        'extra': len(extra)
    }
    
    if accuracy_stats['total_reference'] > 0:
        recall = accuracy_stats['correctly_identified'] / accuracy_stats['total_reference']
        print(f"\nRecall: {recall:.2%} ({accuracy_stats['correctly_identified']}/{accuracy_stats['total_reference']})")
    
    if accuracy_stats['total_predicted'] > 0:
        precision = accuracy_stats['correctly_identified'] / accuracy_stats['total_predicted']
        print(f"Precision: {precision:.2%} ({accuracy_stats['correctly_identified']}/{accuracy_stats['total_predicted']})")

def run_summary_task(args, reference_doc, full_text):
    """Run summary task and display results."""
    all_annotation_types = ['isTemei', 'isProba', 'isSelected', 'isCerere', 'isReclamant', 'isParat']
    
    annotation_to_summary_field = {
        'isTemei': 'Temei',
        'isProba': 'Proba', 
        'isSelected': 'Selected',
        'isCerere': 'Cerere',
        'isReclamant': 'Reclamant',
        'isParat': 'Parat'
    }
    
    category_names = {
        'isTemei': 'Temeiul Legal',
        'isProba': 'Probele și Dovezile',
        'isSelected': 'Descrierea Faptelor',
        'isCerere': 'Cererea',
        'isReclamant': 'Reclamantul',
        'isParat': 'Pârâtul'
    }
    
    print("Preparing document for server processing...")
    processed_input = prepare_document_for_summary(reference_doc)
    
    print("Sending document to server for summarization...")
    summary_result = process_summary_with_server(processed_input, args.server_url, args.timeout)
    
    if summary_result is None:
        print("Failed to process document through server")
        sys.exit(1)
    
    print("\n" + "="*80)
    print(f"SUMMARY ANALYSIS RESULTS FOR: {args.document_id}")
    if hasattr(args, 'document_type'):
        print(f"Document type: {args.document_type.upper()}")
    print("="*80)
    
    print(f"\nFULL DOCUMENT TEXT:")
    print("-" * 60)
    print(full_text)
    print("\n")
    
    for annotation_type in all_annotation_types:
        category_name = category_names.get(annotation_type, annotation_type)
        summary_field = annotation_to_summary_field.get(annotation_type)
        
        print("="*80)
        print(f"CATEGORY: {category_name} ({annotation_type})")
        print("="*80)
        
        annotated_words = extract_annotated_words(reference_doc, annotation_type)
        
        print(f"\nANNOTATED TEXT IN REFERENCE ({annotation_type}):")
        print("-" * 60)
        if annotated_words:
            annotated_text = ' '.join(annotated_words)
            print(annotated_text)
        else:
            print("(No words annotated in reference for this category)")
        
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

def main():
    """Main function to test a single document."""
    parser = argparse.ArgumentParser(description="Test single document processing")
    parser.add_argument("task_type", 
                       choices=["annotation", "summary"],
                       help="Type of task: annotation or summary")
    parser.add_argument("document_id", 
                       help="Document ID (e.g., 3196_306_2024.json)")
    parser.add_argument("--document-type", "-d",
                       choices=["subpoena", "counterclaim"],
                       help="Type of document: subpoena or counterclaim (used for default validation dir)")
    parser.add_argument("--validation-dir", "-v", 
                       help="Path to validation directory containing JSON files")
    parser.add_argument("--server-url", "-s", 
                       default="http://localhost:8060",
                       help="URL of the document processing server")
    parser.add_argument("--timeout", "-t", 
                       type=int, default=300,
                       help="Timeout in seconds for API calls")
    parser.add_argument("--entity-type", "-e", 
                       default="isProba",
                       help="Entity type to analyze for annotation task (default: isProba)")

    args = parser.parse_args()
    
    if args.validation_dir is None:
        if args.document_type == "subpoena":
            args.validation_dir = "../train/subpoena_validation"
        elif args.document_type == "counterclaim":
            args.validation_dir = "../train/counterclaim_validation"
        else:
            print("Warning: No document type specified, using default validation directory for subpoenas.")
            sys.exit(1)
    
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
        print(f"Loading document: {args.document_id}")
        if hasattr(args, 'document_type') and args.document_type:
            print(f"Document type: {args.document_type}")
        reference_doc = load_document(args.document_id, args.validation_dir)
        
        full_text = extract_document_text(reference_doc)
        
        if args.task_type == "annotation":
            run_annotation_task(args, reference_doc, full_text)
        elif args.task_type == "summary":
            run_summary_task(args, reference_doc, full_text)
        
    except Exception as e:
        print(f"Error during processing: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
