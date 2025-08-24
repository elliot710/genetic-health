"""
Genetic data analyzer for processing VCF and CSV genetic data
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
import requests
import asyncio

class GeneticAnalyzer:
    def __init__(self):
        self.variant_cache = {}
        self.gene_info_cache = {}
    
    async def analyze_csv_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze genetic CSV data"""
        analysis = {
            "total_variants": len(df),
            "data_summary": {}
        }
        
        # Check common column patterns
        if 'rsid' in df.columns:
            analysis["rsids_count"] = df['rsid'].nunique()
            analysis["top_rsids"] = df['rsid'].value_counts().head(10).to_dict()
        
        if 'chromosome' in df.columns:
            analysis["chromosomes"] = df['chromosome'].value_counts().to_dict()
        
        if 'position' in df.columns:
            analysis["position_range"] = {
                "min": int(df['position'].min()) if not df['position'].empty else 0,
                "max": int(df['position'].max()) if not df['position'].empty else 0
            }
        
        if 'genotype' in df.columns:
            analysis["genotype_distribution"] = df['genotype'].value_counts().to_dict()
        
        # Look for allele columns
        allele_cols = [col for col in df.columns if 'allele' in col.lower()]
        if allele_cols:
            analysis["allele_columns"] = allele_cols
            for col in allele_cols:
                analysis[f"{col}_distribution"] = df[col].value_counts().head(10).to_dict()
        
        return analysis
    
    async def search_variants(self, gene: Optional[str] = None, chromosome: Optional[str] = None, position: Optional[int] = None) -> List[Dict]:
        """Search for variants by criteria"""
        # This would typically query a database or external API
        # For now, returning mock data based on your existing files
        
        results = []
        
        if gene:
            # Mock gene-based search
            results.append({
                "rsid": f"rs{np.random.randint(1000000, 9999999)}",
                "gene": gene,
                "chromosome": f"chr{np.random.randint(1, 23)}",
                "position": np.random.randint(10000, 250000000),
                "ref_allele": np.random.choice(['A', 'T', 'G', 'C']),
                "alt_allele": np.random.choice(['A', 'T', 'G', 'C']),
                "clinical_significance": np.random.choice(['Benign', 'Likely benign', 'VUS', 'Likely pathogenic', 'Pathogenic'])
            })
        
        return results
    
    async def generate_summary(self, vcf_data: List[Dict], csv_data: Dict) -> Dict[str, Any]:
        """Generate summary of genetic data"""
        summary = {
            "total_variants": len(vcf_data) + csv_data.get('total_variants', 0),
            "data_sources": [],
            "key_findings": []
        }
        
        if vcf_data:
            summary["data_sources"].append("VCF file")
            summary["vcf_variants"] = len(vcf_data)
        
        if csv_data:
            summary["data_sources"].append("CSV file")
            summary["csv_variants"] = csv_data.get('total_variants', 0)
        
        # Add key findings based on data
        summary["key_findings"] = [
            "Genetic data successfully parsed and analyzed",
            f"Found {summary['total_variants']} total variants",
            "Ready for health insights analysis"
        ]
        
        return summary
    
    async def get_gene_info(self, gene_symbol: str) -> Dict[str, Any]:
        """Get gene information from external APIs"""
        if gene_symbol in self.gene_info_cache:
            return self.gene_info_cache[gene_symbol]
        
        try:
            # Example using Ensembl REST API
            url = f"https://rest.ensembl.org/lookup/symbol/homo_sapiens/{gene_symbol}"
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                gene_info = response.json()
                self.gene_info_cache[gene_symbol] = gene_info
                return gene_info
        except Exception as e:
            print(f"Error fetching gene info for {gene_symbol}: {e}")
        
        return {"gene": gene_symbol, "description": "Gene information not available"}
    
    async def annotate_variants(self, variants: List[Dict]) -> List[Dict]:
        """Annotate variants with additional information"""
        annotated = []
        
        for variant in variants:
            # Add mock annotations
            variant_copy = variant.copy()
            variant_copy["annotations"] = {
                "consequence": np.random.choice([
                    "missense_variant", "synonymous_variant", "intronic_variant", 
                    "upstream_gene_variant", "downstream_gene_variant"
                ]),
                "impact": np.random.choice(["HIGH", "MODERATE", "LOW", "MODIFIER"]),
                "clinical_significance": np.random.choice([
                    "Benign", "Likely benign", "VUS", "Likely pathogenic", "Pathogenic"
                ])
            }
            annotated.append(variant_copy)
        
        return annotated