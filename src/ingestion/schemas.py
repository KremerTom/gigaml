"""
Pydantic schemas for structured data extraction from equity research PDFs.
"""

from typing import Optional, List, Dict
from pydantic import BaseModel, Field


# ==================== Page 1: Metadata & Overview ====================

class ShareholdingQuarter(BaseModel):
    """Shareholding pattern for one quarter."""
    quarter: str = Field(description="Quarter identifier (e.g., 'Q4FY24')")
    promoter_pct: Optional[float] = Field(None, description="Promoter shareholding percentage")
    fii_pct: Optional[float] = Field(None, description="FII shareholding percentage")
    mf_institutional_pct: Optional[float] = Field(None, description="Mutual Fund/Institutional shareholding percentage")
    public_pct: Optional[float] = Field(None, description="Public shareholding percentage")
    others_pct: Optional[float] = Field(None, description="Others shareholding percentage")
    promoter_pledge_pct: Optional[float] = Field(None, description="Promoter pledge percentage")


class ForecastRow(BaseModel):
    """One row of financial forecasts."""
    metric: str = Field(description="Metric name (e.g., 'Sales', 'EBITDA')")
    fy24a: Optional[float] = Field(None, description="FY24 Actual value")
    fy25e: Optional[float] = Field(None, description="FY25 Estimate value")
    fy26e: Optional[float] = Field(None, description="FY26 Estimate value")
    unit: Optional[str] = Field(None, description="Unit (e.g., 'cr', 'percentage', 'ratio')")


class QualitativeChunk(BaseModel):
    """A qualitative text section from the report."""
    type: str = Field(description="Section type: 'business_highlights', 'margin_analysis', 'key_highlights', 'valuation', 'other'")
    content: str = Field(description="Full text content of the section")


class Page1Metadata(BaseModel):
    """Page 1 metadata and forecasts."""
    # Company Info
    company_name: str = Field(description="Company name")
    sector: str = Field(description="Sector/industry")
    bse_code: Optional[str] = Field(None, description="BSE stock code")
    nse_code: Optional[str] = Field(None, description="NSE stock code")
    bloomberg_code: Optional[str] = Field(None, description="Bloomberg ticker")

    # Report Info
    report_date: str = Field(description="Report date")
    report_type: str = Field(description="Report type (e.g., 'Q4FY24 RESULT UPDATE')")

    # Investment Rating
    rating: str = Field(description="Investment rating (BUY/HOLD/SELL)")
    cmp: float = Field(description="Current Market Price")
    target_price: float = Field(description="Target price")
    expected_return_pct: float = Field(description="Expected return percentage")

    # Market Data
    market_cap_cr: Optional[float] = Field(None, description="Market cap in crores")
    enterprise_value_cr: Optional[float] = Field(None, description="Enterprise value in crores")
    outstanding_shares_cr: Optional[float] = Field(None, description="Outstanding shares in crores")
    free_float_pct: Optional[float] = Field(None, description="Free float percentage")
    dividend_yield_pct: Optional[float] = Field(None, description="Dividend yield percentage")
    week_52_high: Optional[float] = Field(None, description="52-week high")
    week_52_low: Optional[float] = Field(None, description="52-week low")
    beta: Optional[float] = Field(None, description="Beta")
    face_value: Optional[float] = Field(None, description="Face value per share")

    # Shareholding Pattern
    shareholding: List[ShareholdingQuarter] = Field(default_factory=list, description="Shareholding pattern across quarters")

    # Financial Forecasts
    forecasts: List[ForecastRow] = Field(default_factory=list, description="Financial forecast table")

    # Qualitative Text Sections
    qualitative_sections: List[QualitativeChunk] = Field(default_factory=list, description="Qualitative text sections (business highlights, valuation, etc.)")


# ==================== Page 2: Quarterly Financials ====================

class QuarterlyPL(BaseModel):
    """Quarterly Profit & Loss statement."""
    # Metric names as keys, quarters as nested dict
    revenue_q4fy24: Optional[float] = None
    revenue_q4fy23: Optional[float] = None
    revenue_q3fy24: Optional[float] = None
    revenue_fy24: Optional[float] = None
    revenue_fy23: Optional[float] = None

    ebitda_q4fy24: Optional[float] = None
    ebitda_q4fy23: Optional[float] = None
    ebitda_q3fy24: Optional[float] = None
    ebitda_fy24: Optional[float] = None
    ebitda_fy23: Optional[float] = None

    ebitda_margin_q4fy24: Optional[float] = None
    ebitda_margin_q4fy23: Optional[float] = None
    ebitda_margin_q3fy24: Optional[float] = None
    ebitda_margin_fy24: Optional[float] = None
    ebitda_margin_fy23: Optional[float] = None

    pat_q4fy24: Optional[float] = None
    pat_q4fy23: Optional[float] = None
    pat_q3fy24: Optional[float] = None
    pat_fy24: Optional[float] = None
    pat_fy23: Optional[float] = None

    eps_q4fy24: Optional[float] = None
    eps_q4fy23: Optional[float] = None
    eps_q3fy24: Optional[float] = None
    eps_fy24: Optional[float] = None
    eps_fy23: Optional[float] = None

    # Add more fields as needed...
    # For now keeping it flexible


# ==================== Generic Metric Storage ====================

class MetricValue(BaseModel):
    """A single metric value with context."""
    field_name: str = Field(description="Field/metric name (e.g., 'revenue', 'ebitda_margin')")
    value: float = Field(description="Numeric value")
    unit: Optional[str] = Field(None, description="Unit (e.g., 'INR_crore', 'percentage', 'ratio')")
    time_period: Optional[str] = Field(None, description="Time period (e.g., 'Q4FY24', 'FY24')")
    is_forecast: bool = Field(default=False, description="Whether this is a forecast/estimate")


class ExtractionResult(BaseModel):
    """Combined extraction result for a PDF."""
    pdf_filename: str
    company_name: str
    page1_metadata: Optional[Page1Metadata] = None
    metrics: List[MetricValue] = Field(default_factory=list, description="All extracted metrics")
    qualitative_chunks: List[Dict] = Field(default_factory=list, description="Qualitative text chunks")
