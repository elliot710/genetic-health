"""
Drug response analyzer for pharmacogenomics
"""
from typing import Dict, List, Any

class DrugResponseAnalyzer:
    def __init__(self):
        self.drug_gene_map = self._load_drug_gene_associations()
        self.pharmacogenes = self._load_pharmacogenes()
    
    def _load_drug_gene_associations(self) -> Dict:
        """Load drug-gene association data"""
        return {
            "CYP2D6": {
                "drugs": [
                    "Codeine", "Tramadol", "Metoprolol", "Fluoxetine", 
                    "Paroxetine", "Risperidone", "Haloperidol"
                ],
                "function": "Drug metabolism",
                "variants": {
                    "rs1065852": {"impact": "Reduced activity", "frequency": 0.20},
                    "rs3892097": {"impact": "No activity", "frequency": 0.07},
                    "rs1135840": {"impact": "Increased activity", "frequency": 0.02}
                }
            },
            "CYP2C19": {
                "drugs": [
                    "Clopidogrel", "Omeprazole", "Escitalopram", 
                    "Sertraline", "Diazepam"
                ],
                "function": "Drug metabolism",
                "variants": {
                    "rs4244285": {"impact": "Reduced activity", "frequency": 0.15},
                    "rs4986893": {"impact": "No activity", "frequency": 0.04},
                    "rs12248560": {"impact": "Increased activity", "frequency": 0.18}
                }
            },
            "DPYD": {
                "drugs": ["5-Fluorouracil", "Capecitabine", "Tegafur"],
                "function": "Drug metabolism",
                "variants": {
                    "rs3918290": {"impact": "Reduced activity", "frequency": 0.01},
                    "rs55886062": {"impact": "Reduced activity", "frequency": 0.003}
                }
            },
            "TPMT": {
                "drugs": ["Azathioprine", "6-Mercaptopurine", "Thioguanine"],
                "function": "Drug metabolism",
                "variants": {
                    "rs1800462": {"impact": "Reduced activity", "frequency": 0.003},
                    "rs1800460": {"impact": "Reduced activity", "frequency": 0.005},
                    "rs1142345": {"impact": "Reduced activity", "frequency": 0.004}
                }
            },
            "SLCO1B1": {
                "drugs": ["Simvastatin", "Atorvastatin", "Rosuvastatin"],
                "function": "Drug transport",
                "variants": {
                    "rs4149056": {"impact": "Reduced transport", "frequency": 0.15}
                }
            }
        }
    
    def _load_pharmacogenes(self) -> List[str]:
        """Load list of important pharmacogenes"""
        return [
            "CYP2D6", "CYP2C19", "CYP2C9", "CYP3A4", "CYP3A5",
            "DPYD", "TPMT", "UGT1A1", "SLCO1B1", "ABCB1",
            "VKORC1", "CFTR", "IFNL3", "HLA-B"
        ]
    
    async def get_drug_response(self, gene: str) -> Dict[str, Any]:
        """Get drug response information for a gene"""
        gene_upper = gene.upper()
        
        if gene_upper in self.drug_gene_map:
            gene_info = self.drug_gene_map[gene_upper]
            
            response = {
                "gene": gene_upper,
                "function": gene_info["function"],
                "affected_drugs": gene_info["drugs"],
                "variants": gene_info["variants"],
                "clinical_recommendations": self._get_gene_recommendations(gene_upper),
                "testing_importance": self._assess_testing_importance(gene_upper)
            }
            
            return response
        else:
            return {
                "gene": gene_upper,
                "status": "not_found",
                "message": f"No pharmacogenomic data available for {gene_upper}",
                "suggestion": "Check if gene name is correct or consult pharmacogenomic databases"
            }
    
    def _get_gene_recommendations(self, gene: str) -> List[str]:
        """Get clinical recommendations for a gene"""
        recommendations = {
            "CYP2D6": [
                "Consider dose adjustments for CYP2D6 metabolized drugs",
                "Monitor for efficacy and adverse effects",
                "Avoid codeine in poor metabolizers"
            ],
            "CYP2C19": [
                "Consider alternative to clopidogrel in poor metabolizers",
                "Adjust proton pump inhibitor dosing based on phenotype",
                "Monitor antidepressant response and side effects"
            ],
            "DPYD": [
                "Screen before 5-fluorouracil treatment",
                "Reduce initial dose in variant carriers",
                "Monitor for severe toxicity"
            ],
            "TPMT": [
                "Test before starting thiopurine therapy",
                "Reduce dose significantly in poor metabolizers",
                "Monitor blood counts closely"
            ],
            "SLCO1B1": [
                "Consider statin dose reduction or alternative",
                "Monitor for myopathy symptoms",
                "Consider rosuvastatin as alternative"
            ]
        }
        
        return recommendations.get(gene, [
            "Consult pharmacogenomic guidelines",
            "Consider genetic testing if planning relevant drug therapy"
        ])
    
    def _assess_testing_importance(self, gene: str) -> str:
        """Assess importance of genetic testing for a gene"""
        high_priority = ["DPYD", "TPMT", "CYP2D6", "CYP2C19"]
        moderate_priority = ["SLCO1B1", "CYP2C9", "VKORC1"]
        
        if gene in high_priority:
            return "High - FDA recommended testing"
        elif gene in moderate_priority:
            return "Moderate - Consider testing if relevant drugs planned"
        else:
            return "Low - May provide useful information"
    
    async def assess_drug_interactions(self, variants: List[Dict]) -> Dict[str, Any]:
        """Assess drug interaction risks from variants"""
        interaction_risks = {
            "high_risk_genes": [],
            "moderate_risk_genes": [],
            "affected_drug_classes": set(),
            "recommendations": []
        }
        
        # Analyze variants for pharmacogenomic significance
        for variant in variants:
            variant_id = variant.get("id", "")
            
            # Check each pharmacogene
            for gene, gene_data in self.drug_gene_map.items():
                if variant_id in gene_data["variants"]:
                    variant_info = gene_data["variants"][variant_id]
                    
                    if "no activity" in variant_info["impact"].lower():
                        interaction_risks["high_risk_genes"].append(gene)
                    elif "reduced activity" in variant_info["impact"].lower():
                        interaction_risks["moderate_risk_genes"].append(gene)
                    
                    # Add affected drug classes
                    interaction_risks["affected_drug_classes"].update(gene_data["drugs"])
        
        # Convert set to list for JSON serialization
        interaction_risks["affected_drug_classes"] = list(interaction_risks["affected_drug_classes"])
        
        # Generate recommendations
        if interaction_risks["high_risk_genes"]:
            interaction_risks["recommendations"].append(
                "High-priority pharmacogenomic testing recommended"
            )
        
        if interaction_risks["moderate_risk_genes"]:
            interaction_risks["recommendations"].append(
                "Consider pharmacogenomic testing for drug optimization"
            )
        
        interaction_risks["recommendations"].extend([
            "Share pharmacogenomic results with all healthcare providers",
            "Keep updated medication list including over-the-counter drugs",
            "Inform prescribers about genetic test results"
        ])
        
        return interaction_risks
    
    async def get_drug_recommendations(self, drug_name: str) -> Dict[str, Any]:
        """Get recommendations for a specific drug"""
        drug_lower = drug_name.lower()
        recommendations = {
            "drug": drug_name,
            "relevant_genes": [],
            "testing_recommended": False,
            "guidance": []
        }
        
        # Find genes that affect this drug
        for gene, gene_data in self.drug_gene_map.items():
            if any(drug_lower in drug.lower() for drug in gene_data["drugs"]):
                recommendations["relevant_genes"].append(gene)
                recommendations["testing_recommended"] = True
        
        if recommendations["relevant_genes"]:
            recommendations["guidance"] = [
                f"Genetic testing for {', '.join(recommendations['relevant_genes'])} recommended",
                "Dose adjustments may be necessary based on genetic results",
                "Monitor for efficacy and adverse effects",
                "Consult pharmacogenomic guidelines"
            ]
        else:
            recommendations["guidance"] = [
                "No specific pharmacogenomic recommendations found",
                "Standard dosing and monitoring apply",
                "Consult prescribing information for guidance"
            ]
        
        return recommendations