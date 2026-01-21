#!/usr/bin/env python3
"""PDF Ingestion Pipeline - Process PDFs in parallel."""

from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.ingestion.pdf_processor import PDFProcessor
from src.ingestion.data_extractor import DataExtractor
from src.ingestion.storage import Database


def process_pdf(pdf_path, use_cache, db):
    """Process a single PDF."""
    pdf_processor = PDFProcessor()
    extractor = DataExtractor()

    result = {
        'pdf': pdf_path.name,
        'success': False,
        'error': None,
        'company': None,
        'doc_id': None
    }

    try:
        images = pdf_processor.convert_pdf_to_images(pdf_path, use_cache=use_cache)
        metadata = extractor.extract_page1_metadata(images[0])
        document_id = db.save_page1_metadata(pdf_path.name, metadata)

        # Save qualitative chunks if present
        if metadata.qualitative_sections:
            company = db.get_company_by_name(metadata.company_name)
            if company:
                chunks = [{'type': q.type, 'content': q.content} for q in metadata.qualitative_sections]
                db.save_qualitative_chunks(company['id'], document_id, chunks, page_number=1)

        result['success'] = True
        result['company'] = metadata.company_name
        result['doc_id'] = document_id
    except Exception as e:
        result['error'] = str(e)

    return result


def main():
    print("=" * 60)
    print("PDF Ingestion Pipeline")
    print("=" * 60)

    # Parse args
    limit = None
    use_cache = True
    workers = 3

    if '--limit' in sys.argv:
        idx = sys.argv.index('--limit')
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])

    if '--workers' in sys.argv:
        idx = sys.argv.index('--workers')
        if idx + 1 < len(sys.argv):
            workers = int(sys.argv[idx + 1])

    if '--clear' in sys.argv:
        use_cache = False
        print("Clearing cache...")

    print(f"Parallel workers: {workers}")

    # Initialize
    db = Database()
    pdf_dir = Path('data/pdfs')
    pdfs = sorted(pdf_dir.glob('*.pdf'))

    if limit:
        pdfs = pdfs[:limit]

    print(f"Found {len(pdfs)} PDFs to process\n")

    if not pdfs:
        print("No PDFs found in data/pdfs/")
        return

    # Process in parallel
    success_count = 0
    error_count = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_pdf, pdf, use_cache, db): pdf for pdf in pdfs}

        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            print(f"[{i}/{len(pdfs)}] {result['pdf']}")

            if result['success']:
                print(f"  SUCCESS: {result['company']} (Doc ID: {result['doc_id']})")
                success_count += 1
            else:
                print(f"  FAILED: {result['error']}")
                error_count += 1
            print()

    # Summary
    print("=" * 60)
    print(f"Successful: {success_count} | Failed: {error_count}")
    print("\nCompanies in database:")
    for company in db.get_companies():
        print(f"  - {company['name']} ({company['sector']})")

    db.close()
    print("\nDone!")


if __name__ == '__main__':
    main()
