# Data Ingestion Pipeline - Implementation Plan

## Overview
This document outlines the complete implementation plan for the data ingestion pipeline that processes equity research PDFs and prepares them for the AI agent's query workflow.

## Design Decisions

### Storage & Configuration
- **Schema Storage:** JSON file (`data/schema.json`) for easy inspection, version control, and portability
- **PDF Storage:** PDFs stored in repo at `data/pdfs/` for now
  - **Future Optimization:** Migrate to blob storage (investigate free Python options like MinIO local, or cloud-agnostic solutions)
- **Image Quality:** High resolution (300 DPI) for maximum accuracy with GPT-5 Vision
- **Processing Mode:** Batch concurrent processing (5-10 parallel API calls) for performance
- **Incremental Updates:** Support adding new PDFs without reprocessing via manifest tracking
- **Error Handling:** Skip failed PDFs, log errors, continue processing remaining files

### AI Models
- **Vision Tasks:** GPT-5 Vision for PDF page analysis and data extraction
- **Text Tasks:** GPT-5 for schema evolution, synonym detection, and structured reasoning
- **Note:** Using latest OpenAI models (GPT-5 family, 2026)

---

## Project Structure

```
gigaml/
├── Context/
│   ├── context.md              # Project overview & requirements
│   └── ingestion_plan.md       # This file
├── src/
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── pdf_processor.py      # PDF to image conversion
│   │   ├── schema_generator.py   # Schema generation & evolution
│   │   ├── data_extractor.py     # Data extraction with Structured Outputs
│   │   ├── storage.py            # SQLite + vector store management
│   │   └── manifest.py           # Track processed PDFs
│   ├── agent/                    # (future: query workflow)
│   │   └── __init__.py
│   └── utils/
│       ├── __init__.py
│       └── config.py             # Configuration management
├── data/
│   ├── pdfs/                     # Input PDFs (user drops PDFs here)
│   ├── images/                   # Temporary high-res images
│   ├── database/
│   │   └── financial_data.db     # SQLite database
│   ├── schema.json               # Dynamic schema with synonyms
│   └── manifest.json             # Tracks which PDFs processed
├── .env                          # OpenAI API key
├── .gitignore                    # Ignore images/, .env, database files
├── requirements.txt
└── ingest.py                     # CLI entry point
```

---

## Phase-by-Phase Implementation

### **Phase 1: Project Setup & Configuration**

**Tasks:**
1. Create directory structure
2. Set up `requirements.txt`:
   ```txt
   pdf2image>=1.16.0
   pillow>=10.0.0
   openai>=1.54.0
   python-dotenv>=1.0.0
   pydantic>=2.0.0
   ```
3. Create `.env` template for OpenAI API key
4. Create `config.py` with:
   - OpenAI API settings (model names, temperature=0 for consistency)
   - Image quality (DPI=300, format=PNG)
   - Batch size (5-10 concurrent API calls)
   - Directory paths

**Deliverables:**
- Complete folder structure
- Configuration management system
- Environment setup

---

### **Phase 2: PDF to Image Conversion**

**Module:** `src/ingestion/pdf_processor.py`

**Functions:**
```python
async def convert_pdf_to_images(
    pdf_path: str,
    output_dir: str = "data/images",
    dpi: int = 300
) -> List[str]:
    """
    Convert PDF pages to high-resolution images.

    Returns:
        List of image file paths (one per page)
    """
```

**Features:**
- Convert PDFs to PNG images at 300 DPI
- Handle multi-page documents
- Cache images with hash-based naming to avoid reconversion
- Clean up old cached images if needed
- Async support for potential parallel processing

**Dependencies:**
- `pdf2image` library (requires poppler-utils system dependency)
- `Pillow` for image handling

**Error Handling:**
- Invalid/corrupted PDFs → log error, skip file
- Missing dependencies → clear error message with installation instructions

---

### **Phase 3: Schema Generation (Batch Processing)**

**Module:** `src/ingestion/schema_generator.py`

#### Step 3.1: Initial Field Discovery

**Process:**
1. Select first 3-5 PDFs for initial schema
2. Convert to images
3. Use async batch processing to send pages to GPT-5 Vision
4. Aggregate results into unified schema

