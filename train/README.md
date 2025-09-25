# Model Training

## Overivew

There are several document types that make up a court case:

* Cerere de chemare in judecata
* Intemeiere
TODO

1. For each document type, we extract the relevant entities. To achieve this,
we train a separate LoRA Adaptor for each entity type.

Entity Types:
* Parat
* Reclamant
* Temei
* Cerere
* Proba
* Descriere In Fapt

## Prerequisites

For fine-tunning the base mode we use `LLaMA-Factory`.

## Document Annotation SFT

### Instruct Dataset

1. Put in `base_ds` the court case courpus. This is a directory with
subdirectories for court cases and inside each court case, all the files, in
OCRized json format 

```
train$ ls base_ds/data-skip_0-batch_10000/1642_231_2031/
case.json  Cerere_de_chemare_în_judecată.json  Răspuns_la_întâmpinare.json
```

2. Run `python3 extract_dataset --type subpoena`.

> There are multiple types available: subpoena, counterclaim.

This will create two directories, `subpoenas` and `subpoena_validation`. The
validation dataset is used to evaluate the accuracy, via the `evaluation.py`
script.

3. Run `python3 create_sharegpt.py --type subpoena`. This will create the LLM
fine-tunning instruct dataset in the conversational dataset format.

This will create files for all the relevant entities (e.g. Parat, Temei etc.).

```
subpoenas_sharegpt_isCerere.json
subpoenas_sharegpt_isProba.json
....
```

These datasets are used to train the LoRA adaptors.

### Training

1. Move the instruct dataset to the `data` directory in LLamaFactory.
2. Register the dataset in `data/dataset_info.json`
3. Update `configs/llama3_lora_sft.yaml` from this project to use this dataset
4. Run the trainning with `llamafactory-cli train llama3_lora_sft.yaml`