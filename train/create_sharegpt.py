#!/usr/bin/env python3
"""
Script to convert document datasets to ShareGPT format.

Supports multiple document types (subpoenas, counterclaims, etc.) and creates
training examples for each category (isTemei, isProba, isSelected, etc.)
with appropriate system prompts and content extraction tasks.

Usage:
    python create_subpoena_sharegpt.py --doc_type subpoena
    python create_subpoena_sharegpt.py --doc_type counterclaim
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Any
import logging
import sys
import argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import get_system_prompt_for_task_type, build_user_prompt_for_task_type

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_document_data(file_path: Path) -> Dict[str, Any]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading file {file_path}: {str(e)}")
        return None

def create_sharegpt_entry(content: str, extracted_text: str, category: str, document_type: str) -> Dict[str, Any]:
    user_content = build_user_prompt_for_task_type(content, category, "annotation", document_type)
    system_prompt = get_system_prompt_for_task_type(document_type, "annotation")
    
    return {
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user", 
                "content": user_content
            },
            {
                "role": "assistant",
                "content": extracted_text
            }
        ]
    }

def should_include_entry(extracted_text: str, min_words: int = 5) -> bool:
    """
    Check if an entry should be included based on content quality.
    
    Args:
        extracted_text: The extracted text to check
        min_words: Minimum number of words required
        
    Returns:
        True if entry should be included, False otherwise
    """
    # Skip if empty or too short
    if not extracted_text or not extracted_text.strip():
        return False
    
    # Count words
    word_count = len(extracted_text.split())
    if word_count < min_words:
        return False
    
    return True

def process_document_file(file_path: Path, document_type: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Process a single document file and create ShareGPT entries organized by category.
    
    Args:
        file_path: Path to the document JSON file
        document_type: Type of document (subpoena, counterclaim, etc.)
        
    Returns:
        Dictionary with category names as keys and lists of ShareGPT entries as values
    """
    data = load_document_data(file_path)
    if not data:
        return {}
    
    content = data.get('content', '')
    if not content or not content.strip():
        logger.warning(f"No content found in {file_path}")
        return {}
    
    category_entries = {}
    
    # Categories to process (excluding content which is the full text)
    categories = ['isTemei', 'isProba', 'isSelected', 'isCerere', 'isReclamant', 'isParat']
    
    for category in categories:
        extracted_text = data.get(category, '')
        
        if should_include_entry(extracted_text):
            try:
                entry = create_sharegpt_entry(content, extracted_text, category, document_type)
                if category not in category_entries:
                    category_entries[category] = []
                category_entries[category].append(entry)
                
            except Exception as e:
                logger.error(f"Error creating entry for {category} in {file_path}: {str(e)}")
    
    return category_entries

def find_document_files(documents_dir: Path) -> List[Path]:
    return list(documents_dir.glob('*.json'))

def main():
    parser = argparse.ArgumentParser(description='Convert documents dataset to ShareGPT format')
    parser.add_argument('--type', default='subpoena', 
                       help='Document type to process (default: subpoena). Determines the source directory.')
    args = parser.parse_args()
    
    document_type = args.type
    # Map document types to directory names
    dir_mapping = {
        'subpoena': 'subpoenas',
        'counterclaim': 'counterclaims'
    }
    
    documents_dir = Path(dir_mapping.get(document_type, f"{document_type}s"))
    output_dir = Path('.')
    
    logger.info("Starting ShareGPT dataset creation...")
    logger.info(f"Document type: {document_type}")
    logger.info(f"Documents directory: {documents_dir}")
    logger.info(f"Output directory: {output_dir}")
    
    # Find all document files
    document_files = find_document_files(documents_dir)
    
    if not document_files:
        logger.error(f"No {document_type} files found in {documents_dir}!")
        return
    
    logger.info(f"Found {len(document_files)} {document_type} files")
    
    # Initialize entries dictionary for each category
    categories = ['isTemei', 'isProba', 'isSelected', 'isCerere', 'isReclamant', 'isParat']
    category_entries = {category: [] for category in categories}
    
    processed_count = 0
    error_count = 0
    
    # Process each file
    for file_path in document_files:
        try:
            entries_by_category = process_document_file(file_path, document_type)
            
            # Add entries to their respective category lists
            for category, entries in entries_by_category.items():
                category_entries[category].extend(entries)
            
            processed_count += 1
            
            if processed_count % 100 == 0:
                total_entries = sum(len(entries) for entries in category_entries.values())
                logger.info(f"Processed {processed_count} files, generated {total_entries} entries so far...")
                
        except Exception as e:
            logger.error(f"Error processing {file_path}: {str(e)}")
            error_count += 1
    
    # Save separate ShareGPT datasets for each category
    total_entries = 0
    saved_files = []
    
    for category in categories:
        entries = category_entries[category]
        if entries:
            output_file = output_dir / f"{document_type}s_sharegpt_{category}.json"
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(entries, f, indent=2, ensure_ascii=False)
                
                total_entries += len(entries)
                saved_files.append((category, len(entries), output_file))
                logger.info(f"Saved {len(entries)} entries for {category} to {output_file}")
                
            except Exception as e:
                logger.error(f"Error saving {category} dataset: {str(e)}")
    
    logger.info("="*50)
    logger.info("ShareGPT dataset creation completed!")
    logger.info(f"Total files processed: {processed_count}")
    logger.info(f"Errors encountered: {error_count}")
    logger.info(f"Total ShareGPT entries created: {total_entries}")
    logger.info(f"Files saved: {len(saved_files)}")
    
    logger.info("\nCategory breakdown:")
    for category, count, file_path in saved_files:
        logger.info(f"  {category}: {count} entries -> {file_path}")
    
    if not saved_files:
        logger.warning("No entries generated for any category!")

if __name__ == "__main__":
    main()