**GPT-5 Vision Prompt Template:**
```
You are analyzing a financial equity research document from an Indian investment service provider.

Extract ALL fields, metrics, and data points visible in this page. Categorize them as:

1. QUANTITATIVE FIELDS (numbers, percentages, dates, financial metrics):
   Examples: revenue, EBITDA, market cap, P/E ratio, growth rates, margins, total assets, net profit
   - Include the specific time period if visible (FY24, Q3 2023, etc.)

2. QUALITATIVE FIELDS (text sections, analysis, commentary):
   Examples: business overview, competitive advantages, key risks, opportunities,
   management commentary, industry trends, valuation rationale

3. METADATA (document/company identifiers):
   Examples: company name, ticker symbol, sector/industry, report date, analyst name

For each field identified, provide:
- Field name (descriptive, lowercase with underscores)
- Category (quantitative/qualitative/metadata)
- Data type (float/integer/string/date/text)
- Unit if applicable (INR crore, USD million, percentage, etc.)

Return as structured JSON matching this format:
{
  "fields": [
    {
      "name": "revenue_fy24",
      "category": "quantitative",
      "data_type": "float",
      "unit": "INR_crore"
    },
    ...
  ]
}
```

**Batch Processing:**
```python
async def discover_fields_batch(
    image_paths: List[str],
    batch_size: int = 10
) -> Dict[str, Any]:
    """
    Process multiple pages concurrently.
    Uses asyncio.gather() for parallel API calls.
    """
```

#### Step 3.2: Schema Structure

**File:** `data/schema.json`

```json
{
  "version": "1.0",
  "last_updated": "2026-01-21T10:00:00Z",
  "fields": {
    "company_name": {
      "type": "metadata",
      "data_type": "string",
      "synonyms": [],
      "required": true,
      "description": "Company name"
    },
    "ticker": {
      "type": "metadata",
      "data_type": "string",
      "synonyms": ["stock_symbol", "ticker_symbol"],
      "required": false,
      "description": "Stock ticker symbol"
    },
    "revenue_fy24": {
      "type": "quantitative",
      "data_type": "float",
      "unit": "INR_crore",
      "synonyms": ["revenue_2024", "fy24_revenue", "revenues_fy24", "total_revenue_fy24"],
      "required": false,
      "description": "Total revenue for fiscal year 2024"
    },
    "ebitda_margin_fy24": {
      "type": "quantitative",
      "data_type": "float",
      "unit": "percentage",
      "synonyms": ["ebitda_margin_2024", "fy24_ebitda_margin"],
      "required": false,
      "description": "EBITDA margin for fiscal year 2024"
    },
    "business_overview": {
      "type": "qualitative",
      "data_type": "text",
      "synonyms": ["company_overview", "business_description", "about_company"],
      "required": false,
      "description": "Description of company's business model and operations"
    },
    "key_risks": {
      "type": "qualitative",
      "data_type": "text",
      "synonyms": ["risk_factors", "risks", "key_risk_factors"],
      "required": false,
      "description": "Key risks and challenges facing the company"
    }
  },
  "statistics": {
    "total_fields": 47,
    "quantitative_fields": 23,
    "qualitative_fields": 18,
    "metadata_fields": 6
  },
  "processed_for_schema": ["sample1.pdf", "sample2.pdf", "sample3.pdf"]
}
```

**Functions:**
```python
def initialize_schema() -> Dict[str, Any]:
    """Create initial empty schema structure"""

def save_schema(schema: Dict[str, Any], path: str = "data/schema.json"):
    """Save schema to JSON file"""

def load_schema(path: str = "data/schema.json") -> Dict[str, Any]:
    """Load schema from JSON file"""

def add_field(schema: Dict, field_name: str, field_config: Dict):
    """Add new field to schema"""

def add_synonym(schema: Dict, field_name: str, synonym: str):
    """Add synonym to existing field"""
```

---

### **Phase 4: Schema Evolution & Synonym Detection**

**Module:** `src/ingestion/schema_generator.py`

#### Step 4.1: Process Remaining PDFs

**Process:**
1. Load existing schema
2. Check manifest to identify unprocessed PDFs
3. Process new PDFs using same field discovery approach
4. Collect all new fields found

#### Step 4.2: Synonym Detection (Batch)

