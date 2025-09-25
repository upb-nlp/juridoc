#!/usr/bin/env python3
"""
Script to process legal document JSON files and create a new dataset
with structured content based on word annotations.

Supported document types:
- subpoena: Processes Cerere_de_chemare_în_judecată.json files
- counterclaim: Processes Întâmpinare.json files

The script extracts:
- Full conte    document_files = find_document_files(base_dir, filename)
    
    if not document_files:
        logger.error(f"No {filename} files found!")
        return
    
    random.seed(42)
    random.shuffle(document_files)
    
    total_files = len(document_files)
    validation_size = int(total_files * 0.05)
    
    validation_files = document_files[:validation_size]
    train_files = document_files[validation_size:]as text)
- Words marked as isProba
- Words marked as isTemei 
- Words marked as isCerere
- Words marked as isReclamant
- Words marked as isParat
- Words marked as isSelected
"""

import json
import os
import argparse
from pathlib import Path
from typing import Dict, List, Any
import logging
import re
import random

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def has_romanian_diacritics(text: str) -> bool:
    romanian_diacritics = r'[ăâîșțĂÂÎȘȚşţŞŢ]'
    return bool(re.search(romanian_diacritics, text))

def is_valid_content(content: str, word_count: int) -> bool:
    # Documents with less than 100 words are likely incomplete or invalid
    if word_count < 100:
        return False
    
    # We skip badly OCRed documents, which usually have no diacritics
    if not has_romanian_diacritics(content):
        return False
    
    return True

def extract_words_by_category(pages: List[Dict]) -> Dict[str, List[str]]:
    """Extract words from pages categorized by their annotation flags, preserving paragraph structure."""
    categories = {
        'content': [],
        'isProba': [],
        'isTemei': [],
        'isCerere': [],
        'isReclamant': [],
        'isParat': [],
        'isSelected': []
    }
    
    for page in pages:
        for paragraph in page.get('paragraphs', []):
            paragraph_content = []
            paragraph_proba = []
            paragraph_temei = []
            paragraph_cerere = []
            paragraph_reclamant = []
            paragraph_parat = []
            paragraph_selected = []
            
            for word in paragraph.get('words', []):
                word_text = word.get('text', '')
                if not word_text:
                    continue
                    
                paragraph_content.append(word_text)
                
                if word.get('isProba', False):
                    paragraph_proba.append(word_text)
                if word.get('isTemei', False):
                    paragraph_temei.append(word_text)
                if word.get('isCerere', False):
                    paragraph_cerere.append(word_text)
                if word.get('isReclamant', False):
                    paragraph_reclamant.append(word_text)
                if word.get('isParat', False):
                    paragraph_parat.append(word_text)
                if word.get('isSelected', False):
                    paragraph_selected.append(word_text)
            
            if paragraph_content:
                content_text = ' '.join(paragraph_content)
                categories['content'].append(f"<p> {content_text} </p>")
                
                if paragraph_proba:
                    proba_text = ' '.join(paragraph_proba)
                    categories['isProba'].append(f"<p> {proba_text} </p>")
                
                if paragraph_temei:
                    temei_text = ' '.join(paragraph_temei)
                    categories['isTemei'].append(f"<p> {temei_text} </p>")
                
                if paragraph_cerere:
                    cerere_text = ' '.join(paragraph_cerere)
                    categories['isCerere'].append(f"<p> {cerere_text} </p>")
                
                if paragraph_reclamant:
                    reclamant_text = ' '.join(paragraph_reclamant)
                    categories['isReclamant'].append(f"<p> {reclamant_text} </p>")
                
                if paragraph_parat:
                    parat_text = ' '.join(paragraph_parat)
                    categories['isParat'].append(f"<p> {parat_text} </p>")
                
                if paragraph_selected:
                    selected_text = ' '.join(paragraph_selected)
                    categories['isSelected'].append(f"<p> {selected_text} </p>")
                
    return categories

