#!/usr/bin/env python3
"""PDF Ingestion Pipeline - Parallelized text-based extraction with immediate flushing + ChromaDB."""

from pathlib import Path
import sys
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
import pdfplumber
from dotenv import load_dotenv
import os
import sqlite3
import threading
import chromadb
from chromadb.utils import embedding_functions

load_dotenv()

# Schema prompts for each page type
PROMPTS = {
    1: """Extract from this financial research document page 1:
- company_name, sector, bse_code, nse_code, bloomberg_code, report_date, rating
- cmp (current price), target_price, market_cap_cr, enterprise_value_cr, free_float_pct, dividend_yield_pct, week_52_high, week_52_low, beta, face_value
- shareholding: list of {quarter, promoter_pct, fii_pct, mf_pct, public_pct, others_pct}
- forecasts: list of {metric, fy24a, fy25e, fy26e, unit} for Sales, EBITDA, PAT, EPS (values in crores)
- business_overview: FULL business description including:
  * Company history and background
  * Mergers and acquisitions (which companies merged, when, details)
  * Business segments and operations
  * Key products/services
  * Network size (branches, locations, etc.)
  * Any other important company facts
  Extract this WORD FOR WORD from the document - do NOT summarize.

Return JSON. Use null for missing values.""",

    2: """Extract from this financial research document page 2:
- quarterly_pnl: {periods: ["Q4FY24",...], rows: [{metric, values: [...]}]} for Revenue, EBITDA, PAT, EPS
- segment_revenue: {segments: [{name, values}]} if present
- sotp_valuation: {components: [{name, basis, multiple, value_cr, value_per_share}]}
- estimate_changes: {changes: [{metric, fy25e_old, fy25e_new, fy26e_old, fy26e_new}]}

Return JSON. Use null/empty for missing sections.""",

    3: """Extract from this financial research document page 3:
- annual_pnl: {periods: ["FY22A","FY23A","FY24A","FY25E","FY26E"], rows: [{metric, values}]}
- balance_sheet: {periods, assets: [{item, values}], liabilities: [{item, values}]}
- cash_flow: {periods, rows: [{metric, values}]}
- ratios: {periods, rows: [{ratio, values}]} for margins, ROE, PE, PB etc

Return JSON. Use null for missing.""",

    4: """Extract rating history from page 4:
- rating_history: [{date, rating, target_price}]

Return JSON. Skip disclaimer.""",
}

