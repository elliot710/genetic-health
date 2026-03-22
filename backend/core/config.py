"""
Configuration settings for the genetic analysis toolkit.
"""
import os
from dataclasses import dataclass


@dataclass
class APIConfiguration:
    """Configuration for external API services."""
    base_delay: float = 0.1
    max_retries: int = 3
    timeout: float = 30.0
    batch_size: int = 50
    max_concurrent: int = 3


@dataclass
class AnalysisConfiguration:
    """Configuration for genetic analysis processing."""
    default_batch_size: int = 10
    max_variants_per_batch: int = 20
    processing_timeout: int = 3600  # 1 hour
    progress_update_interval: int = 5
    enable_specialized_analysis: bool = True
    enable_parallel_processing: bool = True
    exclude_benign_from_panels: bool = True  # Skip benign/likely_benign classified variants from panel insights


@dataclass
class DatabaseConfiguration:
    """Configuration for database operations."""
    max_connections: int = 20
    connection_timeout: int = 30
    query_timeout: int = 60
    enable_connection_pooling: bool = True


class Settings:
    """Centralized application settings."""
    
    def __init__(self):
        self.api = APIConfiguration()
        self.analysis = AnalysisConfiguration()
        self.database = DatabaseConfiguration()
        
        # Load from environment variables if available
        self._load_from_env()
    
    def _load_from_env(self):
        """Load configuration from environment variables."""
        # API settings
        self.api.base_delay = float(os.getenv('API_BASE_DELAY', self.api.base_delay))
        self.api.max_retries = int(os.getenv('API_MAX_RETRIES', self.api.max_retries))
        self.api.timeout = float(os.getenv('API_TIMEOUT', self.api.timeout))
        self.api.batch_size = int(os.getenv('API_BATCH_SIZE', self.api.batch_size))
        self.api.max_concurrent = int(os.getenv('API_MAX_CONCURRENT', self.api.max_concurrent))
        
        # Analysis settings
        self.analysis.default_batch_size = int(os.getenv('ANALYSIS_BATCH_SIZE', self.analysis.default_batch_size))
        self.analysis.max_variants_per_batch = int(os.getenv('ANALYSIS_MAX_VARIANTS_PER_BATCH', self.analysis.max_variants_per_batch))
        self.analysis.processing_timeout = int(os.getenv('ANALYSIS_TIMEOUT', self.analysis.processing_timeout))
        self.analysis.enable_specialized_analysis = os.getenv('ENABLE_SPECIALIZED_ANALYSIS', 'true').lower() == 'true'
        self.analysis.enable_parallel_processing = os.getenv('ENABLE_PARALLEL_PROCESSING', 'true').lower() == 'true'
        self.analysis.exclude_benign_from_panels = os.getenv('EXCLUDE_BENIGN_FROM_PANELS', 'true').lower() == 'true'
        
        # Database settings
        self.database.max_connections = int(os.getenv('DB_MAX_CONNECTIONS', self.database.max_connections))
        self.database.connection_timeout = int(os.getenv('DB_CONNECTION_TIMEOUT', self.database.connection_timeout))
        self.database.query_timeout = int(os.getenv('DB_QUERY_TIMEOUT', self.database.query_timeout))


# Global settings instance
settings = Settings()