**GPT-5 Prompt Template:**
```
You are a financial data schema expert. Your task is to identify synonyms and merge duplicate fields.

EXISTING SCHEMA FIELDS:
{json.dumps(existing_fields, indent=2)}

NEW FIELDS DISCOVERED:
{json.dumps(new_fields, indent=2)}

For each new field, determine:
1. Is it a SYNONYM of an existing field? (same concept, different wording)
   - Consider variations like: "revenue" vs "revenues", "FY24" vs "2024" vs "fy_24"
   - Consider semantic equivalence: "market_cap" vs "market_capitalization"

2. Is it a GENUINELY NEW field? (represents different data)

Return as JSON:
{
  "synonyms": {
    "new_field_name": "existing_field_name",
    ...
  },
  "new_fields": [
    {
      "name": "genuinely_new_field",
      "category": "quantitative",
      "data_type": "float",
      "unit": "INR_crore"
    },
    ...
  ],
  "reasoning": {
    "new_field_name": "Explanation of why this is a synonym/new field"
  }
}
```

**Function:**
```python
async def detect_synonyms(
    existing_schema: Dict[str, Any],
    new_fields: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Use GPT-5 to identify synonyms and genuinely new fields.
    Single API call for all new fields (batch processing).
    """
```

#### Step 4.3: Schema Update

**Process:**
1. Add synonyms to existing fields in schema
2. Add genuinely new fields to schema
3. Update statistics
4. Update `last_updated` timestamp
5. Add processed PDF names to `processed_for_schema` list
6. Save updated schema

**Function:**
```python
def evolve_schema(
    schema: Dict[str, Any],
    synonym_mappings: Dict[str, str],
    new_fields: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Update schema with synonyms and new fields"""
```

---

### **Phase 5: Data Extraction (Batch + Structured Outputs)**

**Module:** `src/ingestion/data_extractor.py`

#### Step 5.1: Dynamic Pydantic Model Generation

**Purpose:** Generate Pydantic models from schema for OpenAI Structured Outputs

**Function:**
```python
def generate_pydantic_models(schema: Dict[str, Any]) -> Tuple[Type[BaseModel], Type[BaseModel]]:
    """
    Dynamically create Pydantic models from schema.

    Returns:
        (QuantitativeDataModel, QualitativeDataModel)
    """
```

**Example Generated Models:**
```python
class QuantitativeData(BaseModel):
    """Dynamically generated from schema"""
    company_name: str
    ticker: Optional[str] = None
    sector: Optional[str] = None
    report_date: Optional[str] = None
    revenue_fy24: Optional[float] = None
    ebitda_fy24: Optional[float] = None
    net_profit_fy24: Optional[float] = None
    market_cap: Optional[float] = None
    # ... all quantitative fields from schema

class QualitativeData(BaseModel):
    """Dynamically generated from schema"""
    company_name: str
    business_overview: Optional[str] = None
    key_risks: Optional[str] = None
    competitive_advantages: Optional[str] = None
    management_commentary: Optional[str] = None
    # ... all qualitative fields from schema
```

#### Step 5.2: Quantitative Data Extraction

**GPT-5 Vision Prompt Template:**
```
You are extracting structured financial data from an equity research document.

Extract the following fields from this document page. Use the exact field names provided.

FIELDS TO EXTRACT:
{json.dumps(quantitative_fields, indent=2)}

INSTRUCTIONS:
- Extract only data that is explicitly present in the document
- For numeric fields, extract the number only (no currency symbols or units)
- For dates, use ISO format (YYYY-MM-DD) or fiscal year notation (FY24)
- If a field is not present or unclear, return null
- Be precise - do not estimate or infer values not explicitly stated
- Pay attention to units (crores vs millions, etc.)

Return data as JSON matching the provided schema.
```

**Function:**
```python
async def extract_quantitative_data_batch(
    pdf_path: str,
    image_paths: List[str],
    schema: Dict[str, Any],
    batch_size: int = 5
) -> Dict[str, Any]:
    """
    Extract quantitative data from PDF using GPT-5 Vision.
    Uses OpenAI Structured Outputs for guaranteed JSON schema compliance.

    Returns aggregated data from all pages.
    """
```

**OpenAI API Usage:**
```python
response = await client.chat.completions.create(
    model="gpt-5-vision",  # or appropriate GPT-5 vision model name
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
            ]
        }
    ],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "quantitative_data",
            "schema": QuantitativeData.model_json_schema()
        }
    },
    temperature=0  # Deterministic extraction
)
```

#### Step 5.3: Qualitative Data Extraction

