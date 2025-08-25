"""
API endpoint configurations for genetic variant annotation services
Contains all endpoint URLs, parameters, and configurations for external APIs
"""

import os
from typing import Dict, Optional
from dataclasses import dataclass

@dataclass
class APIEndpoint:
    """Configuration for an API endpoint"""
    url: str
    method: str = "GET"
    headers: Optional[Dict[str, str]] = None
    rate_limit: float = 10.0  # requests per second
    timeout: int = 30
    retries: int = 3
    description: str = ""

class APIEndpoints:
    """Centralized API endpoint configurations"""
    
    # NCBI E-utilities with API key from environment variable
    NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")  # Load from environment variable
    NCBI_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    NCBI_ENDPOINTS = {
        "esearch": APIEndpoint(
            url=f"{NCBI_BASE_URL}/esearch.fcgi",
            rate_limit=10.0,  # Increased from 3.0 to 10.0 with API key
            description="Search NCBI databases for UIDs"
        ),
        "efetch": APIEndpoint(
            url=f"{NCBI_BASE_URL}/efetch.fcgi",
            rate_limit=10.0,  # Increased from 3.0 to 10.0 with API key
            description="Fetch full records from NCBI databases"
        ),
        "einfo": APIEndpoint(
            url=f"{NCBI_BASE_URL}/einfo.fcgi",
            rate_limit=10.0,  # Increased from 3.0 to 10.0 with API key
            description="Get information about NCBI databases"
        ),
        "elink": APIEndpoint(
            url=f"{NCBI_BASE_URL}/elink.fcgi",
            rate_limit=10.0,  # Increased from 3.0 to 10.0 with API key
            description="Find related records in NCBI databases"
        ),
        "esummary": APIEndpoint(
            url=f"{NCBI_BASE_URL}/esummary.fcgi",
            rate_limit=10.0,  # Increased from 3.0 to 10.0 with API key
            description="Get document summaries from NCBI databases"
        )
    }
    
    # LitVar API
    LITVAR_BASE_URL = "https://www.ncbi.nlm.nih.gov/research/litvar2-api"
    LITVAR_ENDPOINTS = {
        "variant_search": APIEndpoint(
            url=f"{LITVAR_BASE_URL}/variant/search",
            rate_limit=10.0,
            description="Search for variants in literature"
        ),
        "variant_detail": APIEndpoint(
            url=f"{LITVAR_BASE_URL}/variant/{{variant_id}}",
            rate_limit=10.0,
            description="Get detailed variant information"
        ),
        "publications": APIEndpoint(
            url=f"{LITVAR_BASE_URL}/variant/{{variant_id}}/publications",
            rate_limit=10.0,
            description="Get publications for a variant"
        )
    }
    
    # SNPedia MediaWiki API
    SNPEDIA_BASE_URL = "https://bots.snpedia.com/api.php"
    SNPEDIA_ENDPOINTS = {
        "query": APIEndpoint(
            url=SNPEDIA_BASE_URL,
            rate_limit=10.0,
            description="Query SNPedia pages via MediaWiki API"
        ),
        "parse": APIEndpoint(
            url=SNPEDIA_BASE_URL,
            rate_limit=10.0,
            description="Parse SNPedia page content"
        ),
        "opensearch": APIEndpoint(
            url=SNPEDIA_BASE_URL,
            rate_limit=10.0,
            description="OpenSearch API for SNPedia"
        )
    }
    
    # Ensembl REST API
    ENSEMBL_BASE_URL = "https://rest.ensembl.org"
    ENSEMBL_ENDPOINTS = {
        "variation": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/variation/human/{{rsid}}",
            headers={"Content-Type": "application/json"},
            rate_limit=15.0,
            description="Get variant information"
        ),
        "vep": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/vep/human/id/{{rsid}}",
            headers={"Content-Type": "application/json"},
            rate_limit=15.0,
            description="Variant Effect Predictor"
        ),
        "lookup": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/lookup/id/{{gene_id}}",
            headers={"Content-Type": "application/json"},
            rate_limit=15.0,
            description="Look up gene information"
        ),
        "phenotype": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/phenotype/region/human/{{region}}",
            headers={"Content-Type": "application/json"},
            rate_limit=15.0,
            description="Get phenotype associations"
        ),
        "regulatory": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/regulatory/species/human/{{rsid}}",
            headers={"Content-Type": "application/json"},
            rate_limit=15.0,
            description="Get regulatory features"
        )
    }
    
    # PharmGKB API
    PHARMGKB_BASE_URL = "https://api.pharmgkb.org"
    PHARMGKB_ENDPOINTS = {
        # Gene endpoints
        "gene": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/gene/{{gene}}",
            rate_limit=10.0,
            description="Get gene information"
        ),
        "gene_drugs": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/gene/{{gene}}/drugs",
            rate_limit=10.0,
            description="Get drugs associated with gene"
        ),
        "gene_annotations": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/gene/{{gene}}/clinicalAnnotations",
            rate_limit=10.0,
            description="Get clinical annotations for gene"
        ),
        "gene_variants": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/gene/{{gene}}/variants",
            rate_limit=10.0,
            description="Get variants in gene"
        ),
        "gene_haplotypes": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/gene/{{gene}}/haplotypes",
            rate_limit=10.0,
            description="Get haplotypes for gene"
        ),
        
        # Variant endpoints
        "variant": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/variant/{{rsid}}",
            rate_limit=10.0,
            description="Get variant information"
        ),
        "variant_annotations": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/variant/{{rsid}}/clinicalAnnotations",
            rate_limit=10.0,
            description="Get clinical annotations for variant"
        ),
        "variant_drug_labels": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/variant/{{rsid}}/drugLabels",
            rate_limit=10.0,
            description="Get drug labels for variant"
        ),
        "variant_guidelines": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/variant/{{rsid}}/guidelines",
            rate_limit=10.0,
            description="Get guidelines for variant"
        ),
        
        # Drug endpoints
        "drug": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/drug/{{drug_id}}",
            rate_limit=10.0,
            description="Get drug information"
        ),
        "drug_search": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/drug/search",
            rate_limit=10.0,
            description="Search for drugs"
        ),
        "drug_annotations": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/drug/{{drug_id}}/clinicalAnnotations",
            rate_limit=10.0,
            description="Get clinical annotations for drug"
        ),
        "drug_genes": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/drug/{{drug_id}}/genes",
            rate_limit=10.0,
            description="Get genes associated with drug"
        ),
        "drug_variants": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/drug/{{drug_id}}/variants",
            rate_limit=10.0,
            description="Get variants associated with drug"
        ),
        "drug_labels": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/drug/{{drug_id}}/drugLabels",
            rate_limit=10.0,
            description="Get drug labels"
        ),
        
        # Guideline endpoints
        "guidelines": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/guideline",
            rate_limit=10.0,
            description="Get all guidelines"
        ),
        "guideline": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/guideline/{{guideline_id}}",
            rate_limit=10.0,
            description="Get specific guideline"
        ),
        
        # Clinical annotation endpoints
        "annotations": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/clinicalAnnotation",
            rate_limit=10.0,
            description="Get all clinical annotations"
        ),
        "annotation": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/clinicalAnnotation/{{annotation_id}}",
            rate_limit=10.0,
            description="Get specific clinical annotation"
        ),
        
        # Haplotype endpoints
        "haplotypes": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/haplotype",
            rate_limit=10.0,
            description="Get all haplotypes"
        ),
        "haplotype": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/haplotype/{{haplotype_id}}",
            rate_limit=10.0,
            description="Get specific haplotype"
        ),
        
        # Phenotype endpoints
        "phenotypes": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/phenotype",
            rate_limit=10.0,
            description="Get all phenotypes"
        ),
        "phenotype": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/phenotype/{{phenotype_id}}",
            rate_limit=10.0,
            description="Get specific phenotype"
        ),
        
        # Chemical endpoints
        "chemicals": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/chemical",
            rate_limit=10.0,
            description="Get all chemicals"
        ),
        "chemical": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/chemical/{{chemical_id}}",
            rate_limit=10.0,
            description="Get specific chemical"
        ),
        
        # Disease endpoints
        "diseases": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/disease",
            rate_limit=10.0,
            description="Get all diseases"
        ),
        "disease": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/disease/{{disease_id}}",
            rate_limit=10.0,
            description="Get specific disease"
        )
    }
    
    # ClinVar via NCBI (specific configurations)
    CLINVAR_DATABASES = ["clinvar"]
    
    # PubMed via NCBI (specific configurations)
    PUBMED_DATABASES = ["pubmed", "pmc"]
    
    # dbSNP via NCBI (specific configurations)
    DBSNP_DATABASES = ["snp"]
    
    @classmethod
    def get_endpoint(cls, service: str, endpoint_name: str) -> Optional[APIEndpoint]:
        """Get endpoint configuration by service and name"""
        service_endpoints = {
            "ncbi": cls.NCBI_ENDPOINTS,
            "litvar": cls.LITVAR_ENDPOINTS,
            "snpedia": cls.SNPEDIA_ENDPOINTS,
            "ensembl": cls.ENSEMBL_ENDPOINTS,
            "pharmgkb": cls.PHARMGKB_ENDPOINTS
        }
        
        endpoints = service_endpoints.get(service.lower())
        if endpoints:
            return endpoints.get(endpoint_name)
        return None
    
    @classmethod
    def get_service_endpoints(cls, service: str) -> Dict[str, APIEndpoint]:
        """Get all endpoints for a specific service"""
        service_endpoints = {
            "ncbi": cls.NCBI_ENDPOINTS,
            "litvar": cls.LITVAR_ENDPOINTS,
            "snpedia": cls.SNPEDIA_ENDPOINTS,
            "ensembl": cls.ENSEMBL_ENDPOINTS,
            "pharmgkb": cls.PHARMGKB_ENDPOINTS
        }
        return service_endpoints.get(service.lower(), {})
    
    @classmethod
    def get_all_endpoints(cls) -> Dict[str, Dict[str, APIEndpoint]]:
        """Get all endpoint configurations"""
        return {
            "ncbi": cls.NCBI_ENDPOINTS,
            "litvar": cls.LITVAR_ENDPOINTS,
            "snpedia": cls.SNPEDIA_ENDPOINTS,
            "ensembl": cls.ENSEMBL_ENDPOINTS,
            "pharmgkb": cls.PHARMGKB_ENDPOINTS
        }
    
    @classmethod
    def format_url(cls, url_template: str, **kwargs) -> str:
        """Format URL template with provided parameters"""
        return url_template.format(**kwargs)

