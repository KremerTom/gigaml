#!/usr/bin/env python3
"""PDF Ingestion Pipeline - Full end-to-end: PDF → PNG → Chunked Extraction → DB."""

from pathlib import Path
import sys
import json
import base64
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from dotenv import load_dotenv
import os
import sqlite3
import threading

load_dotenv()

# Smart chunks by page type - consistent units (cr = crores, pct = percentage)
CHUNKS = {
    "page1": {
        "basic": "Extract: company_name, sector, bse_code, nse_code, bloomberg_code, report_date, report_type, rating. Return JSON.",
        "market": """Extract market data. Monetary values in crores (cr), percentages as numbers (65.0 not 0.65).
Return JSON: {"cmp": 684, "target_price": 791, "currency": "INR", "market_cap_cr": 154805, "enterprise_value_cr": 193373, "outstanding_shares_cr": 222.6, "free_float_pct": 65.0, "dividend_yield_pct": 0.4, "week_52_high": 715, "week_52_low": 407, "beta": 0.9, "face_value": 1}""",
        "shareholding": """Extract shareholding table. Return JSON: {"quarters": [{"quarter": "Q4FY24", "promoter_pct": 34.6, "fii_pct": 30.5, "mf_pct": 25.8, "public_pct": 5.9, "others_pct": 3.2},...]}""",
        "forecasts": """Extract consolidated forecasts table. Values in crores except ratios/percentages.
Return JSON: {"forecasts": [{"metric": "Sales", "fy24a": 215962, "fy25e": 230421, "fy26e": 246319, "unit": "cr"}, {"metric": "EBITDA_Margin", "fy24a": 11.9, "fy25e": 12.8, "fy26e": 13.1, "unit": "pct"},...]}""",
        "qualitative": """Extract all qualitative text (business highlights, analysis, key points).
Return JSON: {"sections": [{"type": "business_highlights", "content": "full text..."}, {"type": "analysis", "content": "..."}]}""",
    },
    "page2": {
        "quarterly_pnl": """Extract quarterly P&L table. All values in crores (cr).
Return JSON: {"periods": ["Q4FY24", "Q4FY23", "Q3FY24", "FY24", "FY23"], "rows": [{"metric": "Revenue", "values": [55994, 55857, 52808, 215962, 223202]}, {"metric": "EBITDA", "values": [7201, 5818, 6322, 25728, 24131]},...]}""",
        "segment_revenue": """Extract segment revenue breakdown if present. Values in crores.
Return JSON: {"segments": [{"name": "Aluminium", "q4fy24": 3762, "fy24": 14949}, {"name": "Copper", "q4fy24": 20919, "fy24": 71953},...]} or {} if no segments.""",
        "sotp_valuation": """Extract Sum of Parts (SOTP) valuation table.
Return JSON: {"components": [{"name": "Aluminium", "basis": "EV/EBITDA", "multiple": 5.8, "year": "FY26E", "value_cr": 70581, "value_per_share": 317},...], "target_price": 791}""",
        "estimate_changes": """Extract Change in Estimates table comparing old vs new.
Return JSON: {"changes": [{"metric": "Revenue", "fy25e_old": 218974, "fy25e_new": 230421, "fy25e_change_pct": 5.2, "fy26e_old": 226722, "fy26e_new": 246319, "fy26e_change_pct": 8.6},...]}""",
    },
    "page3": {
        "annual_pnl": """Extract annual P&L statement (FY22A through FY26E). Values in crores.
Return JSON: {"periods": ["FY22A", "FY23A", "FY24A", "FY25E", "FY26E"], "rows": [{"metric": "Revenue", "values": [195059, 223202, 215962, 230421, 246319]}, {"metric": "EBITDA", "values": [29793, 24142, 25753, 29535, 32153]},...]}""",
        "balance_sheet": """Extract balance sheet (FY22A through FY26E). Values in crores.
Return JSON: {"periods": ["FY22A", "FY23A", "FY24A", "FY25E", "FY26E"], "assets": [{"item": "Cash", "values": [17392, 15368, 14437, 16405, 18735]}, {"item": "Total_Assets", "values": [223062, 224817, 231907, 253685, 275730]},...], "liabilities": [{"item": "Debt_Funds", "values": [65089, 60554, 56712, 54962, 53212]},...]}""",
        "cash_flow": """Extract cash flow statement (FY22A through FY26E). Values in crores.
Return JSON: {"periods": ["FY22A", "FY23A", "FY24A", "FY25E", "FY26E"], "rows": [{"metric": "Net_Inc_Depn", "values": [20930, 17183, 17676, 21104, 23391]}, {"metric": "CF_Operation", "values": [16838, 19208, 24056, 27733, 28983]},...]}""",
        "ratios": """Extract financial ratios (FY22A through FY26E).
Return JSON: {"periods": ["FY22A", "FY23A", "FY24A", "FY25E", "FY26E"], "profitability": [{"ratio": "EBITDA_Margin_pct", "values": [15.3, 10.8, 11.9, 12.8, 13.1]}, {"ratio": "ROE_pct", "values": [17.6, 10.7, 9.6, 10.9, 10.9]},...], "valuation": [{"ratio": "PE", "values": [9.3, 9.0, 12.3, 12.0, 10.8]}, {"ratio": "PB", "values": [1.6, 1.0, 1.2, 1.3, 1.2]},...]}""",
    },
    "page4": {
        "rating_history": """Extract rating history table (dates, ratings, target prices).
Return JSON: {"history": [{"date": "24-Jun-24", "rating": "BUY", "target_price": 791}, {"date": "7-Mar-24", "rating": "HOLD", "target_price": 571},...]}""",
    },
}

