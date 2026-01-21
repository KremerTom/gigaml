#!/usr/bin/env python3
"""Debug single API call with full extraction."""
import time
import base64
from pathlib import Path
from openai import OpenAI
from pydantic import BaseModel
from typing import Optional, List
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=180)

class MetricValue(BaseModel):
    field_name: str
    value: float
    unit: Optional[str] = None
    time_period: Optional[str] = None

class QualitativeChunk(BaseModel):
    section_type: str
    content: str

class PageExtraction(BaseModel):
    company_name: str
    page_type: str
    metrics: List[MetricValue]
    qualitative: List[QualitativeChunk]

image_path = Path("data/images/32585599286500cb_page_1.png")
print(f"Testing: {image_path.name}")

with open(image_path, "rb") as f:
    image_base64 = base64.b64encode(f.read()).decode('utf-8')

prompt = """Extract ALL data from this equity research report page.
- metrics: field_name (snake_case with time period), value (number), unit, time_period
- qualitative: section_type, content (full text)
Skip charts. Negative (3.2) = -3.2."""

print("Calling API...")
start = time.time()

try:
    response = client.beta.chat.completions.parse(
        model="gpt-5",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
            ]
        }],
        response_format=PageExtraction
    )
    elapsed = time.time() - start
    result = response.choices[0].message.parsed
    print(f"SUCCESS in {elapsed:.1f}s")
    print(f"Metrics: {len(result.metrics)}")
    print(f"Qualitative: {len(result.qualitative)}")
    print("\nFirst 5 metrics:")
    for m in result.metrics[:5]:
        print(f"  {m.field_name}: {m.value} {m.unit or ''} ({m.time_period or 'n/a'})")
    print("\nQualitative sections:")
    for q in result.qualitative:
        print(f"  {q.section_type}: {len(q.content)} chars")
except Exception as e:
    elapsed = time.time() - start
    print(f"FAILED after {elapsed:.1f}s: {e}")