# Database configurations
DATABASE_CONFIGS = {
    "clinvar": {
        "name": "ClinVar",
        "description": "Clinical variant interpretations",
        "ncbi_db": "clinvar",
        "rate_limit": 10.0  # Increased from 3.0 to 10.0 with API key
    },
    "pubmed": {
        "name": "PubMed",
        "description": "Biomedical literature database",
        "ncbi_db": "pubmed",
        "rate_limit": 10.0  # Increased from 3.0 to 10.0 with API key
    },
    "pmc": {
        "name": "PubMed Central",
        "description": "Free full-text biomedical literature",
        "ncbi_db": "pmc",
        "rate_limit": 10.0  # Increased from 3.0 to 10.0 with API key
    },
    "snp": {
        "name": "dbSNP",
        "description": "Single nucleotide polymorphism database",
        "ncbi_db": "snp",
        "rate_limit": 10.0  # Increased from 3.0 to 10.0 with API key
    },
    "gene": {
        "name": "Gene",
        "description": "Gene-specific information",
        "ncbi_db": "gene",
        "rate_limit": 10.0  # Increased from 3.0 to 10.0 with API key
    },
    "omim": {
        "name": "OMIM",
        "description": "Online Mendelian Inheritance in Man",
        "ncbi_db": "omim",
        "rate_limit": 10.0  # Increased from 3.0 to 10.0 with API key
    }
}

