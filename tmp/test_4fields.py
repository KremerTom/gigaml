#!/usr/bin/env python3
"""4 fields, 6 seconds - end to end."""
import time, base64, json, sqlite3
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=30)

image_path = Path("data/images/32585599286500cb_page_1.png")
with open(image_path, "rb") as f:
    image_base64 = base64.b64encode(f.read()).decode('utf-8')

print("1. Calling API...")
start = time.time()
response = client.chat.completions.create(
    model="gpt-5",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Extract: company_name, sector, cmp (current price), target_price. Return JSON only: {\"company_name\":\"...\",\"sector\":\"...\",\"cmp\":123,\"target_price\":456}"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
        ]
    }],
    response_format={"type": "json_object"}
)
print(f"   API: {time.time()-start:.1f}s")

data = json.loads(response.choices[0].message.content)
print(f"   Got: {data}")

print("2. Storing to DB...")
db = sqlite3.connect("data/database/test.db")
db.execute("CREATE TABLE IF NOT EXISTS test_extract (company TEXT, sector TEXT, cmp REAL, target REAL)")
db.execute("INSERT INTO test_extract VALUES (?,?,?,?)", 
           (data['company_name'], data['sector'], data['cmp'], data['target_price']))
db.commit()

print("3. Verifying...")
row = db.execute("SELECT * FROM test_extract").fetchone()
print(f"   Stored: {row}")
db.close()
print("DONE")
