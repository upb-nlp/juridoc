# Overview

This project is an implementation of a juridical document processor using LLMs.
It provides entity ectraction and annotation functionality alongisde domain
specific document summarization. This implementation specifically targets the
legal document from romanian courts.

This repo provides all the scripts, code and documentation used to train the
models and run the project. No training data is available in this repo.

## Running

Make sure you have installed CUDA on the node, and `nvidia-smi` shows the
availables accelerators. 

> On the GPU node, copy the relevant LoRA adaptors into the directory `lora` in the root of this proeject. We use the LoRA adaptors to improve the base model performance for domain specific tasks.

Running this on a GPU node, with no separation between the fastapi server and
vLLM server:

```bash
docker compose up juridoc
```

## FastAPI Server

The server exposes several endpoints for: Entity Extraction and Summarization.
The summarization is done on documents that have been processed through the
entity extraction endpoint.

### Document Annotation Endpoints

**POST `/annotate-document`**
**Description**: Submit a legal document for LLM-based annotation and entity extraction. Returns `task_id` for tracking progress. The system will analyze the document and annotate words with various legal entity types (isTemei, isProba, isSelected, isCerere, isReclamant, isParat).

**Optional Parameters**:
- `extraction_type`: Array of annotation types to extract. If not provided, all types will be processed. Valid values: `["isTemei", "isProba", "isSelected", "isCerere", "isReclamant", "isParat"]`. This is optional after `lastSaved` key.

The input document should be in the JSON format below:
```
{
    "id": "",
    "userId": "",
    "email": "",
    "caseNumber": "",
    "entityId": 0,
    "documentTypeId": 1,
    "documentTypeName": "",
    "attachmentId": 0,
    "extractedPages": [
        6,
        7
    ],
    "extractedContent": "content of the document",
    "content": "content of the document",
    "pages": [
        {
            "width": 2483,
            "height": 2483,
            "pageNumber": 1,
            "paragraphs": [
                {
                    "id": "par_1_1",
                    "words": [
                        {
                            "id": "word_1_1",
                            "text": "",
                            "left": 887,
                            "top": 397,
                            "width": 196,
                            "height": 34,
                            "isSelected": false,
                            "isProba": false,
                            "isExceptie": false,
                            "isTemei": false,
                            "isCerere": false,
                            "isReclamant": false,
                            "isParat": false
                        },
                        ...
                    ]
                }
            ]
        }
    ],
    "isGold": false,
    "isManuallyAdnotated": false,
    "lastSaved": "",
}
```

**GET `/task-status/{task_id}`**
**Description**: Check the current status of a document processing task. Returns current status and progress information.

**Possible statuses**: `pending`, `processing`, `extracting_content`, `annotating`, `completed`, `failed`

**GET `/annotated-document/{task_id}`**
**Description**: Retrieve the annotated document with LLM annotations when processing is complete. 

**Response**: Returns the same document structure as input, but with word-level annotations applied. We use the following fields:
- `isTemei`
- `isProba`
- `isSelected`
- `isCerere`
- `isReclamant`
- `isParat`

Returned object:
```
{
    "task_id": "task_id_str"
    "status": "completed"
    "document": {annotated document format from above}
}
```

**Status Codes**:
- `200`: Document ready, returns annotated document
- `202`: Task still processing, check status later
- `404`: Task not found
- `400`: Task failed, check error message, inside the `error` field

### Document Summarization Endpoints

**POST `/summarize-document`**
**Description**: Submit a legal document for LLM-based summarization. Returns `task_id`. 
The input document format is the same as for the annotation endpoint above.

**GET `/task-status/{task_id}`**
**Description**: Check the current status of a document processing task (works for both annotation and summarization tasks)

**GET `/summarized-document/{task_id}`**
**Description**: Retrieve the document summary when processing is complete. Returns a JSON object with document metadata and summary fields:

```json
{
    "task_id": "string",
    "status": "completed",
    "summary": {
        "all the entries from the document format"
        "Temei": "",
        "Proba": "",
        "Selected": "",
        "Cerere": "",
        "Reclamant": "",
        "Parat": ""
    },
    "error": null
}
```

## Model Training

In the `train` directory are the scripts and the relevant evaluation for
training the LoRA adaptors.

## Extending

Each type of document requires specific prompts, training and handling. In `doc_types`,
we have the specific implementations. Document types:

- Subpoena (Cerere de chemare in judecata) - `subpoena.py`.
- Statement of Defence (Intampinare)

## Accuracy

We evaluated this implementation using the script ```test/evaluate.py```.

### Subpoema

#### Entity Recognitions

##### Base Model Performance

For the base model `meta-llama/Llama-3.1-8B-Instruct`:

| Entity Type | Recall (%) | Extra Annotations (%) | Precision | Recall | F1-Score |
|-------------|------------|----------------------|-----------|--------|----------|
| Temei       | 55.7       | 3.83                 | 0.6152    | 0.5585 | 0.5531   |
| Cerere      | 55.8       | 4.59                 | 0.6152    | 0.5585 | 0.5531   |
| Probe       | 25.1       | 3.22                 | 0.1792    | 0.2512 | 0.1269   |
| Fapt        | 34.7       | 1.71                 | 0.8790    | 0.3473 | 0.4526   |
| Reclamant   | 45.1       | 0.49                 | 0.4179    | 0.4514 | 0.3408   |
| Parat       | 26.7       | 1.01                 | 0.1230    | 0.2667 | 0.1404   |

###### Model Performance with LoRA Adaptors

Model with LoRA adaptors trained on relevant examples.

| Entity Type | Recall (%) | Extra Annotations (%) | Precision | Recall | F1-Score |
|-------------|------------|----------------------|-----------|--------|----------|
| Fapt        | 84.6       | 7.60                 | 0.8301    | 0.8463 | 0.8296   |
| Cerere      | 93.2       | 1.75                 | 0.8758    | 0.9322 | 0.8792   |
| Proba       | 84.4       | 0.61                 | 0.8053    | 0.8444 | 0.7189   |
| Temei       | 78.3       | 0.02                 | 0.8870    | 0.7833 | 0.8271   |
| Parat       | 88.9       | 0.75                 | 0.5193    | 0.8889 | 0.5898   |
| Reclamant   | 82.3       | 2.24                 | 0.5766    | 0.8227 | 0.4617   |

**Note**: 
- Recall Percentage = % of originally annotated words correctly identified
- Extra Annotations Rate = % of total words incorrectly annotated


### Counterclaim

#### Entity Recognitions

##### Base Model Performance

For the base model `meta-llama/Llama-3.1-8B-Instruct`:

| Entity Type | Recall (%) | Extra Annotations (%) | Precision | Recall | F1-Score |
|-------------|------------|----------------------|-----------|--------|----------|
| Reclamant   | 40.0       | 1.72                 | 0.2133    | 0.4000 | 0.2679   |
| Fapt        | 27.9       | 0.79                 | 0.8043    | 0.2794 | 0.3690   |
| Temei       | 68.7       | 3.63                 | 0.3148    | 0.6868 | 0.3587   |
| Proba       | 47.4       | 2.46                 | 0.2911    | 0.4740 | 0.3081   |
| Cerere      | 57.7       | 4.38                 | 0.3327    | 0.5772 | 0.3688   |
| Parat       | 20.0       | 0.51                 | 0.0792    | 0.2000 | 0.1022   |

* for parat, it seems like most of the dataset is badly annotated

###### Model Performance with LoRA Adaptors

Model with LoRA adaptors trained on relevant examples.

| Entity Type | Recall (%) | Extra Annotations (%) | Precision | Recall | F1-Score |
|-------------|------------|----------------------|-----------|--------|----------|