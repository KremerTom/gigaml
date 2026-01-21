# Financial Research Agent: Technical Architecture

## Overview

This system implements a conversational AI agent capable of answering natural language questions about equity research reports. The architecture consists of three primary components: a PDF ingestion pipeline, a hybrid storage layer (relational + vector), and a multi-turn conversational agent with function calling capabilities.

---

## 1. Data Ingestion Pipeline

### Input Processing
The pipeline ingests analyst research PDFs (typically 4 pages each) containing structured financial data, tabular statements, and qualitative commentary. Text and table extraction is performed locally using `pdfplumber`, avoiding the latency and cost of vision-based extraction.

### Extraction Strategy
Rather than treating each PDF as a monolithic document, the system employs page-specific extraction prompts:

- **Page 1**: Company metadata, market data, shareholding patterns, analyst forecasts, and business overview
- **Page 2**: Quarterly P&L, segment revenue breakdowns, valuation models
- **Page 3**: Annual financials (P&L, Balance Sheet, Cash Flow), key ratios
- **Page 4**: Rating history

Each page's extracted text is sent to GPT-5 with a structured JSON schema. The model returns normalized data that maps directly to database tables.

### Parallelization
Ingestion is parallelized at the page level using a thread pool (80 concurrent workers). Pages complete independently and flush to storage immediately upon extraction. A queueing mechanism handles race conditions where pages 2-4 complete before page 1 (which establishes the company record).

Retry logic with exponential backoff handles transient API failures.

---

## 2. Storage Architecture

### Relational Layer (SQLite)
Quantitative data is stored in a normalized SQLite schema:

| Table | Purpose |
|-------|---------|
| `companies` | Company master data (name, sector, exchange codes) |
| `documents` | Source document metadata and ratings |
| `metrics` | Point-in-time metrics (CMP, target price, shareholding %) |
| `time_series` | Historical financials indexed by period (FY24A, FY25E, etc.) |
| `qualitative` | Free-text content (business descriptions, analyst commentary) |

This structure supports arbitrary SQL queries, metric comparisons across companies, and time-series analysis.

### Vector Layer (ChromaDB)
Qualitative text is additionally embedded and stored in ChromaDB using OpenAI's `text-embedding-3-small` model. This enables semantic similarity search for queries like "which companies have exposure to renewable energy" that cannot be answered through keyword matching alone.

Documents are indexed with metadata (company name, page number, content type) to support filtered retrieval.

---

## 3. Conversational Agent

### Architecture
The agent uses GPT-5 with function calling to decompose user questions into tool invocations. The conversation loop supports multi-turn context, allowing follow-up questions and clarifications.

### Available Tools

| Tool | Function |
|------|----------|
| `list_companies` | Enumerate companies in corpus |
| `get_company_metrics` | Retrieve all metrics for a company |
| `get_time_series` | Fetch financial statement data by table type |
| `get_qualitative` | Return full qualitative text for a company |
| `search_qualitative` | Keyword search within qualitative content |
| `semantic_search` | Vector similarity search across all qualitative data |
| `compare_companies` | Rank companies by a specific metric |
| `query_database` | Execute arbitrary SELECT queries |

### Retrieval Strategy
For factual questions (e.g., "What is Sun Pharma's target price?"), the agent calls `get_company_metrics` and extracts the relevant field.

For conceptual questions (e.g., "Which banks have undergone mergers?"), the agent first attempts `search_qualitative` with relevant keywords, then falls back to `semantic_search` if keyword matching fails.

### Guardrails
The system prompt enforces strict corpus-only responses:
- No external knowledge or web lookups
- Explicit error messages for missing companies or data
- Mandatory source citation for all answers

---

## 4. Performance Characteristics

| Metric | Value |
|--------|-------|
| Ingestion throughput | ~20 PDFs in 4-5 minutes (80 pages) |
| API calls per PDF | 4 (one per page) |
| Storage footprint | ~5MB SQLite + ~2MB vector index per 20 PDFs |
| Query latency | 2-5 seconds (includes LLM reasoning) |

---

## 5. Limitations and Future Work

- **Schema rigidity**: The current extraction prompts assume a consistent 4-page format. Documents with different structures require prompt updates.
- **Embedding granularity**: Qualitative content is embedded at the page level. Chunk-level embedding would improve retrieval precision for long documents.
- **No incremental updates**: Re-ingesting a PDF replaces existing records rather than merging changes.

---

## Dependencies

- Python 3.10+
- OpenAI API (GPT-5, text-embedding-3-small)
- pdfplumber (text extraction)
- ChromaDB (vector storage)
- SQLite (relational storage)