def process_document_file(file_path: Path) -> Dict[str, Any]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        case_number = data.get('caseNumber', '')
        document_type = data.get('documentTypeName', '')
        
        pages = data.get('pages', [])
        
        word_categories = extract_words_by_category(pages)
        
        full_content = ' '.join(word_categories['content'])
        total_word_count = sum(len(p.split()) - 2 for p in word_categories['content'])  # -2 to exclude <p> and </p> tags
        
        if not is_valid_content(full_content, total_word_count):
            logger.debug(f"Skipping file - validation failed: words={total_word_count}, has_diacritics={has_romanian_diacritics(full_content)}")
            return None
        
        result = {
            'case_number': case_number,
            'document_type': document_type,
            'content': full_content,
            'isProba': ' '.join(word_categories['isProba']),
            'isTemei': ' '.join(word_categories['isTemei']),
            'isCerere': ' '.join(word_categories['isCerere']),
            'isReclamant': ' '.join(word_categories['isReclamant']),
            'isParat': ' '.join(word_categories['isParat']),
            'isSelected': ' '.join(word_categories['isSelected']),
            'word_counts': {
                'total_words': total_word_count,
                'proba_paragraphs': len(word_categories['isProba']),
                'temei_paragraphs': len(word_categories['isTemei']),
                'cerere_paragraphs': len(word_categories['isCerere']),
                'reclamant_paragraphs': len(word_categories['isReclamant']),
                'parat_paragraphs': len(word_categories['isParat']),
                'selected_paragraphs': len(word_categories['isSelected'])
            }
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error processing file {file_path}: {str(e)}")
        return None

def find_document_files(base_dir: Path, filename: str) -> List[Path]:
    """Find all files with the specified filename in the dataset directories."""
    document_files = []
    
    # Look in all data directories
    for data_dir in base_dir.glob('data-*'):
        if data_dir.is_dir():
            logger.info(f"Scanning directory: {data_dir}")
            
            # Find all court case directories
            for case_dir in data_dir.iterdir():
                if case_dir.is_dir():
                    document_file = case_dir / filename
                    if document_file.exists():
                        document_files.append(document_file)
                        
    logger.info(f"Found {len(document_files)} {filename} files")
    return document_files

def extract_case_id_from_path(file_path: Path) -> str:
    """Extract case ID from the file path."""
    return file_path.parent.name

def main():
    parser = argparse.ArgumentParser(description='Process legal document JSON files and create datasets')
    parser.add_argument('--type', choices=['subpoena', 'counterclaim'], default='subpoena',
                       help='Document type to process (default: subpoena)')
    
    args = parser.parse_args()
    doc_type = args.type
    
    # Configure filenames and output directories based on document type
    if doc_type == 'subpoena':
        filename = 'Cerere_de_chemare_în_judecată.json'
        train_output_dir = Path('subpoenas')
        validation_output_dir = Path('subpoena_validation')
    elif doc_type == 'counterclaim':
        filename = 'Întâmpinare.json'
        train_output_dir = Path('counterclaims')
        validation_output_dir = Path('counterclaim_validation')
    
    base_dir = Path('base_ds')
    
    train_output_dir.mkdir(exist_ok=True)
    validation_output_dir.mkdir(exist_ok=True)
    
    logger.info(f"Starting {doc_type} dataset creation with validation split...")
    logger.info(f"Base directory: {base_dir}")
    logger.info(f"Training output directory: {train_output_dir}")
    logger.info(f"Validation output directory: {validation_output_dir}")
    logger.info(f"Looking for files: {filename}")
    
    document_files = find_document_files(base_dir, filename)
    
    if not document_files:
        logger.error(f"No {filename} files found!")
        return
    
    random.seed(42)
    random.shuffle(document_files)
    
    total_files = len(document_files)
    validation_size = int(total_files * 0.05)
    
    validation_files = document_files[:validation_size]
    train_files = document_files[validation_size:]
    
    logger.info(f"Total files found: {total_files}")
    logger.info(f"Validation files: {len(validation_files)} (5%)")
    logger.info(f"Training files: {len(train_files)} (95%)")
    
    processed_count = 0
    error_count = 0
    validation_processed = 0
    train_processed = 0
    
    logger.info("Copying original JSON files for validation dataset...")
    for file_path in validation_files:
        case_id = extract_case_id_from_path(file_path)
        output_file = validation_output_dir / f"{case_id}.json"
        
        if output_file.exists():
            logger.debug(f"Skipping validation {case_id} - already exists")
            continue
            
        try:
            with open(file_path, 'r', encoding='utf-8') as source:
                original_data = json.load(source)
            
            with open(output_file, 'w', encoding='utf-8') as target:
                json.dump(original_data, target, indent=2, ensure_ascii=False)
                
            validation_processed += 1
            processed_count += 1
                    
        except Exception as e:
            logger.error(f"Error copying validation file for {case_id}: {str(e)}")
            error_count += 1
    
    logger.info("Processing training files...")
    for file_path in train_files:
        case_id = extract_case_id_from_path(file_path)
        output_file = train_output_dir / f"{case_id}.json"
        
        if output_file.exists():
            logger.debug(f"Skipping training {case_id} - already exists")
            continue
            
        result = process_document_file(file_path)
        
        if result is not None:
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                train_processed += 1
                processed_count += 1
                
                if processed_count % 100 == 0:
                    logger.info(f"Processed {processed_count} files total ({train_processed} train, {validation_processed} validation)...")
                    
            except Exception as e:
                logger.error(f"Error saving training result for {case_id}: {str(e)}")
                error_count += 1
        else:
            error_count += 1
    
    logger.info("="*50)
    logger.info("Dataset creation completed!")
    logger.info(f"Total files processed: {processed_count}")
    logger.info(f"Training files processed: {train_processed}")
    logger.info(f"Validation files processed: {validation_processed}")
    logger.info(f"Errors encountered: {error_count}")
    logger.info(f"Training output directory: {train_output_dir}")
    logger.info(f"Validation output directory: {validation_output_dir}")
    
    if processed_count > 0:
        train_example = list(train_output_dir.glob('*.json'))[0] if list(train_output_dir.glob('*.json')) else 'None'
        validation_example = list(validation_output_dir.glob('*.json'))[0] if list(validation_output_dir.glob('*.json')) else 'None'
        logger.info(f"Example training file: {train_example}")
        logger.info(f"Example validation file: {validation_example}")

if __name__ == "__main__":
    main()