**GPT-5 Vision Prompt Template:**
```
You are extracting qualitative text content from a financial research document.

Extract the following sections from this document page:

SECTIONS TO EXTRACT:
{json.dumps(qualitative_fields, indent=2)}

INSTRUCTIONS:
- Extract complete text passages, not summaries
- Preserve the original wording and tone
- Include relevant context (e.g., "According to management...")
- Identify which section/heading each passage belongs to
- If a section is not present on this page, return null
- Maintain paragraph structure where appropriate

For each extracted section, also provide:
- Section heading (if visible)
- Page number
- Approximate location on page (top/middle/bottom)

Return as structured JSON.
```

**Function:**
```python
async def extract_qualitative_data_batch(
    pdf_path: str,
    image_paths: List[str],
    schema: Dict[str, Any],
    batch_size: int = 5
) -> List[Dict[str, Any]]:
    """
    Extract qualitative text chunks from PDF.
    Returns list of text chunks with metadata.
    """
```

**Output Format:**
```python
[
    {
        "company_name": "XYZ Corp",
        "field_name": "business_overview",
        "text": "XYZ Corp is a leading manufacturer...",
        "metadata": {
            "section_heading": "Company Overview",
            "page_number": 2,
            "location": "top",
            "document": "xyz_report_2024.pdf"
        }
    },
    ...
]
```

#### Step 5.4: Error Handling & Recovery

**Strategies:**
- **API Rate Limits:** Exponential backoff with retry logic
- **Invalid Responses:** Log warning, mark field as null, continue
- **Corrupted Images:** Skip page, log error, continue with remaining pages
- **Failed PDFs:** Log to `errors.log`, update manifest with "failed" status, continue with next PDF

**Function:**
```python
async def extract_pdf_with_retry(
    pdf_path: str,
    max_retries: int = 3
) -> Tuple[Optional[Dict], Optional[List[Dict]], Optional[str]]:
    """
    Extract data from PDF with retry logic.

    Returns:
        (quantitative_data, qualitative_data, error_message)
        If successful: (data, data, None)
        If failed: (None, None, error_msg)
    """
```

**Error Log Format (`data/errors.log`):**
```
[2026-01-21 10:15:23] PDF: report_abc.pdf | Error: API timeout after 3 retries
[2026-01-21 10:18:45] PDF: report_xyz.pdf | Error: Invalid image format on page 5
```

---

### **Phase 6: Storage Implementation**

**Module:** `src/ingestion/storage.py`

#### Step 6.1: SQLite Database Design

**Schema:**
```sql
-- Documents metadata (tracks all processed PDFs)
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT UNIQUE NOT NULL,
    file_hash TEXT,  -- SHA256 hash to detect changes
    processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL,  -- 'success', 'failed', 'processing'
    error_message TEXT,
    page_count INTEGER,
    pdf_date DATE,  -- Report date from PDF
    analyst_name TEXT
);

-- Companies (one per PDF typically, but handle multiple)
CREATE TABLE companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    ticker TEXT UNIQUE,
    sector TEXT,
    industry TEXT,
    document_id INTEGER NOT NULL,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

-- Quantitative metrics (pivot table for flexibility)
CREATE TABLE metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    field_name TEXT NOT NULL,  -- e.g., 'revenue_fy24', 'ebitda_margin_q3_2023'
    value REAL NOT NULL,
    unit TEXT,  -- 'INR_crore', 'percentage', etc.
    date_context TEXT,  -- 'FY24', 'Q3 2023', '2024-03-31', etc.
    document_id INTEGER NOT NULL,
    page_number INTEGER,
    extraction_confidence REAL,  -- Optional: confidence score
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

-- Indexes for fast queries
CREATE INDEX idx_metrics_field ON metrics(field_name);
CREATE INDEX idx_metrics_company ON metrics(company_id);
CREATE INDEX idx_metrics_company_field ON metrics(company_id, field_name);
CREATE INDEX idx_companies_ticker ON companies(ticker);
CREATE INDEX idx_companies_sector ON companies(sector);
CREATE INDEX idx_documents_status ON documents(status);
```

**Why Pivot Table Approach:**
- ✅ Handles 100+ dynamic fields without schema changes
- ✅ Easy to add new metrics discovered later
- ✅ Flexible querying by field_name
- ✅ Supports multiple time periods per company
- ❌ Slightly slower than denormalized table (acceptable tradeoff)

