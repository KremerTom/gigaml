#!/usr/bin/env python3
"""End-to-end: Extract 4 fields, store in real database."""
import time, base64, json
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
import os
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.storage import Database

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=120)

# 1. Extract
image_path = Path("data/images/32585599286500cb_page_1.png")
with open(image_path, "rb") as f:
    image_base64 = base64.b64encode(f.read()).decode('utf-8')

print("1. Extracting from image...")
start = time.time()
response = client.chat.completions.create(
    model="gpt-5",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Extract: company_name, sector, cmp, target_price, currency, and summary (the main text/analysis on the page). Return JSON: {\"company_name\":\"...\",\"sector\":\"...\",\"cmp\":123,\"target_price\":456,\"currency\":\"INR\",\"summary\":\"full text of business highlights and analysis...\"}"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
        ]
    }],
    response_format={"type": "json_object"}
)
data = json.loads(response.choices[0].message.content)
print(f"   Extracted in {time.time()-start:.1f}s")
print(f"   Metrics: company={data['company_name']}, cmp={data['cmp']}, target={data['target_price']}")
print(f"   Summary: {len(data.get('summary',''))} chars")

# 2. Store in real database
print("2. Storing in database...")
db = Database()

# Insert company
cursor = db.conn.cursor()
cursor.execute("""
    INSERT INTO companies (name, sector) VALUES (?, ?)
    ON CONFLICT(name) DO UPDATE SET sector=excluded.sector
    RETURNING id
""", (data['company_name'], data['sector']))
company_id = cursor.fetchone()[0]

# Insert document
cursor.execute("""
    INSERT OR REPLACE INTO documents (filename, company_id, report_date, report_type)
    VALUES (?, ?, ?, ?)
""", ("Hindalco_test.pdf", company_id, "2024-06-04", "Q4FY24"))
doc_id = cursor.lastrowid

# Insert metrics with currency
currency = data.get('currency', 'INR')
cursor.execute("""
    INSERT INTO metrics (company_id, document_id, field_name, value, unit, time_period, is_forecast)
    VALUES (?, ?, ?, ?, ?, ?, ?)
""", (company_id, doc_id, "cmp", data['cmp'], currency, None, 0))
cursor.execute("""
    INSERT INTO metrics (company_id, document_id, field_name, value, unit, time_period, is_forecast)
    VALUES (?, ?, ?, ?, ?, ?, ?)
""", (company_id, doc_id, "target_price", data['target_price'], currency, None, 0))

db.conn.commit()
print(f"   Company ID: {company_id}, Doc ID: {doc_id}")

# Insert qualitative chunk (summary)
if data.get('summary'):
    cursor.execute("""
        INSERT INTO qualitative_chunks (company_id, document_id, chunk_type, content, page_number)
        VALUES (?, ?, ?, ?, ?)
    """, (company_id, doc_id, "summary", data['summary'], 1))
    db.conn.commit()
    print(f"   Stored summary ({len(data['summary'])} chars)")

# 3. Verify
print("3. Verifying...")
companies = db.get_companies()
print(f"   Companies: {[c['name'] for c in companies]}")

metrics = db.get_metrics(company_id)
print(f"   Metrics: {[(m['field_name'], m['value'], m['unit']) for m in metrics]}")

chunks = cursor.execute("SELECT chunk_type, length(content) as len FROM qualitative_chunks WHERE company_id=?", (company_id,)).fetchall()
print(f"   Qualitative: {[(c[0], c[1]) for c in chunks]}")

db.close()
print("\nDONE - Data stored in data/database/financial_data.db")
