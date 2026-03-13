"""
Genetic Health Analysis Toolkit Backend
"""

__version__ = "1.0.0"
__author__ = "Genetic Health Analysis Team"

from .utils.vcf_parser import VCFParser

__all__ = [
    "VCFParser"
]