**Future Optimization (Phase 7+):**
```sql
-- Materialized view for common queries (to be created later)
CREATE TABLE company_financials_snapshot AS
SELECT
    c.id as company_id,
    c.name,
    c.ticker,
    MAX(CASE WHEN m.field_name = 'revenue_fy24' THEN m.value END) as revenue_fy24,
    MAX(CASE WHEN m.field_name = 'ebitda_fy24' THEN m.value END) as ebitda_fy24,
    MAX(CASE WHEN m.field_name = 'net_profit_fy24' THEN m.value END) as net_profit_fy24,
    -- ... other common fields
FROM companies c
LEFT JOIN metrics m ON c.id = m.company_id
GROUP BY c.id;

-- Refresh this view after each ingestion run
```

**Functions:**
```python
class DatabaseManager:
    def __init__(self, db_path: str = "data/database/financial_data.db"):
        self.db_path = db_path
        self.conn = None

    def initialize_database(self):
        """Create tables if they don't exist"""

    def insert_document(self, filename: str, status: str, **kwargs) -> int:
        """Insert document record, return document_id"""

    def insert_company(self, name: str, document_id: int, **kwargs) -> int:
        """Insert company record, return company_id"""

    def insert_metrics_batch(self, metrics: List[Dict[str, Any]]):
        """Bulk insert metrics for efficiency"""

    def update_document_status(self, document_id: int, status: str, error: str = None):
        """Update document processing status"""

    def get_company_by_ticker(self, ticker: str) -> Optional[Dict]:
        """Retrieve company by ticker"""

    def clear_all_data(self):
        """Drop all tables and recreate"""
```

#### Step 6.2: OpenAI Vector Store Setup

**Purpose:** Store qualitative text chunks for semantic search during query phase

**Process:**
1. Create vector store via OpenAI API
2. Format qualitative chunks with rich metadata
3. Upload to OpenAI Files API
4. Add files to vector store
5. Store vector_store_id for later retrieval

**Text Chunk Format:**
```
COMPANY: XYZ Corporation
TICKER: XYZ
SECTOR: Technology
DOCUMENT: xyz_corp_equity_research_2024.pdf
REPORT_DATE: 2024-03-15
SECTION: Business Overview
PAGE: 3

XYZ Corporation is a leading provider of cloud infrastructure solutions
in the Indian market. Founded in 2010, the company has grown to serve
over 5,000 enterprise customers across banking, healthcare, and retail
sectors. The company's competitive advantage lies in its localized data
centers and 24/7 customer support in regional languages...

---
```

**Metadata Schema:**
```python
{
    "company_name": "XYZ Corporation",
    "ticker": "XYZ",
    "sector": "Technology",
    "document_filename": "xyz_corp_equity_research_2024.pdf",
    "document_id": 123,
    "report_date": "2024-03-15",
    "section": "Business Overview",
    "page_number": 3,
    "field_name": "business_overview",
    "chunk_id": "xyz_corp_business_overview_p3"
}
```

**Functions:**
```python
class VectorStoreManager:
    def __init__(self, api_key: str):
        self.client = openai.Client(api_key=api_key)
        self.vector_store_id = None

    def create_vector_store(self, name: str = "financial_research_corpus") -> str:
        """Create new vector store, return ID"""

    def upload_text_chunks(self, chunks: List[Dict[str, Any]]) -> List[str]:
        """
        Upload text chunks to vector store.
        Each chunk includes text + metadata.
        Returns list of file IDs.
        """

    def add_files_to_vector_store(self, file_ids: List[str]):
        """Add uploaded files to vector store"""

    def delete_vector_store(self):
        """Delete vector store and all associated files"""

    def get_vector_store_stats(self) -> Dict[str, Any]:
        """Return statistics about vector store"""
```

**Configuration Storage:**
Save vector_store_id to a config file for query phase:
```json
// data/vector_store_config.json
{
  "vector_store_id": "vs_abc123xyz",
  "created_date": "2026-01-21T10:00:00Z",
  "total_chunks": 342,
  "total_files": 18
}
```

#### Step 6.3: Manifest Tracking

**Purpose:** Track which PDFs have been processed to enable incremental updates

**File:** `data/manifest.json`