print_lock = threading.Lock()
def log(msg):
    with print_lock:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class Database:
    def __init__(self, path="data/database/financial_data.db"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        
        # ChromaDB for semantic search
        self.chroma = chromadb.PersistentClient(path="data/vectordb")
        openai_ef = embedding_functions.OpenAIEmbeddingFunction(
            api_key=os.getenv("OPENAI_API_KEY"),
            model_name="text-embedding-3-small"
        )
        self.qualitative_collection = self.chroma.get_or_create_collection(
            name="qualitative",
            embedding_function=openai_ef
        )
    
    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS companies (id INTEGER PRIMARY KEY, name TEXT UNIQUE, sector TEXT, bse_code TEXT, nse_code TEXT, bloomberg_code TEXT);
            CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, filename TEXT UNIQUE, company_id INTEGER, report_date TEXT, report_type TEXT, rating TEXT);
            CREATE TABLE IF NOT EXISTS metrics (id INTEGER PRIMARY KEY, company_id INTEGER, document_id INTEGER, field_name TEXT, value REAL, unit TEXT, time_period TEXT);
            CREATE TABLE IF NOT EXISTS time_series (id INTEGER PRIMARY KEY, company_id INTEGER, document_id INTEGER, table_name TEXT, metric TEXT, period TEXT, value REAL, unit TEXT);
            CREATE TABLE IF NOT EXISTS qualitative (id INTEGER PRIMARY KEY, company_id INTEGER, document_id INTEGER, chunk_type TEXT, content TEXT, page_num INTEGER);
            CREATE INDEX IF NOT EXISTS idx_metrics_company ON metrics(company_id);
            CREATE INDEX IF NOT EXISTS idx_ts_company ON time_series(company_id);
        """)
        self.conn.commit()
    
    def save_page1(self, filename: str, data: dict) -> tuple:
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("""INSERT INTO companies (name, sector, bse_code, nse_code, bloomberg_code) 
                          VALUES (?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET sector=excluded.sector RETURNING id""",
                       (data.get("company_name"), data.get("sector"), data.get("bse_code"), 
                        data.get("nse_code"), data.get("bloomberg_code")))
            company_id = cur.fetchone()[0]
            cur.execute("INSERT OR REPLACE INTO documents (filename, company_id, report_date, report_type, rating) VALUES (?,?,?,?,?)",
                       (filename, company_id, data.get("report_date"), "quarterly", data.get("rating")))
            doc_id = cur.lastrowid
            
            # Market metrics
            for field in ["cmp", "target_price", "market_cap_cr", "enterprise_value_cr", 
                         "week_52_high", "week_52_low", "beta", "face_value",
                         "free_float_pct", "dividend_yield_pct"]:
                val = data.get(field)
                if val is not None:
                    unit = "cr" if "_cr" in field else ("pct" if "_pct" in field else "INR")
                    cur.execute("INSERT INTO metrics (company_id, document_id, field_name, value, unit) VALUES (?,?,?,?,?)",
                               (company_id, doc_id, field, val, unit))
            
            # Shareholding
            for q in data.get("shareholding") or []:
                qtr = q.get("quarter", "unknown")
                for field in ["promoter_pct", "fii_pct", "mf_pct", "public_pct", "others_pct"]:
                    val = q.get(field)
                    if val is not None:
                        cur.execute("INSERT INTO metrics (company_id, document_id, field_name, value, unit, time_period) VALUES (?,?,?,?,?,?)",
                                   (company_id, doc_id, field, val, "pct", qtr))
            
            # Forecasts
            for f in data.get("forecasts") or []:
                metric = (f.get("metric") or "unknown").lower().replace(" ", "_")
                unit = f.get("unit", "cr")
                for period in ["fy24a", "fy25e", "fy26e"]:
                    val = f.get(period)
                    if val is not None:
                        cur.execute("INSERT INTO metrics (company_id, document_id, field_name, value, unit, time_period) VALUES (?,?,?,?,?,?)",
                                   (company_id, doc_id, f"{metric}_{period}", val, unit, period.upper()))
            
            # Qualitative (SQLite + ChromaDB - always flush)
            content = data.get("business_overview") or data.get("business_highlights")
            if content:
                cur.execute("INSERT INTO qualitative (company_id, document_id, chunk_type, content, page_num) VALUES (?,?,?,?,?)",
                           (company_id, doc_id, "business_overview", content, 1))
                # Flush to ChromaDB immediately
                doc_id_str = f"{data.get('company_name', 'unknown')}_{doc_id}_p1"
                try:
                    self.qualitative_collection.add(
                        documents=[content],
                        ids=[doc_id_str],
                        metadatas=[{"company": data.get("company_name", ""), "page": 1, "type": "business_overview"}]
                    )
                except Exception:
                    pass
            
            self.conn.commit()
            return company_id, doc_id
    
    def save_time_series(self, company_id: int, doc_id: int, table_name: str, data: dict):
        if not data:
            return
        with self.lock:
            cur = self.conn.cursor()
            periods = data.get("periods") or []
            for row in (data.get("rows") or []) + (data.get("assets") or []) + (data.get("liabilities") or []) + (data.get("segments") or []):
                metric = (row.get("metric") or row.get("item") or row.get("ratio") or row.get("name") or "unknown").lower().replace(" ", "_")
                values = row.get("values") or []
                unit = row.get("unit", "cr")
                for i, val in enumerate(values):
                    if val is not None and i < len(periods):
                        cur.execute("INSERT INTO time_series (company_id, document_id, table_name, metric, period, value, unit) VALUES (?,?,?,?,?,?,?)",
                                   (company_id, doc_id, table_name, metric, periods[i], val, unit))
            self.conn.commit()
    
    def save_qualitative(self, company_id: int, doc_id: int, content: str, chunk_type: str, page_num: int, company_name: str = ""):
        if not content:
            return
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("INSERT INTO qualitative (company_id, document_id, chunk_type, content, page_num) VALUES (?,?,?,?,?)",
                       (company_id, doc_id, chunk_type, content, page_num))
            self.conn.commit()
            # Flush to ChromaDB immediately
            if chunk_type != "rating_history":
                doc_id_str = f"{company_name}_{doc_id}_p{page_num}_{chunk_type}"
                try:
                    self.qualitative_collection.add(
                        documents=[content],
                        ids=[doc_id_str],
                        metadatas=[{"company": company_name, "page": page_num, "type": chunk_type}]
                    )
                except Exception:
                    pass
    
    def get_company_doc(self, filename: str):
        """Get company_id and doc_id for a filename."""
        with self.lock:
            row = self.conn.execute("SELECT company_id, id FROM documents WHERE filename = ?", (filename,)).fetchone()
            return (row["company_id"], row["id"]) if row else (None, None)
    
    def get_stats(self):
        with self.lock:
            return {
                "companies": self.conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0],
                "metrics": self.conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0],
                "time_series": self.conn.execute("SELECT COUNT(*) FROM time_series").fetchone()[0],
                "qualitative": self.conn.execute("SELECT COUNT(*) FROM qualitative").fetchone()[0],
            }


def extract_pdf_pages(pdf_path: Path) -> list:
    """Extract text from all pages of a PDF."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages[:4]):  # Only first 4 pages
            text = page.extract_text() or ""
            tables = page.extract_tables() or []
            table_text = "\n".join(" | ".join(str(c) if c else "" for c in row) for table in tables for row in table if row)
            pages.append({"page_num": i + 1, "text": text, "table_text": table_text})
    return pages


def process_and_save_page(client: OpenAI, db: Database, pdf_name: str, page_num: int, text: str, table_text: str, pending_pages: dict, max_retries: int = 3) -> dict:
    """Process a single page and save immediately to DB with retry logic."""
    if page_num not in PROMPTS:
        return {"pdf": pdf_name, "page": page_num, "success": False, "error": "No prompt"}
    
    prompt = PROMPTS[page_num] + f"\n\nText:\n{text[:6000]}\n\nTables:\n{table_text[:4000]}"
    
    for attempt in range(max_retries):
        try:
            start = time.time()
            response = client.chat.completions.create(
                model="gpt-5",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
            elapsed = time.time() - start
            break  # Success
        except Exception as e:
            if attempt < max_retries - 1:
                log(f"RETRY {pdf_name[:20]}... p{page_num} attempt {attempt+2}/{max_retries}")
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            log(f"FAIL {pdf_name[:20]}... p{page_num}: {str(e)[:30]}")
            return {"pdf": pdf_name, "page": page_num, "success": False, "error": str(e)}
    
    try:
        
        # FLUSH IMMEDIATELY
        if page_num == 1:
            company_id, doc_id = db.save_page1(pdf_name, data)
            # Process any pending pages for this PDF
            if pdf_name in pending_pages:
                for pending in pending_pages[pdf_name]:
                    save_page_data(db, company_id, doc_id, pending["page"], pending["data"])
                del pending_pages[pdf_name]
            log(f"SAVED {pdf_name[:20]}... p1 → {data.get('company_name', '?')[:15]} ({elapsed:.1f}s)")
        else:
            company_id, doc_id = db.get_company_doc(pdf_name)
            if company_id:
                save_page_data(db, company_id, doc_id, page_num, data)
                log(f"SAVED {pdf_name[:20]}... p{page_num} ({elapsed:.1f}s)")
            else:
                # Page 1 not processed yet, queue this
                if pdf_name not in pending_pages:
                    pending_pages[pdf_name] = []
                pending_pages[pdf_name].append({"page": page_num, "data": data})
                log(f"QUEUE {pdf_name[:20]}... p{page_num} ({elapsed:.1f}s)")
        
        return {"pdf": pdf_name, "page": page_num, "success": True, "time": elapsed}
    except Exception as e:
        log(f"FAIL {pdf_name[:20]}... p{page_num}: {str(e)[:30]}")
        return {"pdf": pdf_name, "page": page_num, "success": False, "error": str(e)}


def save_page_data(db: Database, company_id: int, doc_id: int, page_num: int, data: dict):
    """Save non-page-1 data to DB."""
    if page_num == 2:
        db.save_time_series(company_id, doc_id, "quarterly_pnl", data.get("quarterly_pnl"))
        db.save_time_series(company_id, doc_id, "segment_revenue", data.get("segment_revenue"))
    elif page_num == 3:
        db.save_time_series(company_id, doc_id, "annual_pnl", data.get("annual_pnl"))
        db.save_time_series(company_id, doc_id, "balance_sheet", data.get("balance_sheet"))
        db.save_time_series(company_id, doc_id, "cash_flow", data.get("cash_flow"))
        db.save_time_series(company_id, doc_id, "ratios", data.get("ratios"))
    elif page_num == 4:
        for h in data.get("rating_history") or []:
            db.save_qualitative(company_id, doc_id, json.dumps(h), "rating_history", 4)


def ingest_pdfs(pdf_dir: str = "data/pdfs", db_path: str = "data/database/financial_data.db", clear: bool = False, max_workers: int = 80):
    """
    Ingest all PDFs in parallel with immediate DB flushing.
    """
    if clear:
        Path(db_path).unlink(missing_ok=True)
    
    pdf_path = Path(pdf_dir)
    pdfs = sorted(pdf_path.glob("*.pdf"))
    
    if not pdfs:
        return {"error": "No PDFs found", "stats": {}}
    
    log(f"Found {len(pdfs)} PDFs")
    
    db = Database(db_path)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=90)
    
    # Extract text from all PDFs (fast, local)
    log("Extracting text from PDFs...")
    pdf_pages = {}
    for pdf in pdfs:
        pdf_pages[pdf.name] = extract_pdf_pages(pdf)
    
    # Build tasks
    tasks = []
    for pdf_name, pages in pdf_pages.items():
        for page in pages:
            tasks.append({
                "pdf": pdf_name,
                "page_num": page["page_num"],
                "text": page["text"],
                "table_text": page["table_text"]
            })
    
    log(f"Processing {len(tasks)} pages with {max_workers} workers (flush on complete)...")
    
    start = time.time()
    pending_pages = {}  # For pages that complete before their page 1
    completed = 0
    failed = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_and_save_page, client, db, t["pdf"], t["page_num"], t["text"], t["table_text"], pending_pages): t
            for t in tasks
        }
        for future in as_completed(futures):
            result = future.result()
            if result["success"]:
                completed += 1
            else:
                failed += 1
            
            # Progress update every 10 pages
            if (completed + failed) % 10 == 0:
                stats = db.get_stats()
                log(f"Progress: {completed + failed}/{len(tasks)} | DB: {stats['companies']} companies, {stats['metrics']} metrics")
    
    elapsed = time.time() - start
    stats = db.get_stats()
    
    log(f"COMPLETE in {elapsed:.1f}s | {completed} ok, {failed} failed")
    return {"time": elapsed, "stats": stats, "pdfs": len(pdfs), "pages": len(tasks), "completed": completed, "failed": failed}


def main():
    print("=" * 60)
    print("PDF Ingestion Pipeline (Parallel + Immediate Flush)")
    print("=" * 60)
    
    result = ingest_pdfs(
        clear='--clear' in sys.argv,
        max_workers=80
    )
    
    print()
    print("=" * 60)
    print(f"Completed in {result.get('time', 0):.1f}s")
    print(f"Pages: {result.get('completed', 0)} ok, {result.get('failed', 0)} failed")
    stats = result.get('stats', {})
    print(f"Companies: {stats.get('companies', 0)}")
    print(f"Metrics: {stats.get('metrics', 0)}")
    print(f"Time Series: {stats.get('time_series', 0)}")
    print(f"Qualitative: {stats.get('qualitative', 0)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
