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

# =============================================================================
# CENTRALIZED RATE LIMIT CONFIGURATION
# =============================================================================
# All API rate limits defined in one place for easy adjustment
RATE_LIMITS = {
    # NCBI E-utilities (with API key can handle higher rates)
    'NCBI': 10.0,  # requests per second - increased from 3.0 with API key
    
    # Ensembl VEP API (generous rate limits)
    'ENSEMBL': 15.0,  # requests per second
    
    # PharmGKB API (very conservative to avoid 429 errors)
    'PHARMGKB': 0.9,  # requests per second
    
    # ClinVar API (NCBI-based, same as NCBI)
    'CLINVAR': 7.0,  # requests per second
    
    # SNPedia API (MediaWiki based, conservative)
    'SNPEDIA': 2.0,  # requests per second
    
    # LitVar/PubMed API (NCBI-based)
    'LITVAR': 10.0,  # requests per second
}

class APIEndpoints:
    """Centralized API endpoint configurations"""
    
    # NCBI E-utilities with API key from environment variable
    NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")  # Load from environment variable
    NCBI_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    NCBI_ENDPOINTS = {
        "esearch": APIEndpoint(
            url=f"{NCBI_BASE_URL}/esearch.fcgi",
            rate_limit=RATE_LIMITS['NCBI'],
            description="Search NCBI databases for UIDs"
        ),
        "efetch": APIEndpoint(
            url=f"{NCBI_BASE_URL}/efetch.fcgi",
            rate_limit=RATE_LIMITS['NCBI'],
            description="Fetch full records from NCBI databases"
        ),
        "einfo": APIEndpoint(
            url=f"{NCBI_BASE_URL}/einfo.fcgi",
            rate_limit=RATE_LIMITS['NCBI'],
            description="Get information about NCBI databases"
        ),
        "elink": APIEndpoint(
            url=f"{NCBI_BASE_URL}/elink.fcgi",
            rate_limit=RATE_LIMITS['NCBI'],
            description="Find related records in NCBI databases"
        ),
        "esummary": APIEndpoint(
            url=f"{NCBI_BASE_URL}/esummary.fcgi",
            rate_limit=RATE_LIMITS['NCBI'],
            description="Get document summaries from NCBI databases"
        )
    }
    
    # LitVar API
    LITVAR_BASE_URL = "https://www.ncbi.nlm.nih.gov/research/litvar2-api"
    LITVAR_ENDPOINTS = {
        "variant_search": APIEndpoint(
            url=f"{LITVAR_BASE_URL}/variant/search",
            rate_limit=RATE_LIMITS['NCBI'],
            description="Search for variants in literature"
        ),
        "variant_detail": APIEndpoint(
            url=f"{LITVAR_BASE_URL}/variant/{{variant_id}}",
            rate_limit=RATE_LIMITS['NCBI'],
            description="Get detailed variant information"
        ),
        "publications": APIEndpoint(
            url=f"{LITVAR_BASE_URL}/variant/{{variant_id}}/publications",
            rate_limit=RATE_LIMITS['NCBI'],
            description="Get publications for a variant"
        )
    }
    
    # SNPedia MediaWiki API
    SNPEDIA_BASE_URL = "https://bots.snpedia.com/api.php"
    SNPEDIA_ENDPOINTS = {
        "query": APIEndpoint(
            url=SNPEDIA_BASE_URL,
            rate_limit=RATE_LIMITS['SNPEDIA'],
            description="Query SNPedia pages via MediaWiki API"
        ),
        "parse": APIEndpoint(
            url=SNPEDIA_BASE_URL,
            rate_limit=RATE_LIMITS['SNPEDIA'],
            description="Parse SNPedia page content"
        ),
        "opensearch": APIEndpoint(
            url=SNPEDIA_BASE_URL,
            rate_limit=RATE_LIMITS['SNPEDIA'],
            description="OpenSearch API for SNPedia"
        )
    }
    
    # Ensembl REST API - Enhanced with comprehensive VEP and annotation endpoints
    ENSEMBL_BASE_URL = "https://rest.ensembl.org"
    ENSEMBL_ENDPOINTS = {
        # Basic variant information
        "variation": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/variation/human/{{rsid}}",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['ENSEMBL'],
            description="Get variant information with population frequencies"
        ),
        
        # Enhanced VEP with comprehensive annotations
        "vep_comprehensive": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/vep/human/id",
            method="POST",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['ENSEMBL'],
            description="Comprehensive VEP with pathogenicity scores (CADD, REVEL, etc.)"
        ),
        "vep_basic": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/vep/human/id/{{rsid}}",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['ENSEMBL'],
            description="Basic Variant Effect Predictor"
        ),
        
        # Gene and transcript information
        "lookup_gene": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/lookup/id/{{gene_id}}",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['ENSEMBL'],
            description="Look up gene information"
        ),
        "lookup_symbol": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/lookup/symbol/human/{{gene_symbol}}",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['ENSEMBL'],
            description="Look up gene by symbol"
        ),
        
        # Population and frequency data
        "variation_populations": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/variation/human/{{rsid}}/populations",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['ENSEMBL'],
            description="Get population frequencies for variant"
        ),
        
        # Phenotype and disease associations
        "phenotype_variant": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/phenotype/variant/human/{{rsid}}",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['ENSEMBL'],
            description="Get phenotype associations for variant"
        ),
        "phenotype_gene": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/phenotype/gene/human/{{gene_id}}",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['ENSEMBL'],
            description="Get phenotype associations for gene"
        ),
        "phenotype_region": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/phenotype/region/human/{{region}}",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['ENSEMBL'],
            description="Get phenotype associations for genomic region"
        ),
        
        # Regulatory and functional elements
        "regulatory_variant": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/regulatory/species/human/{{rsid}}",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['ENSEMBL'],
            description="Get regulatory features for variant"
        ),
        "regulatory_region": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/regulatory/species/human/{{region}}",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['ENSEMBL'],
            description="Get regulatory features for region"
        ),
        
        # Linkage disequilibrium and population genetics
        "ld": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/ld/human/{{rsid}}",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['ENSEMBL'],
            description="Get linkage disequilibrium data"
        ),
        
        # Protein and transcript information
        "transcript": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/lookup/id/{{transcript_id}}",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['ENSEMBL'],
            description="Get transcript information"
        ),
        "protein_features": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/overlap/id/{{gene_id}}",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['ENSEMBL'],
            description="Get protein domains and features"
        ),
        
        # Comparative genomics and conservation
        "homology": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/homology/id/{{gene_id}}",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['ENSEMBL'],
            description="Get gene homology across species"
        ),
        
        # Sequence and assembly information
        "sequence_variant": APIEndpoint(
            url=f"{ENSEMBL_BASE_URL}/sequence/region/human/{{region}}",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['ENSEMBL'],
            description="Get genomic sequence for region"
        )
    }
    
    # PharmGKB API
    PHARMGKB_BASE_URL = "https://api.pharmgkb.org"
    PHARMGKB_ENDPOINTS = {
        # Gene endpoints
        "gene": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/gene/{{gene}}",
            rate_limit=RATE_LIMITS['PHARMGKB'],
            description="Get gene information"
        ),
        "gene_drugs": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/gene/{{gene}}/drugs",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get drugs associated with gene"
        ),
        "gene_annotations": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/gene/{{gene}}/clinicalAnnotations",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get clinical annotations for gene"
        ),
        "gene_variants": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/gene/{{gene}}/variants",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get variants in gene"
        ),
        "gene_haplotypes": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/gene/{{gene}}/haplotypes",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get haplotypes for gene"
        ),
        
        # Variant endpoints
        "variant": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/variant/{{rsid}}",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get variant information"
        ),
        "variant_annotations": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/variant/{{rsid}}/clinicalAnnotations",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get clinical annotations for variant"
        ),
        "variant_drug_labels": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/variant/{{rsid}}/drugLabels",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get drug labels for variant"
        ),
        "variant_guidelines": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/variant/{{rsid}}/guidelines",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get guidelines for variant"
        ),
        
        # Drug endpoints
        "drug": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/drug/{{drug_id}}",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get drug information"
        ),
        "drug_search": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/drug/search",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Search for drugs"
        ),
        "drug_annotations": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/drug/{{drug_id}}/clinicalAnnotations",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get clinical annotations for drug"
        ),
        "drug_genes": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/drug/{{drug_id}}/genes",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get genes associated with drug"
        ),
        "drug_variants": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/drug/{{drug_id}}/variants",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get variants associated with drug"
        ),
        "drug_labels": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/drug/{{drug_id}}/drugLabels",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get drug labels"
        ),
        
        # Guideline endpoints
        "guidelines": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/guideline",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get all guidelines"
        ),
        "guideline": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/guideline/{{guideline_id}}",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get specific guideline"
        ),
        
        # Clinical annotation endpoints
        "annotations": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/clinicalAnnotation",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get all clinical annotations"
        ),
        "annotation": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/clinicalAnnotation/{{annotation_id}}",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get specific clinical annotation"
        ),
        
        # Haplotype endpoints
        "haplotypes": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/haplotype",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get all haplotypes"
        ),
        "haplotype": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/haplotype/{{haplotype_id}}",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get specific haplotype"
        ),
        
        # Phenotype endpoints
        "phenotypes": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/phenotype",
            rate_limit=RATE_LIMITS['PHARMGKB'],  # Reduced from 10.0 to RATE_LIMITS['PHARMGKB']
            description="Get all phenotypes"
        ),
        "phenotype": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/phenotype/{{phenotype_id}}",
            rate_limit=RATE_LIMITS['PHARMGKB'],
            description="Get specific phenotype"
        ),
        
        # Chemical endpoints
        "chemicals": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/chemical",
            rate_limit=RATE_LIMITS['PHARMGKB'],
            description="Get all chemicals"
        ),
        "chemical": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/chemical/{{chemical_id}}",
            rate_limit=RATE_LIMITS['PHARMGKB'],
            description="Get specific chemical"
        ),
        
        # Disease endpoints
        "diseases": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/disease",
            rate_limit=RATE_LIMITS['PHARMGKB'],
            description="Get all diseases"
        ),
        "disease": APIEndpoint(
            url=f"{PHARMGKB_BASE_URL}/v1/disease/{{disease_id}}",
            rate_limit=RATE_LIMITS['PHARMGKB'],
            description="Get specific disease"
        )
    }
    
    # ClinVar via NCBI (specific configurations)
    CLINVAR_DATABASES = ["clinvar"]
    
    # PubMed via NCBI (specific configurations)
    PUBMED_DATABASES = ["pubmed", "pmc"]
    
    # dbSNP via NCBI (specific configurations)
    DBSNP_DATABASES = ["snp"]
    
    # Additional genomic databases and clinical resources
    
    # ClinGen API
    CLINGEN_BASE_URL = "https://clinicalgenome.org/curation-activities/gene-disease-validity"
    CLINGEN_ENDPOINTS = {
        "gene_validity": APIEndpoint(
            url=f"{CLINGEN_BASE_URL}/gene/{{gene_symbol}}",
            rate_limit=RATE_LIMITS['NCBI'],
            description="Get gene-disease validity classifications"
        ),
        "dosage_sensitivity": APIEndpoint(
            url="https://dosage.clinicalgenome.org/api/region/{{region}}",
            rate_limit=RATE_LIMITS['NCBI'],
            description="Get dosage sensitivity information"
        )
    }
    
    # gnomAD API (via Ensembl and direct)
    GNOMAD_BASE_URL = "https://gnomad.broadinstitute.org/api"
    GNOMAD_ENDPOINTS = {
        "variant": APIEndpoint(
            url=f"{GNOMAD_BASE_URL}/variant/{{variant_id}}",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['NCBI'],
            description="Get gnomAD population frequencies and constraint metrics"
        ),
        "gene_constraint": APIEndpoint(
            url=f"{GNOMAD_BASE_URL}/gene/{{gene_id}}/constraint",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['NCBI'],
            description="Get gene constraint scores (pLI, LOEUF)"
        )
    }
    
    # UniProt API for protein information
    UNIPROT_BASE_URL = "https://rest.uniprot.org"
    UNIPROT_ENDPOINTS = {
        "protein": APIEndpoint(
            url=f"{UNIPROT_BASE_URL}/uniprotkb/{{accession}}",
            headers={"Accept": "application/json"},
            rate_limit=RATE_LIMITS['NCBI'],
            description="Get protein information and annotations"
        ),
        "protein_search": APIEndpoint(
            url=f"{UNIPROT_BASE_URL}/uniprotkb/search",
            headers={"Accept": "application/json"},
            rate_limit=RATE_LIMITS['NCBI'],
            description="Search proteins by gene name or other criteria"
        ),
        "protein_features": APIEndpoint(
            url=f"{UNIPROT_BASE_URL}/uniprotkb/{{accession}}/features",
            headers={"Accept": "application/json"},
            rate_limit=RATE_LIMITS['NCBI'],
            description="Get protein domains and functional features"
        )
    }
    
    # STRING API for protein interactions
    STRING_BASE_URL = "https://string-db.org/api"
    STRING_ENDPOINTS = {
        "interactions": APIEndpoint(
            url=f"{STRING_BASE_URL}/json/network",
            rate_limit=RATE_LIMITS['NCBI'],
            description="Get protein-protein interaction networks"
        ),
        "functional_enrichment": APIEndpoint(
            url=f"{STRING_BASE_URL}/json/enrichment",
            rate_limit=RATE_LIMITS['NCBI'],
            description="Get functional enrichment analysis"
        )
    }
    
    # OMIM API for disease information  
    OMIM_BASE_URL = "https://api.omim.org/api"
    OMIM_ENDPOINTS = {
        "entry": APIEndpoint(
            url=f"{OMIM_BASE_URL}/entry",
            rate_limit=RATE_LIMITS['NCBI'],
            description="Get OMIM disease entries"
        ),
        "gene": APIEndpoint(
            url=f"{OMIM_BASE_URL}/entry/search",
            rate_limit=RATE_LIMITS['NCBI'],
            description="Search OMIM by gene or phenotype"
        )
    }
    
    # GWAS Catalog API
    GWAS_BASE_URL = "https://www.ebi.ac.uk/gwas/rest/api"
    GWAS_ENDPOINTS = {
        "variant_associations": APIEndpoint(
            url=f"{GWAS_BASE_URL}/singleNucleotidePolymorphisms/{{rsid}}/associations",
            headers={"Accept": "application/json"},
            rate_limit=RATE_LIMITS['NCBI'],
            description="Get GWAS associations for variant"
        ),
        "gene_associations": APIEndpoint(
            url=f"{GWAS_BASE_URL}/genes/{{gene_name}}/associations",
            headers={"Accept": "application/json"},
            rate_limit=RATE_LIMITS['NCBI'],
            description="Get GWAS associations for gene"
        ),
        "trait_associations": APIEndpoint(
            url=f"{GWAS_BASE_URL}/efoTraits/{{trait_id}}/associations",
            headers={"Accept": "application/json"},
            rate_limit=RATE_LIMITS['NCBI'],
            description="Get GWAS associations for trait"
        )
    }
    
    # Open Targets API for disease-target associations
    OPENTARGETS_BASE_URL = "https://api.platform.opentargets.org/api/v4/graphql"
    OPENTARGETS_ENDPOINTS = {
        "target_disease": APIEndpoint(
            url=OPENTARGETS_BASE_URL,
            method="POST",
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['NCBI'],
            description="Get target-disease associations"
        ),
        "drug_target": APIEndpoint(
            url=OPENTARGETS_BASE_URL,
            method="POST", 
            headers={"Content-Type": "application/json"},
            rate_limit=RATE_LIMITS['NCBI'],
            description="Get drug-target associations"
        )
    }
    
    @classmethod
    def get_endpoint(cls, service: str, endpoint_name: str) -> Optional[APIEndpoint]:
        """Get endpoint configuration by service and name"""
        service_endpoints = {
            "ncbi": cls.NCBI_ENDPOINTS,
            "litvar": cls.LITVAR_ENDPOINTS,
            "snpedia": cls.SNPEDIA_ENDPOINTS,
            "ensembl": cls.ENSEMBL_ENDPOINTS,
            "pharmgkb": cls.PHARMGKB_ENDPOINTS,
            "clingen": cls.CLINGEN_ENDPOINTS,
            "gnomad": cls.GNOMAD_ENDPOINTS,
            "uniprot": cls.UNIPROT_ENDPOINTS,
            "string": cls.STRING_ENDPOINTS,
            "omim": cls.OMIM_ENDPOINTS,
            "gwas": cls.GWAS_ENDPOINTS,
            "opentargets": cls.OPENTARGETS_ENDPOINTS
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
            "pharmgkb": cls.PHARMGKB_ENDPOINTS,
            "clingen": cls.CLINGEN_ENDPOINTS,
            "gnomad": cls.GNOMAD_ENDPOINTS,
            "uniprot": cls.UNIPROT_ENDPOINTS,
            "string": cls.STRING_ENDPOINTS,
            "omim": cls.OMIM_ENDPOINTS,
            "gwas": cls.GWAS_ENDPOINTS,
            "opentargets": cls.OPENTARGETS_ENDPOINTS
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
            "pharmgkb": cls.PHARMGKB_ENDPOINTS,
            "clingen": cls.CLINGEN_ENDPOINTS,
            "gnomad": cls.GNOMAD_ENDPOINTS,
            "uniprot": cls.UNIPROT_ENDPOINTS,
            "string": cls.STRING_ENDPOINTS,
            "omim": cls.OMIM_ENDPOINTS,
            "gwas": cls.GWAS_ENDPOINTS,
            "opentargets": cls.OPENTARGETS_ENDPOINTS
        }
    
    @classmethod
    def format_url(cls, url_template: str, **kwargs) -> str:
        """Format URL template with provided parameters"""
        return url_template.format(**kwargs)

