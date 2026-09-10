# 0.000099% of laion-5b

A teaching tool exploring the sources behind [LAION-5B](https://laion.ai/blog/laion-5b/), built for SUPSI's [Data Driven Design](https://maind.supsi.ch/master-interaction-design/) course.

- **`notebook/`** — `run_pipeline.py` downloads a sample and computes a CLIP/UMAP layout.
- **`app/`** — Svelte gallery that reads and displays it.

## Run

```bash
cd notebook && python run_pipeline.py   # builds app/public/data/
cd ../app && npm install && npm run dev
```
