#!/usr/bin/env python3
"""Quick test to isolate API timing."""
import time
import base64
from pathlib import Path
from openai import OpenAI
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=120)
image_path = Path("data/images/32585599286500cb_page_1.png")

# Simple schema
class BasicInfo(BaseModel):
    company_name: str
    sector: str
    cmp: float
    target_price: float

print(f"Image size: {image_path.stat().st_size / 1024:.1f} KB")

with open(image_path, "rb") as f:
    image_base64 = base64.b64encode(f.read()).decode('utf-8')

# Test structured output
start = time.time()
print("Calling API (structured output)...")
response = client.beta.chat.completions.parse(
    model="gpt-5",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Extract basic info from this equity research report."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
        ]
    }],
    response_format=BasicInfo
)
print(f"API call: {time.time() - start:.2f}s")
print(f"Response: {response.choices[0].message.parsed}")
