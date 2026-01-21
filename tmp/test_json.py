#!/usr/bin/env python3
"""Test with regular JSON output (not structured output)."""
import time, base64, json
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=60)

image_path = Path("data/images/32585599286500cb_page_1.png")
with open(image_path, "rb") as f:
    image_base64 = base64.b64encode(f.read()).decode('utf-8')

prompt = """Extract data from this equity research report. Return JSON:
{"company":"...","metrics":[{"field":"revenue_fy24","value":123,"unit":"cr"}],"text":["business overview text..."]}
Extract all numeric values with snake_case field names including time period. Include qualitative text sections."""

import sys
print("Calling API (regular JSON)...", flush=True)
sys.stdout.flush()
start = time.time()

response = client.chat.completions.create(
    model="gpt-5",
    messages=[{
        "role": "user", 
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
        ]
    }],
    response_format={"type": "json_object"}
)

elapsed = time.time() - start
print(f"Done in {elapsed:.1f}s")
data = json.loads(response.choices[0].message.content)
print(f"Company: {data.get('company')}")
print(f"Metrics: {len(data.get('metrics', []))}")
print(f"Text sections: {len(data.get('text', []))}")
