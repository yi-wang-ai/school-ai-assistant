# Deployment notes

Local deployment of Dify v1.17.1 (Docker Compose, macOS, Docker Desktop with 8 GB RAM).

## Setup

- Dify cloned to `~/Code/dify` at tag `1.17.1` (kept outside this repo).
- `docker/.env` copied from `.env.example`; `SECRET_KEY` generated with `openssl rand -base64 42`.
- Models: DeepSeek (LLM, `DeepSeek V4.1 Flash`), SiliconFlow (`BAAI/bge-m3` embedding, `BAAI/bge-reranker-v2-m3` rerank).
- Knowledge base: parent-child chunking (parent = full document, child = one line, max 512 chars), high-quality index, hybrid search + rerank, Top K 3.
  - Reason for full-document parents: v1 and v2 share clause numbers; returning the whole document keeps the version header (effective dates) in the LLM context.

## Issues and fixes

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | `docker compose up` failed mid-pull with `httpReadSeeker: failed open ... EOF` | Unstable connection to Docker Hub CDN; `compose pull` stalled silently on retry | Pulled the 8 missing images one by one with retries, then `docker compose up -d` |
| 2 | Dify showed documents as "Available" but retrieval returned nothing; worker log: `store is read-only due to: resource pressure` | Host disk at 97%; Weaviate switches to read-only above 90% disk usage | Freed ~32 GB (Docker build cache, unused CI image); added `docker-compose.override.yaml` raising `DISK_USE_READONLY_PERCENTAGE` to 97; re-indexed by disabling and re-enabling each document; verified 77 vectors in Weaviate |

Lesson from #2: the UI status was misleading. Verify indexing with a retrieval test (or a vector count), not the document status.

## Known retrieval weakness

Markdown table rows (hotel limits) become separate child chunks without the table header, so their match scores are low. Answers still work because the full parent document is returned. To revisit after the baseline evaluation.