# Thread-safe print
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
    
    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS companies (id INTEGER PRIMARY KEY, name TEXT UNIQUE, sector TEXT, bse_code TEXT, nse_code TEXT, bloomberg_code TEXT);
            CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, filename TEXT UNIQUE, company_id INTEGER, report_date TEXT, report_type TEXT, rating TEXT);
            CREATE TABLE IF NOT EXISTS metrics (id INTEGER PRIMARY KEY, company_id INTEGER, document_id INTEGER, field_name TEXT, value REAL, unit TEXT, time_period TEXT);
            CREATE TABLE IF NOT EXISTS time_series (id INTEGER PRIMARY KEY, company_id INTEGER, document_id INTEGER, table_name TEXT, metric TEXT, period TEXT, value REAL, unit TEXT);
            CREATE TABLE IF NOT EXISTS qualitative (id INTEGER PRIMARY KEY, company_id INTEGER, document_id INTEGER, chunk_type TEXT, content TEXT, page_num INTEGER);
            CREATE INDEX IF NOT EXISTS idx_metrics_company ON metrics(company_id);
            CREATE INDEX IF NOT EXISTS idx_metrics_field ON metrics(field_name);
            CREATE INDEX IF NOT EXISTS idx_ts_company ON time_series(company_id);
            CREATE INDEX IF NOT EXISTS idx_ts_table ON time_series(table_name);
        """)
        self.conn.commit()
    
    def flush_basic(self, filename: str, data: dict) -> tuple:
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("INSERT INTO companies (name, sector, bse_code, nse_code, bloomberg_code) VALUES (?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET sector=excluded.sector RETURNING id",
                       (data.get("company_name"), data.get("sector"), data.get("bse_code"), data.get("nse_code"), data.get("bloomberg_code")))
            company_id = cur.fetchone()[0]
            cur.execute("INSERT OR REPLACE INTO documents (filename, company_id, report_date, report_type, rating) VALUES (?,?,?,?,?)",
                       (filename, company_id, data.get("report_date"), data.get("report_type"), data.get("rating")))
            doc_id = cur.lastrowid
            self.conn.commit()
            return company_id, doc_id
    
    def flush_market(self, company_id: int, doc_id: int, data: dict):
        with self.lock:
            cur = self.conn.cursor()
            for field in ["cmp", "target_price", "market_cap_cr", "enterprise_value_cr", "outstanding_shares_cr", "week_52_high", "week_52_low", "beta", "face_value"]:
                val = data.get(field)
                if val is not None:
                    unit = "cr" if "_cr" in field else ("INR" if field in ["cmp", "target_price", "week_52_high", "week_52_low", "face_value"] else "")
                    cur.execute("INSERT INTO metrics (company_id, document_id, field_name, value, unit) VALUES (?,?,?,?,?)",
                               (company_id, doc_id, field, val, unit))
            for field in ["free_float_pct", "dividend_yield_pct"]:
                val = data.get(field)
                if val is not None:
                    cur.execute("INSERT INTO metrics (company_id, document_id, field_name, value, unit) VALUES (?,?,?,?,?)",
                               (company_id, doc_id, field, val, "pct"))
            self.conn.commit()
    
    def flush_shareholding(self, company_id: int, doc_id: int, data: dict):
        with self.lock:
            cur = self.conn.cursor()
            for q in data.get("quarters", []):
                qtr = q.get("quarter", "unknown")
                for field in ["promoter_pct", "fii_pct", "mf_pct", "public_pct", "others_pct"]:
                    val = q.get(field)
                    if val is not None:
                        cur.execute("INSERT INTO metrics (company_id, document_id, field_name, value, unit, time_period) VALUES (?,?,?,?,?,?)",
                                   (company_id, doc_id, field, val, "pct", qtr))
            self.conn.commit()
    
    def flush_forecasts(self, company_id: int, doc_id: int, data: dict):
        with self.lock:
            cur = self.conn.cursor()
            for f in data.get("forecasts", []):
                metric = f.get("metric", "unknown").lower().replace(" ", "_").replace("(%)", "pct")
                unit = f.get("unit", "cr")
                for period in ["fy24a", "fy25e", "fy26e"]:
                    val = f.get(period)
                    if val is not None:
                        cur.execute("INSERT INTO metrics (company_id, document_id, field_name, value, unit, time_period) VALUES (?,?,?,?,?,?)",
                                   (company_id, doc_id, f"{metric}_{period}", val, unit, period.upper()))
            self.conn.commit()
    
    def flush_qualitative(self, company_id: int, doc_id: int, data: dict, page_num: int):
        with self.lock:
            cur = self.conn.cursor()
            for s in data.get("sections", []):
                cur.execute("INSERT INTO qualitative (company_id, document_id, chunk_type, content, page_num) VALUES (?,?,?,?,?)",
                           (company_id, doc_id, s.get("type", "other"), s.get("content", ""), page_num))
            self.conn.commit()
    
    def flush_time_series(self, company_id: int, doc_id: int, table_name: str, data: dict, unit: str = "cr"):
        """Flush tabular time-series data (P&L, Balance Sheet, Cash Flow, Ratios)."""
        with self.lock:
            cur = self.conn.cursor()
            periods = data.get("periods", [])
            for row in data.get("rows", []) + data.get("assets", []) + data.get("liabilities", []):
                metric = row.get("metric") or row.get("item") or row.get("ratio", "unknown")
                metric = metric.lower().replace(" ", "_").replace("(%)", "pct")
                values = row.get("values", [])
                for i, val in enumerate(values):
                    if val is not None and i < len(periods):
                        cur.execute("INSERT INTO time_series (company_id, document_id, table_name, metric, period, value, unit) VALUES (?,?,?,?,?,?,?)",
                                   (company_id, doc_id, table_name, metric, periods[i], val, unit))
            # Handle nested ratio categories
            for category in ["profitability", "valuation", "liquidity", "leverage"]:
                for row in data.get(category, []):
                    metric = row.get("ratio", "unknown").lower().replace(" ", "_")
                    values = row.get("values", [])
                    for i, val in enumerate(values):
                        if val is not None and i < len(periods):
                            cur.execute("INSERT INTO time_series (company_id, document_id, table_name, metric, period, value, unit) VALUES (?,?,?,?,?,?,?)",
                                       (company_id, doc_id, f"ratios_{category}", metric, periods[i], val, ""))
            self.conn.commit()
    
    def flush_sotp(self, company_id: int, doc_id: int, data: dict):
        with self.lock:
            cur = self.conn.cursor()
            for comp in data.get("components", []):
                name = comp.get("name", "unknown").lower().replace(" ", "_")
                for field in ["value_cr", "value_per_share", "multiple"]:
                    val = comp.get(field)
                    if val is not None:
                        cur.execute("INSERT INTO metrics (company_id, document_id, field_name, value, unit) VALUES (?,?,?,?,?)",
                                   (company_id, doc_id, f"sotp_{name}_{field}", val, "cr" if "cr" in field else ("x" if "multiple" in field else "INR")))
            self.conn.commit()
    
    def flush_rating_history(self, company_id: int, doc_id: int, data: dict):
        with self.lock:
            cur = self.conn.cursor()
            for h in data.get("history", []):
                cur.execute("INSERT INTO qualitative (company_id, document_id, chunk_type, content, page_num) VALUES (?,?,?,?,?)",
                           (company_id, doc_id, "rating_history", json.dumps(h), 4))
            self.conn.commit()
    
    def get_stats(self):
        return {
            "companies": self.conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0],
            "metrics": self.conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0],
            "time_series": self.conn.execute("SELECT COUNT(*) FROM time_series").fetchone()[0],
            "qualitative": self.conn.execute("SELECT COUNT(*) FROM qualitative").fetchone()[0],
        }


def convert_pdf_to_images(pdf_path: Path, output_dir: Path, dpi: int = 200) -> list:
    """Convert PDF to images, return list of image paths. Uses caching."""
    from pdf2image import convert_from_path
    
    pdf_hash = hashlib.md5(pdf_path.read_bytes()).hexdigest()[:16]
    existing = sorted(output_dir.glob(f"{pdf_hash}_page_*.png"))
    if existing:
        log(f"Cached: {pdf_path.name} ({len(existing)} pages)")
        return existing
    
    log(f"Converting: {pdf_path.name}...")
    images = convert_from_path(str(pdf_path), dpi=dpi)
    
    image_paths = []
    for i, img in enumerate(images, 1):
        img_path = output_dir / f"{pdf_hash}_page_{i}.png"
        img.save(str(img_path), "PNG")
        image_paths.append(img_path)
    
    log(f"Created {len(image_paths)} images for {pdf_path.name}")
    return image_paths


def extract_chunk(image_path: Path, chunk_name: str, prompt: str, delay: float = 0) -> dict:
    """Extract a single chunk with optional delay."""
    if delay > 0:
        time.sleep(delay)
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=120)
    
    with open(image_path, "rb") as f:
        img_base64 = base64.b64encode(f.read()).decode()
    
    start = time.time()
    img_name = image_path.stem[:8]
    log(f"START {img_name}/{chunk_name}")
    
    try:
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
            ]}],
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        elapsed = time.time() - start
        log(f"DONE  {img_name}/{chunk_name} ({elapsed:.1f}s)")
        return {"image": str(image_path), "chunk": chunk_name, "success": True, "data": data, "time": elapsed}
    except Exception as e:
        elapsed = time.time() - start
        log(f"FAIL  {img_name}/{chunk_name} ({elapsed:.1f}s): {str(e)[:40]}")
        return {"image": str(image_path), "chunk": chunk_name, "success": False, "error": str(e), "time": elapsed}


def flush_data(db, cid, did, chunk_name, data, page_num):
    """Flush extracted data based on chunk type."""
    if chunk_name == "market":
        db.flush_market(cid, did, data)
    elif chunk_name == "shareholding":
        db.flush_shareholding(cid, did, data)
    elif chunk_name == "forecasts":
        db.flush_forecasts(cid, did, data)
    elif chunk_name == "qualitative":
        db.flush_qualitative(cid, did, data, page_num)
    elif chunk_name in ["quarterly_pnl", "annual_pnl"]:
        db.flush_time_series(cid, did, chunk_name, data, "cr")
    elif chunk_name == "balance_sheet":
        db.flush_time_series(cid, did, "balance_sheet", data, "cr")
    elif chunk_name == "cash_flow":
        db.flush_time_series(cid, did, "cash_flow", data, "cr")
    elif chunk_name == "ratios":
        db.flush_time_series(cid, did, "ratios", data, "")
    elif chunk_name == "sotp_valuation":
        db.flush_sotp(cid, did, data)
    elif chunk_name == "rating_history":
        db.flush_rating_history(cid, did, data)
    log(f"FLUSH {chunk_name}")


def main():
    print("=" * 60)
    print("Full PDF Ingestion Pipeline")
    print("=" * 60)
    
    if '--clear' in sys.argv:
        Path("data/database/financial_data.db").unlink(missing_ok=True)
        if '--clear-images' in sys.argv:
            for img in Path("data/images").glob("*.png"):
                img.unlink()
            print("Cleared database and images")
        else:
            print("Cleared database")
    
    pdf_dir = Path("data/pdfs")
    image_dir = Path("data/images")
    image_dir.mkdir(parents=True, exist_ok=True)
    
    # Use existing images grouped by hash prefix
    existing_images = sorted(image_dir.glob("*_page_*.png"))
    if existing_images:
        print(f"Found {len(existing_images)} existing images")
        # Group by hash prefix
        image_groups = {}
        for img in existing_images:
            prefix = img.stem.split("_page_")[0]
            if prefix not in image_groups:
                image_groups[prefix] = []
            image_groups[prefix].append(img)
        # Sort each group by page number
        for prefix in image_groups:
            image_groups[prefix] = sorted(image_groups[prefix], key=lambda x: int(x.stem.split("_page_")[1]))
        print(f"Image groups: {len(image_groups)}")
    else:
        image_groups = {}
    
    # Try converting any PDFs without images
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    print(f"Found {len(pdfs)} PDFs")
    
    for pdf in pdfs:
        try:
            images = convert_pdf_to_images(pdf, image_dir)
            if images:
                prefix = images[0].stem.split("_page_")[0]
                image_groups[prefix] = images
        except Exception as e:
            pass  # Skip silently, we'll use existing images
    
    total_images = sum(len(imgs) for imgs in image_groups.values())
    print(f"Total images: {total_images}")
    
    if not image_groups:
        print("No images to process!")
        return
    
    # Build extraction tasks for all pages
    print("\n--- Building Extraction Tasks ---")
    tasks = []
    delay = 0
    stagger = 2  # seconds between task starts
    
    for prefix, images in image_groups.items():
        for page_num, image_path in enumerate(images, 1):
            page_key = f"page{page_num}" if page_num <= 4 else None
            if page_key and page_key in CHUNKS:
                for chunk_name, prompt in CHUNKS[page_key].items():
                    tasks.append({
                        "prefix": prefix,
                        "image": image_path,
                        "page": page_num,
                        "chunk": chunk_name,
                        "prompt": prompt,
                        "delay": delay
                    })
                    delay += stagger
    
    print(f"Tasks: {len(tasks)}")
    print(f"Stagger: {stagger}s between starts")
    print(f"Estimated time: {delay}s")
    
    if not tasks:
        print("No tasks to run!")
        return
    
    db = Database()
    
    # Track results per image group for flushing
    group_info = {prefix: {"filename": f"{prefix}.pdf", "company_id": None, "doc_id": None} for prefix in image_groups}
    
    print("\n--- Extracting Data ---")
    start_total = time.time()
    completed = 0
    failed = 0
    pending_flushes = []  # Store results that need basic first
    
    with ThreadPoolExecutor(max_workers=min(50, len(tasks))) as executor:
        futures = {
            executor.submit(extract_chunk, t["image"], t["chunk"], t["prompt"], t["delay"]): t
            for t in tasks
        }
        
        for future in as_completed(futures):
            task = futures[future]
            result = future.result()
            prefix = task["prefix"]
            chunk_name = result["chunk"]
            page_num = task["page"]
            info = group_info[prefix]
            
            if not result["success"]:
                failed += 1
                continue
            
            completed += 1
            data = result["data"]
            
            # Flush based on chunk type
            if chunk_name == "basic":
                company_id, doc_id = db.flush_basic(info["filename"], data)
                info["company_id"] = company_id
                info["doc_id"] = doc_id
                log(f"FLUSH basic → {data.get('company_name', 'unknown')[:20]}")
                # Process any pending flushes for this group
                for pf in pending_flushes[:]:
                    if pf["prefix"] == prefix:
                        flush_data(db, info["company_id"], info["doc_id"], pf["chunk"], pf["data"], pf["page"])
                        pending_flushes.remove(pf)
            elif not info["company_id"]:
                pending_flushes.append({"prefix": prefix, "chunk": chunk_name, "data": data, "page": page_num})
            else:
                flush_data(db, info["company_id"], info["doc_id"], chunk_name, data, page_num)
    
    total_time = time.time() - start_total
    stats = db.get_stats()
    
    print()
    print("=" * 60)
    print(f"COMPLETED in {total_time:.1f}s")
    print(f"Tasks: {completed} ok, {failed} failed")
    print(f"Companies: {stats['companies']}")
    print(f"Metrics: {stats['metrics']}")
    print(f"Time Series: {stats['time_series']}")
    print(f"Qualitative: {stats['qualitative']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
