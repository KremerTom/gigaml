"""
PDF to Image Conversion Module

Converts PDF files to high-resolution images for vision model processing.
"""

import hashlib
from pathlib import Path
from typing import List, Optional

from PIL import Image
import fitz  # PyMuPDF

from src.utils.config import config


class PDFProcessor:
    """Handles PDF to image conversion with caching."""

    def __init__(self):
        """Initialize PDF processor."""
        self.image_dir = config.images_dir
        self.dpi = config.pdf_dpi
        self.image_format = config.image_format

        # Ensure image directory exists
        self.image_dir.mkdir(parents=True, exist_ok=True)

    def convert_pdf_to_images(
        self,
        pdf_path: Path,
        use_cache: bool = True
    ) -> List[Path]:
        """
        Convert PDF to high-resolution images.

        Args:
            pdf_path: Path to PDF file
            use_cache: If True, use cached images if they exist

        Returns:
            List of paths to generated images (one per page)
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # Generate unique identifier for this PDF
        pdf_hash = self._compute_file_hash(pdf_path)

        # Check if images already exist in cache
        if use_cache:
            cached_images = self._get_cached_images(pdf_hash)
            if cached_images:
                print(f"Using cached images for {pdf_path.name}")
                return cached_images

        # Convert PDF to images using PyMuPDF
        print(f"Converting {pdf_path.name} to images (DPI={self.dpi})...")
        try:
            pdf_document = fitz.open(str(pdf_path))
            image_paths = []

            # Calculate zoom factor for desired DPI (default 72 DPI)
            zoom = self.dpi / 72
            mat = fitz.Matrix(zoom, zoom)

            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                pix = page.get_pixmap(matrix=mat)

                # Save image
                image_filename = f"{pdf_hash}_page_{page_num + 1}.{self.image_format.lower()}"
                image_path = self.image_dir / image_filename
                pix.save(str(image_path))
                image_paths.append(image_path)
                print(f"  Saved page {page_num + 1}/{len(pdf_document)}: {image_path.name}")

            pdf_document.close()
            return image_paths

        except Exception as e:
            raise RuntimeError(f"Failed to convert PDF {pdf_path}: {e}")

    def _compute_file_hash(self, file_path: Path) -> str:
        """
        Compute SHA256 hash of file for caching.

        Args:
            file_path: Path to file

        Returns:
            First 16 characters of SHA256 hash
        """
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            # Read in chunks to handle large files
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)
        return sha256.hexdigest()[:16]

    def _get_cached_images(self, pdf_hash: str) -> Optional[List[Path]]:
        """
        Check if cached images exist for this PDF.

        Args:
            pdf_hash: Hash identifier for the PDF

        Returns:
            List of cached image paths, or None if not found
        """
        # Look for images with this hash
        pattern = f"{pdf_hash}_page_*.{self.image_format.lower()}"
        cached_images = sorted(self.image_dir.glob(pattern))

        if cached_images:
            return cached_images
        return None

    def clear_cache(self, pdf_hash: Optional[str] = None):
        """
        Clear cached images.

        Args:
            pdf_hash: If provided, clear only images for this PDF.
                     If None, clear all cached images.
        """
        if pdf_hash:
            pattern = f"{pdf_hash}_page_*.{self.image_format.lower()}"
            for image_path in self.image_dir.glob(pattern):
                image_path.unlink()
                print(f"Deleted: {image_path.name}")
        else:
            # Clear all images
            for image_path in self.image_dir.glob(f"*.{self.image_format.lower()}"):
                image_path.unlink()
            print(f"Cleared all images from {self.image_dir}")


# Convenience function
def convert_pdf_to_images(pdf_path: Path, use_cache: bool = True) -> List[Path]:
    """
    Convert a PDF to images.

    Args:
        pdf_path: Path to PDF file
        use_cache: If True, use cached images if available

    Returns:
        List of paths to generated images
    """
    processor = PDFProcessor()
    return processor.convert_pdf_to_images(pdf_path, use_cache=use_cache)
