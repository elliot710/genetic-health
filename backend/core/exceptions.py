"""
Custom exception classes for the genetic analysis toolkit.
"""
from typing import Optional, Dict, Any


class GeneticAnalysisException(Exception):
    """Base exception for genetic analysis operations."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class AnalysisNotFoundException(GeneticAnalysisException):
    """Raised when a genetic analysis is not found."""
    pass


class VariantProcessingException(GeneticAnalysisException):
    """Raised when variant processing fails."""
    pass


class FileParsingException(GeneticAnalysisException):
    """Raised when an uploaded genetic data file cannot be parsed."""
    pass


class APIServiceException(GeneticAnalysisException):
    """Base exception for external API service errors."""
    pass


class APIRateLimitException(APIServiceException):
    """Raised when API rate limits are exceeded."""
    pass


class APIConnectionException(APIServiceException):
    """Raised when API connection fails."""
    pass


class APIResponseException(APIServiceException):
    """Raised when API returns invalid response."""
    pass


class DatabaseException(GeneticAnalysisException):
    """Raised when database operations fail."""
    pass


class AnalysisTimeoutException(GeneticAnalysisException):
    """Raised when analysis times out."""
    pass


class InvalidVariantException(GeneticAnalysisException):
    """Raised when variant data is invalid."""
    pass


class SpecializedAnalysisException(GeneticAnalysisException):
    """Raised when specialized analysis fails."""
    pass