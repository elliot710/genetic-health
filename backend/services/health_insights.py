"""
Health insights analyzer for genetic variants
"""
from typing import Dict, List, Any
import requests
import json

class HealthInsights:
    def __init__(self):
        self.variant_db = self._load_variant_database()
        self.disease_associations = self._load_disease_associations()
    
    def _load_variant_database(self) -> Dict:
        """Load genetic variant database (mock data for demo)"""
        return {
            "rs1815739": {
                "gene": "ACTN3",
                "description": "Alpha-actinin-3 deficiency",
                "health_impact": "Athletic performance",
                "risk_allele": "T",
                "protective_allele": "C",
                "frequency": 0.42,
                "clinical_significance": "Benign"
            },
            "rs1801282": {
                "gene": "PPARG",
                "description": "Peroxisome proliferator-activated receptor gamma",
                "health_impact": "Type 2 diabetes risk",
                "risk_allele": "C",
                "protective_allele": "G", 
                "frequency": 0.15,
                "clinical_significance": "Risk factor"
            },
            "rs429358": {
                "gene": "APOE",
                "description": "Apolipoprotein E",
                "health_impact": "Alzheimer's disease risk",
                "risk_allele": "C",
                "protective_allele": "T",
                "frequency": 0.14,
                "clinical_significance": "Pathogenic"
            }
        }
    
    def _load_disease_associations(self) -> Dict:
        """Load disease association data"""
        return {
            "cardiovascular": {
                "genes": ["APOE", "LDLR", "PCSK9", "ABCG8", "MTHFR", "MTR", "MTRR", "CBS", "COMT"],
                "variants": ["rs429358", "rs7412", "rs11591147", "rs1801133", "rs1801394"]
            },
            "methylation": {
                "genes": ["MTHFR", "MTR", "MTRR", "COMT", "CBS", "AHCY", "BHMT", "GNMT", "MAT1A", "DNMT1", "DNMT3A", "DNMT3B", "PEMT", "CHDH", "SHMT1", "SHMT2", "TYMS", "DHFR", "FOLR1", "FOLR2", "SLC19A1", "SLC46A1"],
                "variants": ["rs1801133", "rs1801131", "rs1801394", "rs4680", "rs234706"]
            },
            "detoxification": {
                "genes": ["CYP1A1", "CYP1A2", "CYP1B1", "CYP2A6", "CYP2B6", "CYP2C8", "CYP2C9", "CYP2C19", "CYP2D6", "CYP2E1", "CYP3A4", "CYP3A5", "CYP3A7", "GSTM1", "GSTT1", "GSTP1", "GSTA1", "GSTA4", "UGT1A1", "UGT1A3", "UGT1A4", "UGT1A6", "UGT2B7", "UGT2B15", "SULT1A1", "SULT1A3", "NAT1", "NAT2", "ABCB1", "ABCC1", "ABCC2", "ABCG2"],
                "variants": ["rs1065852", "rs762551", "rs4244285", "rs1801280", "rs3892097"]
            },
            "diabetes": {
                "genes": ["PPARG", "TCF7L2", "KCNJ11"],
                "variants": ["rs1801282", "rs7903146", "rs5219"]
            },
            "cancer": {
                "genes": ["BRCA1", "BRCA2", "TP53", "MLH1"],
                "variants": ["rs80357906", "rs80359550"]
            },
            "neurological": {
                "genes": ["APOE", "MAPT", "PSEN1"],
                "variants": ["rs429358", "rs10445337"]
            }
        }
    
    async def get_variant_insights(self, rsid: str) -> Dict[str, Any]:
        """Get health insights for a specific variant"""
        if rsid in self.variant_db:
            variant_info = self.variant_db[rsid]
            
            insights = {
                "rsid": rsid,
                "gene": variant_info["gene"],
                "description": variant_info["description"],
                "health_impact": variant_info["health_impact"],
                "clinical_significance": variant_info["clinical_significance"],
                "allele_frequency": variant_info["frequency"],
                "risk_assessment": self._assess_variant_risk(variant_info),
                "recommendations": self._get_variant_recommendations(variant_info)
            }
            
            # Try to get additional info from external APIs
            external_info = await self._fetch_external_variant_info(rsid)
            if external_info:
                insights["external_data"] = external_info
            
            return insights
        else:
            # Try external lookup
            external_info = await self._fetch_external_variant_info(rsid)
            return {
                "rsid": rsid,
                "status": "not_found_locally",
                "external_data": external_info,
                "recommendations": ["Consult with a genetic counselor for interpretation"]
            }
    
    def _assess_variant_risk(self, variant_info: Dict) -> Dict[str, Any]:
        """Assess risk level for a variant"""
        clinical_sig = variant_info.get("clinical_significance", "").lower()
        
        if "pathogenic" in clinical_sig:
            risk_level = "High"
            risk_score = 0.8
        elif "risk factor" in clinical_sig:
            risk_level = "Moderate"
            risk_score = 0.5
        elif "benign" in clinical_sig:
            risk_level = "Low"
            risk_score = 0.2
        else:
            risk_level = "Unknown"
            risk_score = 0.3
        
        return {
            "risk_level": risk_level,
            "risk_score": risk_score,
            "confidence": "Medium" if variant_info.get("frequency", 0) > 0.01 else "Low"
        }
    
    def _get_variant_recommendations(self, variant_info: Dict) -> List[str]:
        """Get recommendations based on variant"""
        recommendations = []
        
        health_impact = variant_info.get("health_impact", "").lower()
        
        if "cardiovascular" in health_impact or "heart" in health_impact:
            recommendations.extend([
                "Regular cardiovascular screening",
                "Maintain healthy cholesterol levels",
                "Exercise regularly and maintain healthy weight"
            ])
        elif "diabetes" in health_impact:
            recommendations.extend([
                "Monitor blood glucose levels regularly",
                "Maintain healthy diet low in processed sugars",
                "Regular physical activity"
            ])
        elif "alzheimer" in health_impact or "neurological" in health_impact:
            recommendations.extend([
                "Cognitive health monitoring",
                "Brain-healthy diet (Mediterranean style)",
                "Regular mental and physical exercise"
            ])
        elif "athletic" in health_impact or "performance" in health_impact:
            recommendations.extend([
                "Optimize training based on genetic profile",
                "Consider sport-specific nutrition strategies"
            ])
        
        recommendations.append("Consult with healthcare provider for personalized advice")
        return recommendations
    
    async def assess_health_risks(self, variants: List[Dict]) -> Dict[str, Any]:
        """Assess overall health risks from variant list"""
        risk_categories = {
            "cardiovascular": {"score": 0, "variants": []},
            "diabetes": {"score": 0, "variants": []},
            "cancer": {"score": 0, "variants": []},
            "neurological": {"score": 0, "variants": []}
        }
        
        for variant in variants:
            variant_id = variant.get("id", "")
            
            # Check against disease associations
            for category, info in self.disease_associations.items():
                if variant_id in info["variants"]:
                    risk_categories[category]["score"] += 0.3
                    risk_categories[category]["variants"].append(variant_id)
        
        # Overall risk assessment
        overall_risk = {
            "total_variants_analyzed": len(variants),
            "risk_categories": risk_categories,
            "overall_score": sum(cat["score"] for cat in risk_categories.values()) / len(risk_categories),
            "recommendations": self._generate_overall_recommendations(risk_categories)
        }
        
        return overall_risk
    
    def _generate_overall_recommendations(self, risk_categories: Dict) -> List[str]:
        """Generate overall health recommendations"""
        recommendations = [
            "Regular health checkups with healthcare provider",
            "Maintain healthy lifestyle with balanced diet and exercise"
        ]
        
        high_risk_categories = [cat for cat, info in risk_categories.items() if info["score"] > 0.5]
        
        if "cardiovascular" in high_risk_categories:
            recommendations.append("Focus on heart-healthy lifestyle choices")
        
        if "diabetes" in high_risk_categories:
            recommendations.append("Monitor blood sugar and maintain healthy weight")
        
        if "cancer" in high_risk_categories:
            recommendations.append("Consider enhanced cancer screening protocols")
        
        if "neurological" in high_risk_categories:
            recommendations.append("Focus on cognitive health and brain fitness")
        
        return recommendations
    
    async def generate_recommendations(self, variants: List[Dict]) -> List[str]:
        """Generate personalized recommendations based on genetic profile"""
        recommendations = [
            "Genetic information should be interpreted by qualified healthcare professionals",
            "Lifestyle factors often have greater impact than genetic predisposition",
            "Regular health monitoring is important regardless of genetic profile"
        ]
        
        # Add specific recommendations based on variants found
        variant_count = len(variants)
        
        if variant_count > 100:
            recommendations.append("Consider comprehensive genetic counseling given extensive variant data")
        
        recommendations.extend([
            "Maintain updated family health history",
            "Stay informed about advances in genetic medicine",
            "Consider sharing genetic information with healthcare team"
        ])
        
        return recommendations
    
    async def _fetch_external_variant_info(self, rsid: str) -> Dict[str, Any]:
        """Fetch variant information from external APIs"""
        try:
            # Example: dbSNP API (mock for demo)
            # In practice, you'd use real APIs like:
            # - NCBI dbSNP
            # - ClinVar
            # - Ensembl Variation
            
            return {
                "source": "External API",
                "status": "mock_data",
                "note": "In production, this would fetch from real genetic databases"
            }
        except Exception as e:
            print(f"Error fetching external data for {rsid}: {e}")
            return {"error": "Unable to fetch external data"}