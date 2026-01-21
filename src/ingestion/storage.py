"""SQLite database storage for extracted financial data."""

import sqlite3
from pathlib import Path
from typing import Optional
from src.utils.config import config
from src.ingestion.schemas import Page1Metadata


class Database:
    """Simple SQLite database manager."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config.database_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = None
        self._connect()
        self._create_tables()

    def _connect(self):
        """Connect to database."""
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def _create_tables(self):
        """Create tables if they don't exist."""
        cursor = self.conn.cursor()

        # Companies table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sector TEXT,
                bse_code TEXT,
                nse_code TEXT,
                bloomberg_code TEXT,
                UNIQUE(name)
            )
        """)

        # Documents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT UNIQUE NOT NULL,
                company_id INTEGER,
                report_date TEXT,
                report_type TEXT,
                processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_id) REFERENCES companies(id)
            )
        """)

        # Metrics table (pivot table for all financial metrics)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                document_id INTEGER NOT NULL,
                field_name TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT,
                time_period TEXT,
                is_forecast INTEGER DEFAULT 0,
                FOREIGN KEY (company_id) REFERENCES companies(id),
                FOREIGN KEY (document_id) REFERENCES documents(id)
            )
        """)

        # Qualitative chunks table (for vector embedding later)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS qualitative_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                document_id INTEGER NOT NULL,
                chunk_type TEXT NOT NULL,
                content TEXT NOT NULL,
                page_number INTEGER,
                FOREIGN KEY (company_id) REFERENCES companies(id),
                FOREIGN KEY (document_id) REFERENCES documents(id)
            )
        """)

        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_company ON metrics(company_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_field ON metrics(field_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_company ON qualitative_chunks(company_id)")

        self.conn.commit()

    def save_page1_metadata(self, pdf_filename: str, metadata: Page1Metadata) -> int:
        """Save Page 1 metadata to database. Returns document_id."""
        cursor = self.conn.cursor()

        # Insert or get company
        cursor.execute("""
            INSERT INTO companies (name, sector, bse_code, nse_code, bloomberg_code)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                sector=excluded.sector,
                bse_code=excluded.bse_code,
                nse_code=excluded.nse_code,
                bloomberg_code=excluded.bloomberg_code
            RETURNING id
        """, (metadata.company_name, metadata.sector, metadata.bse_code,
              metadata.nse_code, metadata.bloomberg_code))

        company_id = cursor.fetchone()[0]

        # Insert document
        cursor.execute("""
            INSERT OR REPLACE INTO documents (filename, company_id, report_date, report_type)
            VALUES (?, ?, ?, ?)
        """, (pdf_filename, company_id, metadata.report_date, metadata.report_type))

        document_id = cursor.lastrowid

        # Insert ALL market data metrics
        metrics_to_insert = [
            ('cmp', metadata.cmp, 'Rs', None, False),
            ('target_price', metadata.target_price, 'Rs', None, False),
            ('expected_return_pct', metadata.expected_return_pct, 'percentage', None, False),
            ('market_cap_cr', metadata.market_cap_cr, 'INR_crore', None, False),
            ('enterprise_value_cr', metadata.enterprise_value_cr, 'INR_crore', None, False),
            ('outstanding_shares_cr', metadata.outstanding_shares_cr, 'crore', None, False),
            ('free_float_pct', metadata.free_float_pct, 'percentage', None, False),
            ('dividend_yield_pct', metadata.dividend_yield_pct, 'percentage', None, False),
            ('week_52_high', metadata.week_52_high, 'Rs', None, False),
            ('week_52_low', metadata.week_52_low, 'Rs', None, False),
            ('beta', metadata.beta, None, None, False),
            ('face_value', metadata.face_value, 'Rs', None, False),
        ]

        # Insert shareholding metrics
        for sh in metadata.shareholding:
            quarter = sh.quarter.lower().replace(' ', '_')
            if sh.promoter_pct is not None:
                metrics_to_insert.append((f'promoter_pct_{quarter}', sh.promoter_pct, 'percentage', sh.quarter, False))
            if sh.fii_pct is not None:
                metrics_to_insert.append((f'fii_pct_{quarter}', sh.fii_pct, 'percentage', sh.quarter, False))
            if sh.mf_institutional_pct is not None:
                metrics_to_insert.append((f'mf_institutional_pct_{quarter}', sh.mf_institutional_pct, 'percentage', sh.quarter, False))
            if sh.public_pct is not None:
                metrics_to_insert.append((f'public_pct_{quarter}', sh.public_pct, 'percentage', sh.quarter, False))
            if sh.others_pct is not None:
                metrics_to_insert.append((f'others_pct_{quarter}', sh.others_pct, 'percentage', sh.quarter, False))
            if sh.promoter_pledge_pct is not None:
                metrics_to_insert.append((f'promoter_pledge_pct_{quarter}', sh.promoter_pledge_pct, 'percentage', sh.quarter, False))

        # Insert forecast metrics
        for forecast in metadata.forecasts:
            for period, value in [('FY24A', forecast.fy24a), ('FY25E', forecast.fy25e), ('FY26E', forecast.fy26e)]:
                if value is not None:
                    field_name = f"{forecast.metric.lower().replace(' ', '_')}_{period.lower()}"
                    is_forecast = 1 if period.endswith('E') else 0
                    metrics_to_insert.append((field_name, value, forecast.unit, period, is_forecast))

        # Filter out None values and batch insert
        metrics_to_insert = [m for m in metrics_to_insert if m[1] is not None]
        cursor.executemany("""
            INSERT INTO metrics (company_id, document_id, field_name, value, unit, time_period, is_forecast)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [(company_id, document_id, *m) for m in metrics_to_insert])

        self.conn.commit()
        return document_id

    def save_qualitative_chunks(self, company_id: int, document_id: int, chunks: list, page_number: int = 1):
        """Save qualitative text chunks for later vector embedding."""
        cursor = self.conn.cursor()
        cursor.executemany("""
            INSERT INTO qualitative_chunks (company_id, document_id, chunk_type, content, page_number)
            VALUES (?, ?, ?, ?, ?)
        """, [(company_id, document_id, c['type'], c['content'], page_number) for c in chunks])
        self.conn.commit()

    def get_companies(self):
        """Get all companies."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM companies")
        return cursor.fetchall()

    def get_company_by_name(self, name: str):
        """Get company by name."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM companies WHERE name = ?", (name,))
        return cursor.fetchone()

    def get_metrics(self, company_id: int):
        """Get all metrics for a company."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM metrics WHERE company_id = ?", (company_id,))
        return cursor.fetchall()

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
