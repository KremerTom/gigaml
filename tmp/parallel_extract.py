#!/usr/bin/env python3
"""Parallel extraction of all pages from all PDFs."""
import time
import base64
import json
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
import os
import sqlite3

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=180)
MODEL = "gpt-5"

# Flexible schema for any page
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
    page_type: str  # 'overview', 'quarterly', 'financials', 'valuation', 'other'
    metrics: List[MetricValue]
    qualitative: List[QualitativeChunk]

PROMPT = """Extract ALL structured data from this Geojit equity research report page.

INSTRUCTIONS:
- Extract EVERY numeric value you see (financial metrics, ratios, percentages, prices)
- For each metric: field_name (snake_case), value (number only), unit (if any), time_period (FY24, Q4FY24, etc.)
- Extract ALL qualitative text sections (business highlights, analysis, commentary, risks, outlook)
- Skip charts/graphs but extract any surrounding text
- Negative numbers in parentheses like (3.2) = -3.2
- Drop currency symbols and 'cr' units from values

METRIC EXAMPLES:
- revenue_fy24, ebitda_margin_q4fy24, promoter_holding_q4fy24, pe_ratio_fy25e, target_price, cmp
- Be specific with time periods in field names

Return company_name, page_type, all metrics, and all qualitative sections."""

def encode_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

def extract_page(image_path: Path) -> dict:
    """Extract data from a single page."""
    start = time.time()
    name = image_path.name
    print(f"[START] {name}", flush=True)
    
    try:
        image_base64 = encode_image(image_path)
        response = client.beta.chat.completions.parse(
            model=MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
                ]
            }],
            response_format=PageExtraction
        )
        result = response.choices[0].message.parsed
        elapsed = time.time() - start
        print(f"[DONE]  {name} - {len(result.metrics)} metrics, {len(result.qualitative)} chunks ({elapsed:.1f}s)", flush=True)
        return {
            "image": name,
            "success": True,
            "data": result.model_dump(),
            "elapsed": elapsed
        }
    except Exception as e:
        elapsed = time.time() - start
        print(f"[ERROR] {name} - {str(e)[:50]} ({elapsed:.1f}s)", flush=True)
        return {
            "image": name,
            "success": False,
            "error": str(e),
            "elapsed": elapsed
        }

def main():
    image_dir = Path("data/images")
    images = sorted(image_dir.glob("*.png"))
    
    # Skip page 4 if it's disclaimer (check later)
    print(f"Found {len(images)} images to process")
    print(f"Starting parallel extraction with {len(images)} workers...")
    print("=" * 60, flush=True)
    
    start_total = time.time()
    results = []
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(extract_page, img): img for img in images}
        for future in as_completed(futures):
            results.append(future.result())
    
    total_time = time.time() - start_total
    
    # Summary
    print("=" * 60)
    success = sum(1 for r in results if r["success"])
    total_metrics = sum(len(r["data"]["metrics"]) for r in results if r["success"])
    total_chunks = sum(len(r["data"]["qualitative"]) for r in results if r["success"])
    
    print(f"Completed: {success}/{len(results)} pages")
    print(f"Total metrics: {total_metrics}")
    print(f"Total qualitative chunks: {total_chunks}")
    print(f"Total time: {total_time:.1f}s (avg {total_time/len(images):.1f}s/page parallel)")
    
    # Save results
    output_path = Path("tmp/extraction_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_path}")

if __name__ == "__main__":
    main()