**Structure:**
```json
{
  "version": "1.0",
  "last_updated": "2026-01-21T15:30:00Z",
  "processed_pdfs": {
    "report_xyz_corp_2024.pdf": {
      "file_hash": "sha256:abc123...",
      "processed_date": "2026-01-21T10:00:00Z",
      "status": "success",
      "pages": 15,
      "document_id": 1,
      "company_name": "XYZ Corporation",
      "ticker": "XYZ"
    },
    "report_abc_ltd_2024.pdf": {
      "file_hash": "sha256:def456...",
      "processed_date": "2026-01-21T10:05:00Z",
      "status": "failed",
      "error": "API timeout after 3 retries",
      "pages": null,
      "document_id": null
    },
    "report_pqr_industries_2024.pdf": {
      "file_hash": "sha256:ghi789...",
      "processed_date": "2026-01-21T10:10:00Z",
      "status": "success",
      "pages": 22,
      "document_id": 3,
      "company_name": "PQR Industries",
      "ticker": "PQR"
    }
  },
  "statistics": {
    "total_pdfs": 20,
    "successful": 18,
    "failed": 2,
    "total_pages_processed": 287,
    "total_companies": 18
  }
}
```

**Functions:**
```python
class ManifestManager:
    def __init__(self, manifest_path: str = "data/manifest.json"):
        self.manifest_path = manifest_path
        self.manifest = None

    def load_manifest(self) -> Dict[str, Any]:
        """Load manifest from file or create new"""

    def save_manifest(self):
        """Save manifest to file"""

    def is_pdf_processed(self, filename: str) -> bool:
        """Check if PDF already processed successfully"""

    def add_pdf_record(self, filename: str, status: str, **kwargs):
        """Add or update PDF processing record"""

    def get_unprocessed_pdfs(self, pdf_directory: str) -> List[str]:
        """Return list of PDF files not yet processed"""

    def get_failed_pdfs(self) -> List[str]:
        """Return list of PDFs that failed processing"""

    def compute_file_hash(self, filepath: str) -> str:
        """Compute SHA256 hash of file"""
```

**Incremental Processing Logic:**
1. Scan `data/pdfs/` directory
2. Load manifest
3. For each PDF:
   - If not in manifest → process
   - If in manifest with status "failed" → reprocess
   - If in manifest with status "success":
     - Compute current file hash
     - If hash matches → skip
     - If hash differs → reprocess (file was updated)

---

### **Phase 7: Data Clearing Functions**

**Module:** `src/ingestion/storage.py`

**Purpose:** Allow fresh starts for development/testing

**Functions:**
```python
def clear_database(db_path: str = "data/database/financial_data.db"):
    """
    Drop all tables and recreate empty schema.
    Preserves database file.
    """

def clear_vector_store(vector_store_id: str):
    """
    Delete vector store and all associated files from OpenAI.
    """

def clear_images(image_dir: str = "data/images"):
    """
    Delete all cached images.
    """

def clear_schema(schema_path: str = "data/schema.json"):
    """
    Delete schema file (will be regenerated on next run).
    """

def clear_manifest(manifest_path: str = "data/manifest.json"):
    """
    Delete manifest file.
    """

def clear_all():
    """
    Nuclear option: clear everything.
    - Drop database tables
    - Delete vector store
    - Delete cached images
    - Delete schema file
    - Delete manifest file
    - Keep PDF files and directory structure
    """
```

**Safety Measures:**
- Require confirmation flag: `clear_all(confirm=True)`
- Log what's being deleted
- Preserve original PDF files
- Create backup of schema before deletion (optional)

---

### **Phase 8: Ingestion CLI**

**Module:** `ingest.py` (root level)

**Command Interface:**
```bash
# Full pipeline: schema generation + data extraction
python ingest.py --full

# Step-by-step workflow
python ingest.py --schema-only      # Generate/update schema from PDFs
python ingest.py --extract-only     # Extract data using existing schema

# Incremental updates
python ingest.py --incremental      # Process only new/updated PDFs

# Maintenance
python ingest.py --clear            # Clear all data (requires --confirm)
python ingest.py --clear-images     # Clear cached images only
python ingest.py --retry-failed     # Retry PDFs that failed previously

# Information
python ingest.py --status           # Show ingestion statistics
python ingest.py --validate         # Validate data integrity

# Configuration
python ingest.py --config           # Show current configuration
```

