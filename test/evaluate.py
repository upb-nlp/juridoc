#!/usr/bin/env python3
import json
import os
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import numpy as np


@dataclass
class EvaluationResult:
    """Complete evaluation results for all entity types."""
    entity_metrics: Dict[str, Dict[str, float]]
    overall_accuracy: float
    total_documents: int
    successful_predictions: int
    failed_predictions: int
    evaluation_time: float
    detailed_results: List[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "total_documents": self.total_documents,
            "successful_predictions": self.successful_predictions,
            "failed_predictions": self.failed_predictions,
            "overall_accuracy": self.overall_accuracy,
            "evaluation_time": self.evaluation_time,
            "entity_metrics": self.entity_metrics
        }
        if self.detailed_results is not None:
            result["detailed_results"] = self.detailed_results
        return result


class DocumentEvaluator:
    # Entity types to evaluate
    #ENTITY_TYPES = ['isTemei', 'isCerere', 'isProba', 'isSelected', 'isReclamant', 'isParat'] 
    ENTITY_TYPES = ['isSelected'] 
    
    def __init__(self, server_url: str, document_type: str = 'subpoena', timeout: int = 300, max_workers: int = 3):
        self.server_url = server_url
        self.document_type = document_type
        self.timeout = timeout
        self.max_workers = max_workers
    
    def load_validation_data(self, validation_dir: str) -> List[Dict[str, Any]]:
        validation_path = Path(validation_dir)
        if not validation_path.exists():
            raise FileNotFoundError(f"Validation directory not found: {validation_dir}")
        
        validation_data = []
        json_files = list(validation_path.glob("*.json"))
        
        print(f"Found {len(json_files)} validation files")
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    data['filename'] = json_file.name
                    validation_data.append(data)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"Error loading {json_file}: {e}")
                continue
                
        return validation_data
    
    def prepare_document_for_processing(self, validation_doc: Dict[str, Any], extraction_types: List[str] = None) -> Dict[str, Any]:
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
        
        document_type_mapping = {
            'subpoena': 'Cerere de chemare în judecată',
            'counterclaim': 'Întâmpinare'
        }
        document['document_type'] = document_type_mapping.get(self.document_type, 'Cerere de chemare în judecată')
        
        if extraction_types:
            document['extraction_type'] = extraction_types
        
        return document
    
    def process_document_with_server(self, document: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            response = requests.post(
                f"{self.server_url}/annotate-document",
                json=document,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                print(f"Error submitting document: {response.status_code}")
                return None
            
            task_response = response.json()
            task_id = task_response['task_id']
            
            max_polls = 60  # 5 minutes with 5-second intervals
            poll_interval = 5
            
            for _ in range(max_polls):
                status_response = requests.get(
                    f"{self.server_url}/task-status/{task_id}",
                    timeout=120
                )
                
                if status_response.status_code != 200:
                    print(f"Error checking task status: {status_response.status_code}")
                    return None
                
                status_data = status_response.json()
                status = status_data['status']
                
                if status == 'completed':
                    break
                elif status == 'failed':
                    print(f"Task failed: {task_id}")
                    return None
                
                time.sleep(poll_interval)
            else:
                print(f"Task timed out: {task_id}")
                return None
            
            result_response = requests.get(
                f"{self.server_url}/annotated-document/{task_id}",
                timeout=120
            )
            
            if result_response.status_code != 200:
                print(f"Error retrieving annotated document: {result_response.status_code}")
                return None
            
            result = result_response.json()
            return result.get('document')
            
        except Exception as e:
            print(f"Error processing document: {e}")
            return None
    
    def extract_word_annotations(self, document: Dict[str, Any]) -> Dict[str, List[bool]]:
        word_annotations = {entity_type: [] for entity_type in self.ENTITY_TYPES}
        
        if not document or 'pages' not in document:
            return word_annotations
        
        for page in document['pages']:
            for paragraph in page.get('paragraphs', []):
                for word in paragraph.get('words', []):
                    word_text = word.get('text', '').strip()
                    if not word_text:
                        continue
                    
                    for entity_type in self.ENTITY_TYPES:
                        is_annotated = word.get(entity_type, False)
                        word_annotations[entity_type].append(is_annotated)
        
        return word_annotations
    
    def extract_annotated_words(self, document: Dict[str, Any]) -> Dict[str, List[str]]:
        """Extract the actual words that are annotated for each entity type."""
        annotated_words = {entity_type: [] for entity_type in self.ENTITY_TYPES}
        
        if not document or 'pages' not in document:
            return annotated_words
        
        for page in document['pages']:
            for paragraph in page.get('paragraphs', []):
                for word in paragraph.get('words', []):
                    word_text = word.get('text', '').strip()
                    if not word_text:
                        continue
                    
                    for entity_type in self.ENTITY_TYPES:
                        is_annotated = word.get(entity_type, False)
                        if is_annotated:
                            annotated_words[entity_type].append(word_text)
        
        return annotated_words
    
    def document_has_entity_annotations(self, document: Dict[str, Any], entity_types: List[str]) -> bool:
        """Check if document has any annotations for the specified entity types."""
        if not document or 'pages' not in document:
            return False
        
        for page in document['pages']:
            for paragraph in page.get('paragraphs', []):
                for word in paragraph.get('words', []):
                    word_text = word.get('text', '').strip()
                    if not word_text:
                        continue
                    
                    for entity_type in entity_types:
                        if word.get(entity_type, False):
                            return True
        
        return False
    
    def _extract_document_text(self, document: Dict[str, Any]) -> str:
        """Extract the full text content from a document for display purposes."""
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
    
    def process_single_document(self, validation_doc: Dict[str, Any], doc_index: int, total_docs: int, extraction_types: List[str] = None) -> Tuple[int, Optional[Dict[str, Dict[str, Any]]], str, Optional[Dict[str, Any]]]:
        """Process a single document and return its evaluation results."""
        filename = validation_doc.get('filename', 'unknown')
        
        try:
            if extraction_types is None:
                extraction_types = self.ENTITY_TYPES
            
            print(f"Processing document {doc_index + 1}/{total_docs}: {filename}")
            
            document = self.prepare_document_for_processing(validation_doc, extraction_types)
            
            processed_doc = self.process_document_with_server(document)
            
            if processed_doc is None:
                print(f"Failed to process document: {filename}")
                return doc_index, None, filename, None
            
            doc_results = self.evaluate_document_pair(validation_doc, processed_doc)
            
            detailed_result = {
                "filename": filename,
                "request_text": self._extract_document_text(validation_doc),
                "extraction_types": extraction_types,
                "metrics": doc_results
            }
            
            print(f"Document {filename} results:")
            for entity_type in extraction_types:
                if entity_type in doc_results:
                    metrics = doc_results[entity_type]
                    print(f"  {entity_type}: Recall={metrics['recall_percentage']:.1f}%, Extra={metrics['extra_annotations_count']} ({metrics['extra_annotations_percentage']:.1f}%), F1={metrics['f1_score']:.3f}")
            
            print(f"Successfully processed document {doc_index + 1}/{total_docs}: {filename}")
            return doc_index, doc_results, filename, detailed_result
            
        except Exception as e:
            print(f"Error processing document {filename}: {e}")
            return doc_index, None, filename, None
    
    def calculate_word_level_metrics(self, ground_truth_annotations: List[bool], predicted_annotations: List[bool]) -> Dict[str, float]:
        """
        Calculate word-level precision, recall, and F1 score.
        
        Args:
            ground_truth_annotations: List of boolean values for ground truth
            predicted_annotations: List of boolean values for predictions
        """
        if len(ground_truth_annotations) != len(predicted_annotations):
            print(f"Warning: Mismatched annotation lengths: {len(ground_truth_annotations)} vs {len(predicted_annotations)}")
            min_len = min(len(ground_truth_annotations), len(predicted_annotations))
            ground_truth_annotations = ground_truth_annotations[:min_len]
            predicted_annotations = predicted_annotations[:min_len]
        
        if not ground_truth_annotations:
            return {
                'precision': 0.0, 'recall': 0.0, 'f1_score': 0.0,
                'total_words': 0, 'gt_positive_words': 0, 'pred_positive_words': 0,
                'recall_percentage': 0.0, 'extra_annotations_count': 0, 'extra_annotations_percentage': 0.0
            }
        
        tp = fp = fn = 0
        
        for gt, pred in zip(ground_truth_annotations, predicted_annotations):
            if gt and pred:
                tp += 1
            elif not gt and pred:
                fp += 1
            elif gt and not pred:
                fn += 1
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        
        total_words = len(ground_truth_annotations)
        gt_positive_words = sum(ground_truth_annotations)
        pred_positive_words = sum(predicted_annotations)
        
        recall_percentage = (tp / gt_positive_words * 100) if gt_positive_words > 0 else 0.0
        
        extra_annotations_count = fp
        extra_annotations_percentage = (fp / total_words * 100) if total_words > 0 else 0.0
        
        return {
            'precision': precision,
            'recall': recall,
            'f1_score': f1_score,
            'total_words': total_words,
            'gt_positive_words': gt_positive_words,
            'pred_positive_words': pred_positive_words,
            'recall_percentage': recall_percentage,
            'extra_annotations_count': extra_annotations_count,
            'extra_annotations_percentage': extra_annotations_percentage
        }
    
    def evaluate_document_pair(self, ground_truth_doc: Dict[str, Any], predicted_doc: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        results = {}
        
        gt_annotations = self.extract_word_annotations(ground_truth_doc)
        pred_annotations = self.extract_word_annotations(predicted_doc)
        
        gt_annotated_words = self.extract_annotated_words(ground_truth_doc)
        pred_annotated_words = self.extract_annotated_words(predicted_doc)

        for entity_type in self.ENTITY_TYPES:
            gt_words = gt_annotations.get(entity_type, [])
            pred_words = pred_annotations.get(entity_type, [])
            
            metrics = self.calculate_word_level_metrics(gt_words, pred_words)
            
            metrics['ground_truth_words'] = ' '.join(gt_annotated_words.get(entity_type, []))
            metrics['predicted_words'] = ' '.join(pred_annotated_words.get(entity_type, []))
            
            results[entity_type] = metrics
        
        return results
    
    def aggregate_metrics(self, all_document_results: List[Dict[str, Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
        """Aggregate metrics across all documents."""
        aggregated = {}
        
        for entity_type in self.ENTITY_TYPES:
            all_metrics = {
                'precision': [], 'recall': [], 'f1_score': [],
                'total_words': [], 'gt_positive_words': [], 'pred_positive_words': [],
                'recall_percentage': [], 'extra_annotations_count': [], 'extra_annotations_percentage': []
            }
            
            for doc_result in all_document_results:
                if entity_type in doc_result:
                    metrics = doc_result[entity_type]
                    for key in all_metrics:
                        if key in metrics and isinstance(metrics[key], (int, float)):
                            all_metrics[key].append(metrics[key])
            
            entity_aggregated = {}
            
            if all_metrics['precision']:
                entity_aggregated = {
                    'avg_precision': np.mean(all_metrics['precision']),
                    'avg_recall': np.mean(all_metrics['recall']),
                    'avg_f1_score': np.mean(all_metrics['f1_score']),
                    'total_words': np.sum(all_metrics['total_words']),
                    'total_gt_positive': np.sum(all_metrics['gt_positive_words']),
                    'total_pred_positive': np.sum(all_metrics['pred_positive_words']),
                    'avg_recall_percentage': np.mean(all_metrics['recall_percentage']),
                    'total_extra_annotations': np.sum(all_metrics['extra_annotations_count']),
                    'avg_extra_percentage': np.mean(all_metrics['extra_annotations_percentage']),
                    'num_documents': len(all_metrics['precision'])
                }
                
            aggregated[entity_type] = entity_aggregated
        
        return aggregated
    
    def evaluate_all_documents(self, validation_dir: str, extraction_types: List[str] = None) -> EvaluationResult:
        start_time = time.time()
        
        validation_data = self.load_validation_data(validation_dir)
        
        if extraction_types is None:
            extraction_types = self.ENTITY_TYPES
        
        original_count = len(validation_data)
        validation_data = [doc for doc in validation_data if self.document_has_entity_annotations(doc, extraction_types)]
        total_documents = len(validation_data)
        
        if total_documents == 0:
            raise ValueError(f"No validation documents found with annotations for entity types: {extraction_types}")
        
        skipped_count = original_count - total_documents
        if skipped_count > 0:
            print(f"Filtered {original_count} -> {total_documents} documents (skipped {skipped_count} without {extraction_types} annotations)")
        else:
            print(f"Processing {total_documents} documents")
        
        all_document_results = []
        detailed_results = []
        successful_predictions = 0
        failed_predictions = 0
        
        print(f"Processing {total_documents} documents with {self.max_workers} parallel workers...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_doc = {
                executor.submit(self.process_single_document, validation_doc, i, total_documents, extraction_types): i 
                for i, validation_doc in enumerate(validation_data)
            }
            
            for future in as_completed(future_to_doc):
                doc_index, doc_results, filename, detailed_result = future.result()
                
                if doc_results is not None:
                    all_document_results.append(doc_results)
                    if detailed_result is not None:
                        detailed_results.append(detailed_result)
                    successful_predictions += 1
                else:
                    if detailed_result is None:
                        detailed_result = {
                            "filename": filename,
                            "request_text": "",
                            "reference_entities": {},
                            "predicted_entities": {},
                            "metrics": {},
                            "error": "Failed to process document"
                        }
                    detailed_results.append(detailed_result)
                    failed_predictions += 1
        
        print("Aggregating results...")
        entity_metrics = self.aggregate_metrics(all_document_results)
        
        all_f1_scores = []
        for doc_result in all_document_results:
            for entity_type, metrics in doc_result.items():
                all_f1_scores.append(metrics['f1_score'])
        
        overall_accuracy = np.mean(all_f1_scores) if all_f1_scores else 0.0
        
        evaluation_time = time.time() - start_time
        
        return EvaluationResult(
            entity_metrics=entity_metrics,
            overall_accuracy=overall_accuracy,
            total_documents=total_documents,
            successful_predictions=successful_predictions,
            failed_predictions=failed_predictions,
            evaluation_time=evaluation_time,
            detailed_results=detailed_results
        )
    
    def print_evaluation_report(self, results: EvaluationResult):
        """Print a detailed evaluation report."""
        print("\n" + "="*100)
        print("EVALUATION REPORT")
        print("="*100)
        
        print(f"Document Type: {self.document_type.upper()}")
        print(f"Total Documents: {results.total_documents}")
        print(f"Successful Predictions: {results.successful_predictions}")
        print(f"Failed Predictions: {results.failed_predictions}")
        print(f"Success Rate: {results.successful_predictions/results.total_documents*100:.2f}%")
        print(f"Overall Accuracy (Avg F1): {results.overall_accuracy:.4f}")
        print(f"Evaluation Time: {results.evaluation_time:.2f} seconds")
        
        print("\nPER-ENTITY DETAILED METRICS:")
        print("-" * 100)
        
        for entity_type, metrics in results.entity_metrics.items():
            if not metrics:
                continue
                
            print(f"\n{entity_type.upper()}:")
            print(f"  Documents processed: {metrics.get('num_documents', 0)}")
            print(f"  Total words: {metrics.get('total_words', 0)}")
            print(f"  Ground truth positive words: {metrics.get('total_gt_positive', 0)}")
            print(f"  Predicted positive words: {metrics.get('total_pred_positive', 0)}")
            print(f"  ")
            print(f"  ACCURACY METRICS:")
            print(f"    Average Precision: {metrics.get('avg_precision', 0):.4f}")
            print(f"    Average Recall: {metrics.get('avg_recall', 0):.4f}")
            print(f"    Average F1-Score: {metrics.get('avg_f1_score', 0):.4f}")
            print(f"  ")
            print(f"  ANNOTATION PERFORMANCE:")
            print(f"    Recall Percentage: {metrics.get('avg_recall_percentage', 0):.1f}%")
            print(f"      (% of originally annotated words correctly identified)")
            print(f"    Extra Annotations: {metrics.get('total_extra_annotations', 0)} words")
            print(f"    Extra Annotations Rate: {metrics.get('avg_extra_percentage', 0):.2f}%")
            print(f"      (% of total words incorrectly annotated)")

        
    def save_results_to_file(self, results: EvaluationResult, output_file: str):
        """Save evaluation results to JSON file."""
        results_dict = results.to_dict()
        results_dict['timestamp'] = datetime.now().isoformat()
        results_dict['document_type'] = self.document_type
        
        def convert_numpy_types(obj):
            """Recursively convert NumPy types to Python native types."""
            if isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            
            if isinstance(obj, dict):
                return {key: convert_numpy_types(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [convert_numpy_types(item) for item in obj]
            else:
                return obj
        
        results_dict = convert_numpy_types(results_dict)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results_dict, f, indent=2, ensure_ascii=False)
        
        print(f"Results saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate legal document entity extraction accuracy")
    parser.add_argument("--type", "-dt",
                       choices=["subpoena", "counterclaim"],
                       default="subpoena",
                       help="Document type to evaluate (subpoena or counterclaim)")
    parser.add_argument("--validation-dir", "-v", 
                       default=None,
                       help="Path to validation directory containing JSON files (auto-detected based on document type if not provided)")
    parser.add_argument("--server-url", "-s", 
                       default="http://localhost:8060",
                       help="URL of the document processing server")
    parser.add_argument("--output", "-o", 
                       default="results.json",
                       help="Output file for evaluation results")
    parser.add_argument("--timeout", "-t", 
                       type=int, default=300,
                       help="Timeout in seconds for API calls")
    parser.add_argument("--limit", "-l", 
                       type=int, default=10,
                       help="Limit number of documents to evaluate (for testing)")
    parser.add_argument("--max-workers", "-w", 
                       type=int, default=1,
                       help="Maximum number of parallel workers for document processing")
    parser.add_argument("--extraction-types", "-e", 
                       nargs='*', default=None,
                       help="Specific entity types to extract and evaluate (default: all)")
    
    args = parser.parse_args()
    
    if args.validation_dir is None:
        if args.type == "subpoena":
            args.validation_dir = "../train/subpoena_validation"
        elif args.type == "counterclaim":
            args.validation_dir = "../train/counterclaim_validation"
    
    try:
        response = requests.get(f"{args.server_url}/health", timeout=30)
        if response.status_code != 200:
            print(f"Warning: Server health check failed with status {response.status_code}")
        else:
            health_data = response.json()
            print(f"Server is healthy: {health_data}")
    except Exception as e:
        print(f"Warning: Could not connect to server: {e}")
        print("Make sure the server is running before proceeding.")
        return
    
    print(f"Evaluating document type: {args.type}")
    print(f"Using validation directory: {args.validation_dir}")
    
    evaluator = DocumentEvaluator(
        server_url=args.server_url, 
        document_type=args.type,
        timeout=args.timeout, 
        max_workers=args.max_workers
    )
    
    try:
        if args.limit:
            validation_data = evaluator.load_validation_data(args.validation_dir)
            
            extraction_types_for_filtering = args.extraction_types if args.extraction_types else evaluator.ENTITY_TYPES
            
            valid_docs = [doc for doc in validation_data if evaluator.document_has_entity_annotations(doc, extraction_types_for_filtering)]
            
            if len(valid_docs) < args.limit:
                print(f"Warning: Only {len(valid_docs)} documents have annotations for {extraction_types_for_filtering}, but {args.limit} requested.")
                print(f"Will process all {len(valid_docs)} available documents.")
                limited_data = valid_docs
            else:
                limited_data = valid_docs[:args.limit]
                print(f"Selected {len(limited_data)} documents with relevant annotations from {len(validation_data)} total documents.")
            
            import tempfile
            
            with tempfile.TemporaryDirectory() as temp_dir:
                for doc in limited_data:
                    filename = doc.get('filename', 'unknown.json')
                    temp_file = os.path.join(temp_dir, filename)
                    with open(temp_file, 'w', encoding='utf-8') as f:
                        json.dump(doc, f, ensure_ascii=False, indent=2)
                
                results = evaluator.evaluate_all_documents(temp_dir, args.extraction_types)
        else:
            results = evaluator.evaluate_all_documents(args.validation_dir, args.extraction_types)
        
        evaluator.print_evaluation_report(results)
        
        output_file = args.output
        if args.output == "results.json":
            output_file = f"results_{args.type}.json"
        
        evaluator.save_results_to_file(results, output_file)
        
    except Exception as e:
        print(f"Error during evaluation: {e}")
        raise


if __name__ == "__main__":
    main()
