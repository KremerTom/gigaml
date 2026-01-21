"""Data extraction from PDF images using GPT-5 vision."""

import base64
from pathlib import Path
from openai import OpenAI
from src.utils.config import config
from src.ingestion.schemas import Page1Metadata


class DataExtractor:
    """Extract structured data from PDF images."""

    def __init__(self, timeout: int = 60):
        self.client = OpenAI(api_key=config.openai_api_key, timeout=timeout)
        self.model = config.gpt5_model

    def extract_page1_metadata(self, image_path: Path) -> Page1Metadata:
        """Extract metadata from Page 1."""
        image_base64 = self._encode_image(image_path)
        prompt = """Extract ALL structured data from this Geojit equity research report page 1.

QUANTITATIVE DATA:
- Company info: name, sector, BSE/NSE/Bloomberg codes, report date, rating
- Market data: CMP, target price, market cap, EV, shares, free float, dividend yield, 52w high/low, beta, face value
- Shareholding pattern: all quarters shown (promoter %, FII %, MF/institutional %, public %, others %, pledge %)
- Consolidated forecasts table: all rows (Sales, Growth, EBITDA, margins, PAT, EPS, P/E, P/B, EV/EBITDA, ROE, D/E) for FY24A, FY25E, FY26E

QUALITATIVE DATA (extract full text for each section):
- Business highlights (main headline section with bullet points)
- Margin analysis (EBITDA margin section)
- Key highlights (key concall and other highlights)
- Valuation commentary

For percentages return just numbers. For crores drop units. Negative growth in parentheses like (3.2) is -3.2."""

        response = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
                ]
            }],
            response_format=Page1Metadata
        )
        return response.choices[0].message.parsed

    def _encode_image(self, image_path: Path) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')


def extract_page1_metadata(image_path: Path) -> Page1Metadata:
    return DataExtractor().extract_page1_metadata(image_path)