**Status Output Example:**
```
┌─────────────────────────────────────────────────────────────┐
│ Financial Research Ingestion Status                         │
├─────────────────────────────────────────────────────────────┤
│ Schema                                                       │
│   Total fields: 47                                          │
│   ├─ Quantitative: 23                                       │
│   ├─ Qualitative: 18                                        │
│   └─ Metadata: 6                                            │
│   Last updated: 2026-01-21 15:30:00                         │
│                                                              │
│ PDF Processing                                               │
│   Total PDFs: 20                                            │
│   ├─ Successful: 18                                         │
│   ├─ Failed: 2                                              │
│   └─ Pending: 0                                             │
│   Total pages: 287                                          │
│                                                              │
│ Database (SQLite)                                            │
│   Companies: 18                                             │
│   Metrics: 1,247 data points                                │
│   Documents: 18                                             │
│   Database size: 2.3 MB                                     │
│                                                              │
│ Vector Store (OpenAI)                                        │
│   Chunks: 342                                               │
│   Files: 18                                                 │
│   Vector Store ID: vs_abc123xyz                             │
│                                                              │
│ Failed PDFs                                                  │
│   1. report_abc_ltd_2024.pdf - API timeout                  │
│   2. report_failed_corp.pdf - Corrupted PDF                 │
│                                                              │
│ Last ingestion: 2026-01-21 15:30:00                         │
└─────────────────────────────────────────────────────────────┘
```