# Search term templates
SEARCH_TEMPLATES = {
    "variant_literature": '"{rsid}"[All Fields] OR "{rsid}"[Title/Abstract]',
    "gene_literature": '"{gene}"[All Fields] AND ("pharmacogenom*" OR "drug response" OR "genetic variant")',
    "drug_gene": '"{drug}"[All Fields] AND "{gene}"[All Fields]',
    "variant_clinvar": '{rsid}[All Fields]',
    "gene_variants": '{gene}[Gene Name] AND "snp"[Filter]'
}

# Response parsing configurations
PARSING_CONFIGS = {
    "clinvar_xml": {
        "variation_archive": ".//VariationArchive",
        "clinical_significance": ".//ClinicalSignificance/Description",
        "conditions": ".//Trait/Name/ElementValue",
        "accession": "Accession",
        "variation_id": "VariationID"
    },
    "pubmed_xml": {
        "article": ".//PubmedArticle",
        "pmid": ".//PMID",
        "title": ".//ArticleTitle",
        "authors": ".//Author",
        "journal": ".//Journal/Title",
        "pub_date": ".//PubDate/Year",
        "abstract": ".//Abstract/AbstractText"
    },
    "snpedia_mediawiki": {
        "page_exists": lambda page_id: page_id != '-1',
        "extract_magnitude": r'magnitude[:\s]*(\d+)',
        "extract_frequency": r'frequency[:\s]*([0-9.]+)',
        "extract_genotype": r'genotype[:\s]*([ATCG/]+)'
    }
}