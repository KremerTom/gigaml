#!/usr/bin/env python3
"""Compare text vs vision extraction speed."""
import time
import json
import pdfplumber
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=60)

PDF_PATH = "data/pdfs/Hindalco Industries_20240604.pdf"

def extract_text(pdf_path, page_num=0):
    """Extract text from a PDF page."""
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num]
        text = page.extract_text()
        tables = page.extract_tables()
    return text, tables

def text_based_extraction(text):
    """Extract structured data from text using GPT-5."""
    prompt = """Extract from this financial research document:
- company_name, sector, cmp (current price), target_price, market_cap_cr, rating

Return JSON: {"company_name": "...", "sector": "...", "cmp": 123, "target_price": 456, "market_cap_cr": 789, "rating": "BUY"}

Document text:
""" + text[:4000]  # Limit text length
    
    start = time.time()
    response = client.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    elapsed = time.time() - start
    data = json.loads(response.choices[0].message.content)
    return data, elapsed

def main():
    print("=" * 50)
    print("Text vs Vision Extraction Comparison")
    print("=" * 50)
    
    # Extract text
    print("\n1. Extracting text from PDF...")
    start = time.time()
    text, tables = extract_text(PDF_PATH, page_num=0)
    text_time = time.time() - start
    print(f"   Text extraction: {text_time:.2f}s")
    print(f"   Text length: {len(text)} chars")
    print(f"   Tables found: {len(tables)}")
    
    # Show sample of text
    print(f"\n   Sample text:\n   {text[:300]}...")
    
    # GPT extraction from text
    print("\n2. GPT-5 extraction from TEXT...")
    data, api_time = text_based_extraction(text)
    print(f"   API call: {api_time:.2f}s")
    print(f"   Total: {text_time + api_time:.2f}s")
    print(f"   Result: {json.dumps(data, indent=2)}")
    
    print("\n" + "=" * 50)
    print("COMPARISON (vs vision ~20-30s per call)")
    print(f"Text approach: {text_time + api_time:.2f}s")
    print("=" * 50)

if __name__ == "__main__":
    main()