**Implementation:**
```python
# ingest.py
import argparse
import asyncio
import sys
from src.ingestion.pdf_processor import PDFProcessor
from src.ingestion.schema_generator import SchemaGenerator
from src.ingestion.data_extractor import DataExtractor
from src.ingestion.storage import DatabaseManager, VectorStoreManager
from src.ingestion.manifest import ManifestManager
from src.utils.config import Config

async def main():
    parser = argparse.ArgumentParser(
        description="Financial Research PDF Ingestion Pipeline"
    )
    parser.add_argument("--full", action="store_true",
                       help="Run full pipeline (schema + extraction)")
    parser.add_argument("--schema-only", action="store_true",
                       help="Generate/update schema only")
    parser.add_argument("--extract-only", action="store_true",
                       help="Extract data using existing schema")
    parser.add_argument("--incremental", action="store_true",
                       help="Process only new/updated PDFs")
    parser.add_argument("--clear", action="store_true",
                       help="Clear all data (requires --confirm)")
    parser.add_argument("--confirm", action="store_true",
                       help="Confirm destructive operations")
    parser.add_argument("--status", action="store_true",
                       help="Show ingestion status")
    parser.add_argument("--retry-failed", action="store_true",
                       help="Retry failed PDFs")

    args = parser.parse_args()

    # Load configuration
    config = Config()

    # Handle different commands
    if args.status:
        await show_status(config)
    elif args.clear:
        if not args.confirm:
            print("⚠️  Clearing all data requires --confirm flag")
            sys.exit(1)
        await clear_all_data(config)
    elif args.full:
        await run_full_pipeline(config)
    elif args.schema_only:
        await generate_schema(config)
    elif args.extract_only:
        await extract_data(config)
    elif args.incremental:
        await incremental_update(config)
    elif args.retry_failed:
        await retry_failed_pdfs(config)
    else:
        parser.print_help()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Implementation Checklist

### Phase 1: Setup
- [ ] Create directory structure
- [ ] Set up `requirements.txt`
- [ ] Create `.env` template
- [ ] Implement `config.py`
- [ ] Create `.gitignore` (exclude images/, .env, *.db)
- [ ] Test environment setup

### Phase 2: PDF Processing
- [ ] Implement `pdf_processor.py`
- [ ] Test PDF to image conversion (single PDF)
- [ ] Test with multi-page PDF
- [ ] Implement image caching
- [ ] Handle error cases (corrupted PDF, missing dependencies)

### Phase 3: Schema Generation
- [ ] Implement initial field discovery
- [ ] Create GPT-5 Vision prompts for field extraction
- [ ] Implement batch processing
- [ ] Test with 3-5 sample PDFs
- [ ] Implement schema JSON structure
- [ ] Implement schema save/load functions

### Phase 4: Schema Evolution
- [ ] Implement synonym detection logic
- [ ] Create GPT-5 prompts for synonym identification
- [ ] Test schema merging with new PDFs
- [ ] Validate synonym mappings
- [ ] Test incremental schema updates

### Phase 5: Data Extraction
- [ ] Implement dynamic Pydantic model generation
- [ ] Create quantitative extraction prompts
- [ ] Create qualitative extraction prompts
- [ ] Implement Structured Outputs API calls
- [ ] Implement batch processing for extraction
- [ ] Test with sample PDFs
- [ ] Implement error handling and retry logic
- [ ] Test with edge cases (missing data, unusual formats)

### Phase 6: Storage
- [ ] Design and create SQLite schema
- [ ] Implement `DatabaseManager` class
- [ ] Test database operations (insert, query)
- [ ] Implement OpenAI Vector Store integration
- [ ] Test vector store upload and retrieval
- [ ] Implement `ManifestManager` class
- [ ] Test manifest tracking
- [ ] Test incremental processing logic

### Phase 7: Data Clearing
- [ ] Implement clear functions
- [ ] Add safety confirmations
- [ ] Test each clear function
- [ ] Test `clear_all()` function

### Phase 8: CLI Interface
- [ ] Implement `ingest.py` CLI
- [ ] Create argparse interface
- [ ] Implement `--status` command
- [ ] Implement `--full` pipeline
- [ ] Implement `--schema-only` command
- [ ] Implement `--extract-only` command
- [ ] Implement `--incremental` command
- [ ] Implement `--clear` command
- [ ] Test all CLI commands
- [ ] Create user documentation

### Testing & Validation
- [ ] Test with all 20 PDFs
- [ ] Validate schema completeness
- [ ] Validate data accuracy (spot check)
- [ ] Test error handling (corrupt PDF, API failures)
- [ ] Test incremental updates
- [ ] Performance testing (batch sizes, concurrent calls)
- [ ] Document any issues or limitations

---

## Future Optimizations (Post-MVP)

### Blob Storage Migration
**Current:** PDFs stored in `data/pdfs/` within repo
**Future:** Migrate to blob storage

**Options:**
1. **Local Blob Storage:**
   - MinIO (S3-compatible, free, local)
   - Setup: Docker container or standalone binary

2. **Cloud Blob Storage (if restrictions lifted):**
   - AWS S3
   - Google Cloud Storage
   - Azure Blob Storage

3. **Implementation:**
   - Abstract storage layer: `BlobStorageInterface`
   - Support multiple backends (local filesystem, MinIO, S3)
   - Configuration-driven selection

**Benefits:**
- Handle large PDF collections without bloating repo
- Better version control (exclude large binaries)
- Scalable to 20,000+ documents

### Performance Optimizations
- Implement connection pooling for SQLite
- Use batch inserts for metrics (already planned)
- Create materialized views for common queries
- Cache frequently accessed schema in memory
- Implement progress bars for long-running operations
- Add logging levels (DEBUG, INFO, WARNING, ERROR)

### Data Quality
- Implement extraction confidence scores
- Flag low-confidence extractions for manual review
- Add data validation rules (e.g., revenue > 0)
- Duplicate detection across PDFs
- Consistency checks (e.g., sum of quarters = annual)

### Advanced Features
- Support for multiple fiscal year formats
- Handle currency conversions (USD to INR, etc.)
- Extract and preserve table structures
- OCR fallback for scanned PDFs
- Multi-language support (Hindi, regional languages)

---

## Notes & Assumptions

1. **OpenAI Models:** Using GPT-5 and GPT-5 Vision (2026 latest models)
2. **Token Usage:** Unlimited budget - prioritize accuracy over cost optimization
3. **Scale:** Designed for 20-20,000 PDFs, currently testing with 20
4. **Accuracy:** Grounded in source documents only, no external data
5. **Local-only:** No cloud deployment, all processing happens locally
6. **Schema:** Fully dynamic, supports 100+ fields without code changes
7. **Incremental:** Support for adding new PDFs without full reprocessing
8. **Error Tolerance:** Skip failed PDFs, log errors, continue processing

---

## Questions to Address Later

1. **Table Structure:** Should we create denormalized views for performance? (Revisit after initial testing)
2. **Blob Storage:** Which free Python blob storage solution to recommend? (Research MinIO, local S3)
3. **Schema Validation:** Should we add manual review step for schema? (Current: fully automated)
4. **Confidence Scores:** Should we track extraction confidence? (Future enhancement)
5. **Multi-company PDFs:** How to handle PDFs covering multiple companies? (Current: assumes one company per PDF)

---

_Last Updated: 2026-01-21_
_Author: Tom Kremer (with Claude Code)_
_Status: Planning Complete - Ready for Implementation_
