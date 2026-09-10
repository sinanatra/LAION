# LAION dataset prep script

`run_pipeline.py` builds the sample for the [gallery app](../app): streams `laion/relaion2B-en-research-safe`, downloads a systematic 1-in-N sample, then computes CLIP + UMAP so similar images sit near each other.

## Setup

1. Create a Hugging Face account, accept the dataset's terms on [its page](https://huggingface.co/datasets/laion/relaion2B-en-research-safe), and get a token from [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).
2. `pip install -r requirements.txt -r requirements-embeddings.txt`
3. `cp .env.example .env` and set `HF_TOKEN=hf_...`
4. `python run_pipeline.py`

## Parameters

Near the top of `run_pipeline.py`: `SAMPLE_EVERY_N` (stride), `MAX_TOTAL_IMAGES` (target), `MAX_IMAGE_DIMENSION`, `MAX_ROWS_TO_SCAN` (safety cap). `--skip-embeddings` downloads only.

Safe to stop and re-run anytime, it resumes from `progress.json` without re-downloading or duplicating.
