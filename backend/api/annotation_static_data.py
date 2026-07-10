SUPPORTED_APIS = {
    "apis": [
        {
            "name": "NCBI E-utilities",
            "url": "https://eutils.ncbi.nlm.nih.gov",
            "description": "Unified access to NCBI databases including ClinVar and PubMed",
            "data_types": ["clinical_significance", "literature_search", "variant_submissions"],
            "methods": ["ESearch", "EFetch"],
            "rate_limit": "3 requests per second",
            "free": True,
        },
        {
            "name": "LitVar API",
            "url": "https://www.ncbi.nlm.nih.gov/research/litvar2-api",
            "description": "Literature variants - connecting genomic variants to publications",
            "data_types": ["variant_literature", "pmids", "variant_gene_disease_drug_relations"],
            "rate_limit": "10 requests per second",
            "free": True,
        },
        {
            "name": "SNPedia MediaWiki API",
            "url": "https://bots.snpedia.com/api.php",
            "description": "Community-curated genetic variant annotations",
            "data_types": ["magnitude", "summary", "frequency", "genotype_interpretations"],
            "rate_limit": "No strict limit",
            "free": True,
        },
        {
            "name": "Ensembl REST API",
            "url": "https://rest.ensembl.org",
            "description": "Comprehensive genomic annotations and variant consequences",
            "data_types": ["variant_info", "consequences", "population_frequencies", "vep_annotations"],
            "rate_limit": "15 requests per second",
            "free": True,
        },
        {
            "name": "ClinVar (via NCBI E-utilities)",
            "url": "https://eutils.ncbi.nlm.nih.gov",
            "description": "Clinical variant interpretations and submissions",
            "data_types": ["clinical_significance", "pathogenicity", "variant_submissions", "conditions"],
            "rate_limit": "3 requests per second",
            "free": True,
        },
        {
            "name": "ClinPGx API",
            "url": "https://api.clinpgx.org",
            "description": "Pharmacogenomic annotations and drug interactions (formerly PharmGKB)",
            "data_types": ["drug_response", "dosing_guidelines", "clinical_annotations", "phenotypes"],
            "rate_limit": "2 requests per second",
            "free": True,
        },
    ],
    "new_features": [
        "NCBI E-utilities integration for comprehensive database access",
        "LitVar API for variant-literature connections",
        "SNPedia MediaWiki API for community annotations",
        "Enhanced ClinVar data with XML parsing",
        "Improved rate limiting and error handling",
        "Clinical summary aggregation across all sources",
    ],
    "usage_examples": [
        {
            "endpoint": "/api/annotations/variant",
            "example": {"rsid": "rs5443", "gene": "GNB3"},
            "response_data": "Ensembl + ClinVar + SNPedia + LitVar annotations",
        },
        {
            "endpoint": "/api/annotations/clinical-summary",
            "example": {"rsid": "rs5443", "gene": "GNB3"},
            "response_data": "Unified clinical interpretation with recommendations",
        },
        {
            "endpoint": "/api/annotations/literature",
            "example": {"rsid": "rs5443"},
            "response_data": "PubMed publications mentioning the variant",
        },
    ],
}


ANNOTATION_EXAMPLES = {
    "cardiovascular": [
        {
            "rsid": "rs5443",
            "gene": "GNB3",
            "variant": "c.825C>T",
            "drugs": ["sildenafil", "antihypertensives"],
            "clinical_significance": "drug response - efficacy variation",
            "frequency": "46.124%",
            "available_data": ["Ensembl", "ClinVar", "SNPedia", "Literature"],
        }
    ],
    "oncology": [
        {
            "rsid": "rs11615",
            "gene": "ERCC1",
            "variant": "c.354T>C",
            "drugs": ["cisplatin", "carboplatin", "oxaliplatin"],
            "clinical_significance": "chemotherapy response - efficacy and toxicity",
            "frequency": "57.54%",
            "available_data": ["Ensembl", "ClinVar", "Literature"],
        }
    ],
    "metabolism": [
        {
            "rsid": "rs1045642",
            "gene": "ABCB1",
            "variant": "c.3435C>T",
            "drugs": ["digoxin", "fexofenadine", "dabigatran"],
            "clinical_significance": "drug transport - P-glycoprotein substrate clearance",
            "frequency": "40-60%",
            "available_data": ["Ensembl", "ClinVar", "ClinPGx"],
        }
    ],
    "high_impact": [
        {
            "rsid": "rs121909001",
            "gene": "CFTR",
            "variant": "c.1521_1523delCTT",
            "condition": "Cystic fibrosis",
            "clinical_significance": "pathogenic",
            "available_data": ["ClinVar", "Literature", "Ensembl"],
        }
    ],
}
