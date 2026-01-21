"""
Configuration management for the Financial Research AI Agent.
Handles all settings for ingestion pipeline and query workflow.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv


class Config:
    """Central configuration class for the entire application."""

    def __init__(self, env_file: Optional[str] = None):
        """
        Initialize configuration.

        Args:
            env_file: Path to .env file. If None, uses default .env in project root
        """
        # Load environment variables
        if env_file:
            load_dotenv(env_file)
        else:
            # Try to load from project root
            project_root = Path(__file__).parent.parent.parent
            env_path = project_root / ".env"
            if env_path.exists():
                load_dotenv(env_path)

        # Validate required environment variables
        self._validate_env()

    def _validate_env(self):
        """Validate that required environment variables are set."""
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError(
                "OPENAI_API_KEY not found in environment variables. "
                "Please create a .env file based on .env.template"
            )

    # ==================== Project Paths ====================

    @property
    def project_root(self) -> Path:
        """Root directory of the project."""
        return Path(__file__).parent.parent.parent

    @property
    def data_dir(self) -> Path:
        """Data directory."""
        return self.project_root / "data"

    @property
    def pdfs_dir(self) -> Path:
        """Directory containing input PDF files."""
        return self.data_dir / "pdfs"

    @property
    def images_dir(self) -> Path:
        """Directory for temporary PDF images."""
        return self.data_dir / "images"

    @property
    def database_dir(self) -> Path:
        """Directory for SQLite database."""
        return self.data_dir / "database"

    @property
    def database_path(self) -> Path:
        """Path to SQLite database file."""
        return self.database_dir / "financial_data.db"

    @property
    def schema_path(self) -> Path:
        """Path to schema JSON file."""
        return self.data_dir / "schema.json"

    @property
    def manifest_path(self) -> Path:
        """Path to manifest JSON file."""
        return self.data_dir / "manifest.json"

    @property
    def vector_store_config_path(self) -> Path:
        """Path to vector store configuration file."""
        return self.data_dir / "vector_store_config.json"

    @property
    def error_log_path(self) -> Path:
        """Path to error log file."""
        return self.data_dir / "errors.log"

    # ==================== OpenAI Configuration ====================

    @property
    def openai_api_key(self) -> str:
        """OpenAI API key from environment."""
        return os.getenv("OPENAI_API_KEY", "")

    @property
    def openai_org_id(self) -> Optional[str]:
        """Optional OpenAI organization ID."""
        return os.getenv("OPENAI_ORG_ID")

    @property
    def gpt5_model(self) -> str:
        """
        GPT-5 model name for all tasks (text and vision).
        GPT-5 is a multimodal model with native vision capabilities.
        """
        return os.getenv("GPT5_MODEL", "gpt-5")

    @property
    def gpt5_vision_model(self) -> str:
        """
        GPT-5 model for vision tasks (same as gpt5_model).
        Kept for backward compatibility - GPT-5 is multimodal.
        """
        return os.getenv("GPT5_VISION_MODEL", "gpt-5")

    @property
    def temperature(self) -> float:
        """Temperature for OpenAI completions (0 for deterministic)."""
        return float(os.getenv("OPENAI_TEMPERATURE", "0"))

    @property
    def max_tokens(self) -> Optional[int]:
        """Maximum tokens for completions. None = unlimited."""
        max_tokens_str = os.getenv("OPENAI_MAX_TOKENS")
        return int(max_tokens_str) if max_tokens_str else None

    @property
    def timeout(self) -> int:
        """API request timeout in seconds."""
        return int(os.getenv("OPENAI_TIMEOUT", "120"))

    @property
    def reasoning_effort(self) -> str:
        """
        Reasoning effort level for GPT-5.2: none, low, medium, high, xhigh.
        Higher effort = better quality but slower/more expensive.
        """
        return os.getenv("REASONING_EFFORT", "medium")

    # ==================== PDF Processing Configuration ====================

    @property
    def pdf_dpi(self) -> int:
        """DPI for PDF to image conversion."""
        return int(os.getenv("PDF_DPI", "300"))

    @property
    def image_format(self) -> str:
        """Image format for PDF conversion (PNG, JPEG)."""
        return os.getenv("IMAGE_FORMAT", "PNG")

    @property
    def use_image_cache(self) -> bool:
        """Whether to cache converted images."""
        return os.getenv("USE_IMAGE_CACHE", "true").lower() == "true"

    # ==================== Batch Processing Configuration ====================

    @property
    def batch_size(self) -> int:
        """Number of concurrent API calls for batch processing."""
        return int(os.getenv("BATCH_SIZE", "5"))

    @property
    def max_retries(self) -> int:
        """Maximum number of retries for failed API calls."""
        return int(os.getenv("MAX_RETRIES", "3"))

    @property
    def retry_delay(self) -> float:
        """Base delay between retries in seconds (uses exponential backoff)."""
        return float(os.getenv("RETRY_DELAY", "2.0"))

    # ==================== Schema Configuration ====================

    @property
    def initial_schema_pdf_count(self) -> int:
        """Number of PDFs to use for initial schema generation."""
        return int(os.getenv("INITIAL_SCHEMA_PDF_COUNT", "3"))

    # ==================== Vector Store Configuration ====================

    @property
    def vector_store_name(self) -> str:
        """Name for OpenAI vector store."""
        return os.getenv("VECTOR_STORE_NAME", "financial_research_corpus")

    # ==================== Logging Configuration ====================

    @property
    def log_level(self) -> str:
        """Logging level (DEBUG, INFO, WARNING, ERROR)."""
        return os.getenv("LOG_LEVEL", "INFO")

    @property
    def verbose(self) -> bool:
        """Whether to print verbose output."""
        return os.getenv("VERBOSE", "true").lower() == "true"

    # ==================== Development/Testing Configuration ====================

    @property
    def dev_mode(self) -> bool:
        """Whether running in development mode."""
        return os.getenv("DEV_MODE", "false").lower() == "true"

    @property
    def skip_existing(self) -> bool:
        """Whether to skip already processed PDFs."""
        return os.getenv("SKIP_EXISTING", "true").lower() == "true"

    # ==================== Helper Methods ====================

    def ensure_directories_exist(self):
        """Create all necessary directories if they don't exist."""
        directories = [
            self.data_dir,
            self.pdfs_dir,
            self.images_dir,
            self.database_dir,
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def get_summary(self) -> dict:
        """Get a dictionary summary of current configuration."""
        return {
            "project_root": str(self.project_root),
            "data_dir": str(self.data_dir),
            "database_path": str(self.database_path),
            "gpt5_model": self.gpt5_model,
            "gpt5_vision_model": self.gpt5_vision_model,
            "temperature": self.temperature,
            "pdf_dpi": self.pdf_dpi,
            "batch_size": self.batch_size,
            "max_retries": self.max_retries,
            "log_level": self.log_level,
            "dev_mode": self.dev_mode,
        }

    def print_summary(self):
        """Print a formatted summary of current configuration."""
        print("=" * 60)
        print("Configuration Summary")
        print("=" * 60)
        for key, value in self.get_summary().items():
            print(f"{key:25s}: {value}")
        print("=" * 60)


# Global config instance (can be imported by other modules)
config = Config()