# VEP Configuration Templates for different analysis scenarios
VEP_CONFIGS = {
    "comprehensive": {
        # Core annotation features
        "hgvs": "1",
        "canonical": "1",
        "ccds": "1",
        "domains": "1",
        "numbers": "1",
        "protein": "1",
        "variant_class": "1",
        "tsl": "1",
        "appris": "1",
        "mane": "1",
        "uniprot": "1",
        
        # Clinical and pathogenicity predictions
        "CADD": "snv_indels",  # CADD deleteriousness scores
        "REVEL": "1",          # Rare Exome Variant Ensemble Learner
        "AlphaMissense": "1",  # Google DeepMind pathogenicity scores
        "ClinPred": "1",       # Disease-relevant variant prediction
        "EVE": "1",            # Evolutionary model of variant effect
        "SpliceAI": "2",       # Splice junction predictions
        "LOEUF": "1",          # Loss-of-function constraint scores
        "LoF": "1",            # Loss-of-function identification
        
        # Database annotations
        "dbNSFP": "LRT_pred,MutationTaster_pred,SIFT_pred,Polyphen2_HDIV_pred,CADD_phred,GERP++_RS,phyloP30way_mammalian,phastCons30way_mammalian",
        "dbscSNV": "1",        # Splicing predictions
        "Phenotypes": "1",     # Phenotype associations
        "GO": "1",             # Gene Ontology terms
        "IntAct": "1",         # Molecular interactions
        "Geno2MP": "1",        # Genotype-phenotype associations
        "OpenTargets": "1",    # Drug targets and disease associations
        "MaveDB": "1",         # Multiplexed variant effect assays
        "DosageSensitivity": "1", # Haploinsufficiency scores
        
        # Regulatory and conservation
        "Enformer": "1",       # Gene expression impact
        "UTRAnnotator": "1",   # UTR variant effects
        "MaxEntScan": "1",     # Splice site predictions
        "GeneSplicer": "1",    # Splice site detection
        "NMD": "1",            # Nonsense-mediated decay
        "Blosum62": "1",       # Amino acid conservation
        "AncestralAllele": "1", # Ancestral allele information
        
        # Output format
        "pick": "1",           # Pick most severe consequence
        "format": "json"
    },
    
    "pharmacogenomics": {
        # Core features for drug response analysis
        "hgvs": "1",
        "canonical": "1",
        "protein": "1",
        "variant_class": "1",
        "mane": "1",
        
        # Key pathogenicity scores for drug metabolism
        "CADD": "snv_indels",
        "REVEL": "1",
        "SIFT": "1",
        "PolyPhen": "1",
        
        # Pharmacogenomic-relevant annotations
        "dbNSFP": "SIFT_pred,Polyphen2_HDIV_pred,LRT_pred,MutationTaster_pred",
        "OpenTargets": "1",
        "Phenotypes": "1",
        
        "pick": "1",
        "format": "json"
    },
    
    "clinical": {
        # Clinical interpretation focused
        "hgvs": "1",
        "canonical": "1",
        "mane": "1",
        "ccds": "1",
        "domains": "1",
        "protein": "1",
        
        # Clinical prediction tools
        "ClinPred": "1",
        "REVEL": "1",
        "AlphaMissense": "1",
        "CADD": "snv_indels",
        "LOEUF": "1",
        "LoF": "1",
        
        # Clinical databases
        "Phenotypes": "1",
        "Geno2MP": "1",
        "DosageSensitivity": "1",
        
        "pick": "1",
        "format": "json"
    },
    
    "research": {
        # Research-focused with extensive annotations
        "hgvs": "1",
        "canonical": "1",
        "ccds": "1",
        "domains": "1",
        "numbers": "1",
        "protein": "1",
        "variant_class": "1",
        "tsl": "1",
        "appris": "1",
        "mane": "1",
        "uniprot": "1",
        "per_gene": "1",
        
        # Full pathogenicity suite
        "CADD": "snv_indels",
        "REVEL": "1",
        "AlphaMissense": "1",
        "ClinPred": "1",
        "EVE": "1",
        "SpliceAI": "2",
        "LOEUF": "1",
        "LoF": "1",
        
        # Comprehensive database annotations
        "dbNSFP": "ALL",  # All available fields (large dataset)
        "dbscSNV": "1",
        "Phenotypes": "1",
        "GO": "1",
        "IntAct": "1",
        "Geno2MP": "1",
        "OpenTargets": "1",
        "MaveDB": "1",
        "DosageSensitivity": "1",
        "Enformer": "1",
        "UTRAnnotator": "1",
        "MaxEntScan": "1",
        "GeneSplicer": "1",
        "NMD": "1",
        "Blosum62": "1",
        "AncestralAllele": "1",
        
        "format": "json"
    }
}

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