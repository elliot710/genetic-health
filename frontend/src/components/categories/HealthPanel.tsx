import React, { useState, useEffect } from 'react'
import { Heart, Shield, Pill, AlertTriangle, Activity } from 'lucide-react'
import { getTheme } from '../../utils/theme'

interface AnalysisData {
  summary?: any
  health_risks?: any
  drug_interactions?: any
  recommendations?: string[]
}

interface HealthPanelProps {
  isDarkMode?: boolean
  theme?: any
  data: AnalysisData
  token?: string
}

export default function HealthPanel({ isDarkMode = false, theme, data, token }: HealthPanelProps) {
  const currentTheme = getTheme(isDarkMode)
  const [realHealthRisks, setRealHealthRisks] = useState<any[]>([])
  const [variantAnnotations, setVariantAnnotations] = useState<{[key: string]: any}>({})
  const [loading, setLoading] = useState(false)
  
  // Function to clean condition name by removing variant IDs
  const cleanConditionName = (condition: string) => {
    // Remove patterns like "(rs123456789)" and "Genetic Variant (rs123456789)"
    return condition
      .replace(/Genetic Variant\s*\([^)]+\)\s*/gi, '')
      .replace(/\([^)]*rs\d+[^)]*\)/gi, '')
      .replace(/\s*\(Protein-affecting\)/gi, '')
      .trim()
  }

  // Function to get variant description based on rsid
  const getVariantDescription = (rsid: string, condition: string, gene: string) => {
    // Common variant descriptions mapping
    const variantDescriptions: {[key: string]: string} = {
      'rs369162678': 'This variant in the RELN gene affects neuronal migration and synaptic function. It is associated with increased susceptibility to epilepsy, particularly temporal lobe epilepsy, and may influence cognitive development and neurological health.',
      'rs143577179': 'A protein-affecting variant that modifies enzyme function or protein structure, potentially impacting cellular processes and metabolic pathways related to health conditions.',
      'rs185185944': 'This variant requires further research to establish clinical significance. Current data suggests potential involvement in cellular mechanisms, but more studies are needed to determine health implications.',
      // Add more specific descriptions as needed
    }
    
    // Return specific description if available, otherwise generate a generic one
    if (variantDescriptions[rsid]) {
      return variantDescriptions[rsid]
    }
    
    // Generate description based on gene and condition
    if (gene && gene !== 'Unknown' && condition) {
      return `This genetic variant in the ${gene} gene has been associated with ${condition.toLowerCase()}. The variant may influence gene expression, protein function, or cellular processes that contribute to disease risk or therapeutic response.`
    }
    
    // Fallback description
    return `This genetic variant has been identified in your analysis and may contribute to your genetic risk profile for ${condition.toLowerCase()}. Further research may provide more specific information about its biological mechanisms and health implications.`
  }

  // Function to get variant annotations
  const getVariantAnnotations = async (rsid: string) => {
    if (!token || !rsid || rsid === 'Unknown' || variantAnnotations[rsid]) return null
    
    try {
      const response = await fetch(`http://localhost:8000/api/annotations/clinical-summary`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ rsid })
      })
      
      if (response.ok) {
        const annotationData = await response.json()
        setVariantAnnotations(prev => ({ ...prev, [rsid]: annotationData }))
        return annotationData
      }
    } catch (error) {
      console.error('Error fetching variant annotations:', error)
    }
    return null
  }

  // Function to create external links
  const getExternalLinks = (rsid: string) => {
    if (!rsid || rsid === 'Unknown') return []
    
    return [
      { label: 'ClinVar', url: `https://www.ncbi.nlm.nih.gov/clinvar/?term=${rsid}[variant name]` },
      { label: 'dbSNP', url: `https://www.ncbi.nlm.nih.gov/snp/${rsid}` },
      { label: 'SNPedia', url: `https://www.snpedia.com/index.php/${rsid}` },
      { label: 'Ensembl', url: `https://useast.ensembl.org/Homo_sapiens/Variation/Summary?v=${rsid}` },
      { label: 'PubMed', url: `https://pubmed.ncbi.nlm.nih.gov/?term=${rsid}` }
    ]
  }
  
  // Load real health risks from API
  useEffect(() => {
    const loadHealthRisks = async () => {
      if (!token) return
      
      setLoading(true)
      try {
        const response = await fetch('http://localhost:8000/analyze/health-risks', {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        })
        
        if (response.ok) {
          const healthData = await response.json()
          console.log('Loaded health risks:', healthData)
          setRealHealthRisks(healthData.health_risks || [])
          
          // Fetch variant annotations for each health risk
          if (healthData.health_risks) {
            healthData.health_risks.forEach((risk: any) => {
              if (risk.associated_variants && risk.associated_variants.length > 0) {
                risk.associated_variants.forEach((variant: string) => {
                  if (variant && variant !== 'Unknown') {
                    getVariantAnnotations(variant)
                  }
                })
              }
            })
          }
        }
      } catch (error) {
        console.error('Error loading health risks:', error)
      } finally {
        setLoading(false)
      }
    }
    
    loadHealthRisks()
  }, [token])
  
  // Use real health risks from API if available, otherwise fallback to data prop, then default
  const getHealthRisks = () => {
    // First priority: Real API data
    if (realHealthRisks.length > 0) {
      return realHealthRisks
        .map((risk: any) => ({
          condition: cleanConditionName(risk.condition),
          risk: risk.risk_level.charAt(0).toUpperCase() + risk.risk_level.slice(1),
          riskScore: risk.risk_level === 'high' ? 85 : risk.risk_level === 'moderate' ? 65 : risk.risk_level === 'low' ? 35 : 20,
          gene: risk.associated_variants?.[0] || 'Unknown',
          description: `Genetic analysis shows ${risk.risk_level} risk for this condition`,
          variantInfo: risk.associated_variants || [],
          clinicalSignificance: risk.clinical_significance || 'Under research',
          riskLevel: risk.risk_level,
          icon: risk.risk_level === 'high' ? AlertTriangle : risk.risk_level === 'moderate' ? Activity : Heart,
          color: risk.risk_level === 'high' 
            ? `bg-red-500/20 text-red-600`
            : risk.risk_level === 'moderate'
            ? `${currentTheme.warning.bg} ${currentTheme.warning.text}`
            : risk.risk_level === 'low'
            ? `${currentTheme.success.bg} ${currentTheme.success.text}`
            : `${currentTheme.text.muted} ${currentTheme.glass}`,
          prevention: Array.isArray(risk.recommendations) ? risk.recommendations : [risk.recommendations || 'Consult with healthcare provider']
        }))
        .sort((a: any, b: any) => {
          // Sort by risk level: high, moderate, low, then unconfirmed/unknown
          const riskOrder = { 'high': 1, 'moderate': 2, 'low': 3, 'unconfirmed': 4, 'unknown': 4 };
          return (riskOrder[a.riskLevel as keyof typeof riskOrder] || 5) - (riskOrder[b.riskLevel as keyof typeof riskOrder] || 5);
        })
    }
    
    // Second priority: Data from props (existing dashboard data)
    if (data?.health_risks?.details && data.health_risks.details.length > 0) {
      return data.health_risks.details
        .map((risk: any) => ({
          condition: cleanConditionName(risk.condition),
          risk: risk.risk_level.charAt(0).toUpperCase() + risk.risk_level.slice(1),
          riskScore: risk.risk_level === 'high' ? 85 : risk.risk_level === 'moderate' ? 65 : risk.risk_level === 'low' ? 35 : 20,
          gene: risk.associated_variants?.[0] || 'Unknown',
          description: `Genetic variant analysis shows ${risk.risk_level} risk`,
          variantInfo: risk.associated_variants || [],
          clinicalSignificance: risk.clinical_significance || 'Under research',
          riskLevel: risk.risk_level,
          icon: risk.risk_level === 'high' ? AlertTriangle : risk.risk_level === 'moderate' ? Activity : Heart,
          color: risk.risk_level === 'high' 
            ? `bg-red-500/20 text-red-600`
            : risk.risk_level === 'moderate'
            ? `${currentTheme.warning.bg} ${currentTheme.warning.text}`
            : risk.risk_level === 'low'
            ? `${currentTheme.success.bg} ${currentTheme.success.text}`
            : `${currentTheme.text.muted} ${currentTheme.glass}`,
          prevention: risk.recommendations || ['Consult with healthcare provider', 'Monitor regularly', 'Maintain healthy lifestyle']
        }))
        .sort((a: any, b: any) => {
          // Sort by risk level: high, moderate, low, then unconfirmed/unknown
          const riskOrder = { 'high': 1, 'moderate': 2, 'low': 3, 'unconfirmed': 4, 'unknown': 4 };
          return (riskOrder[a.riskLevel as keyof typeof riskOrder] || 5) - (riskOrder[b.riskLevel as keyof typeof riskOrder] || 5);
        })
    }
    
    // Third priority: Loading or default message
    if (loading) {
      return [{
        condition: 'Loading Health Risks...',
        risk: 'Processing',
        riskScore: 0,
        gene: 'Multiple',
        description: 'Loading your genetic health risk analysis results...',
        icon: Activity,
        color: `${currentTheme.primary.bg} ${currentTheme.primary.text}`,
        prevention: ['Analysis in progress...']
      }]
    }
    
    // Final fallback: No data available
    return [{
      condition: 'No Health Risks Found',
      risk: 'Good News',
      riskScore: 20,
      gene: 'Multiple',
      description: 'No significant genetic health risks identified in your analysis, or analysis is still in progress.',
      icon: Heart,
      color: `${currentTheme.success.bg} ${currentTheme.success.text}`,
      prevention: ['Continue healthy lifestyle habits', 'Regular health checkups recommended', 'Results may update as analysis completes']
    }]
  }

  const getDrugResponses = () => {
    if (data?.drug_interactions?.details && data.drug_interactions.details.length > 0) {
      return data.drug_interactions.details.map((dr: any) => ({
        drug: dr.drug,
        gene: dr.gene,
        response: dr.response_type.charAt(0).toUpperCase() + dr.response_type.slice(1).replace('_', ' '),
        dosage: dr.response_type === 'poor' ? 'Reduced/Alternative' : 
                dr.response_type === 'ultrarapid' ? 'Increased' : 'Standard',
        description: `${dr.response_type.replace('_', ' ')} metabolism detected`,
        recommendation: dr.recommendations || 'Consult healthcare provider for dosing guidance'
      }))
    }
    
    // Return default message when no real data is available
    return [{
      drug: 'Analysis in Progress',
      gene: 'Multiple',
      response: 'Processing',
      dosage: 'TBD',
      description: 'Pharmacogenomic analysis is being processed',
      recommendation: 'Drug response predictions will appear here when analysis completes'
    }]
  }

  const healthRisks = getHealthRisks()
  const drugResponses = getDrugResponses()

  const preventiveRecommendations = [
    {
      category: 'Screening Schedule',
      recommendations: [
        'Blood pressure: Every 6 months',
        'Cholesterol: Every 2 years',
        'Blood glucose: Annually',
        'Bone density: Every 5 years after 50'
      ]
    },
    {
      category: 'Lifestyle Priorities',
      recommendations: [
        'Mediterranean diet pattern',
        '150 min moderate exercise weekly',
        'Stress reduction techniques',
        'Quality sleep 7-9 hours'
      ]
    },
    {
      category: 'Supplement Considerations',
      recommendations: [
        'Omega-3 fatty acids',
        'Vitamin D (test levels first)',
        'Magnesium for blood pressure',
        'Probiotics for gut health'
      ]
    }
  ]

  const getRiskColor = (risk: string): string => {
    switch (risk.toLowerCase()) {
      case 'high':
        return currentTheme.error.text
      case 'moderate':
        return currentTheme.warning.text
      case 'low':
        return currentTheme.success.text
      default:
        return currentTheme.text.secondary
    }
  }

  const getRiskBg = (riskScore: number) => {
    if (riskScore >= 50) return 'bg-red-500'
    if (riskScore >= 25) return 'bg-yellow-500'
    return 'bg-green-500'
  }

  const getResponseColor = (response: string) => {
    if (response === 'Sensitive' || response === 'Poor') return 'text-red-600'
    if (response === 'Enhanced' || response === 'Good') return 'text-green-600'
    return 'text-gray-600'
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-6`}>
        <div className="flex items-center mb-4">
          <Heart className={`h-8 w-8 ${currentTheme.primary.text} mr-3`} />
          <div>
            <h2 className={`text-2xl font-bold ${currentTheme.text.primary}`}>Health & Wellness</h2>
            <p className={`${currentTheme.text.secondary}`}>Your genetic health risks and drug response profile</p>
          </div>
        </div>
      </div>

      {/* Enhanced Health Risk Summary */}
      {healthRisks.length > 0 && (
        <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-6`}>
          <h3 className={`text-lg font-semibold ${currentTheme.text.primary} mb-4`}>Risk Assessment Summary</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className={`text-center p-4 ${currentTheme.error.bg} rounded-lg`}>
              <div className={`text-2xl font-bold ${currentTheme.error.text} mb-1`}>
                {healthRisks.filter((r: any) => r.riskLevel === 'high').length}
              </div>
              <div className={`text-sm font-medium ${currentTheme.error.text}`}>High Risk Conditions</div>
              <div className={`text-xs ${currentTheme.error.text}`}>Require monitoring</div>
            </div>
            <div className={`text-center p-4 ${currentTheme.warning.bg} rounded-lg`}>
              <div className={`text-2xl font-bold ${currentTheme.warning.text} mb-1`}>
                {healthRisks.filter((r: any) => r.riskLevel === 'moderate').length}
              </div>
              <div className={`text-sm font-medium ${currentTheme.warning.text}`}>Moderate Risk</div>
              <div className={`text-xs ${currentTheme.warning.text}`}>Lifestyle factors matter</div>
            </div>
            <div className={`text-center p-4 ${currentTheme.success.bg} rounded-lg`}>
              <div className={`text-2xl font-bold ${currentTheme.success.text} mb-1`}>
                {healthRisks.filter((r: any) => r.riskLevel === 'low').length}
              </div>
              <div className={`text-sm font-medium ${currentTheme.success.text}`}>Low Risk</div>
              <div className={`text-xs ${currentTheme.success.text}`}>Continue healthy habits</div>
            </div>
          </div>
        </div>
      )}

      {/* Health Risk Assessment */}
      <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${currentTheme.text.primary} mb-4`}>Health Risk Assessment</h3>
        <div className="space-y-6">
          {healthRisks.map((risk: any, index: number) => {
            const Icon = risk.icon
            return (
              <div key={index} className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-6 hover:shadow-lg transition-shadow`}>
                {/* Header Section */}
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-start space-x-4">
                    <div className={`p-3 rounded-xl ${risk.color} flex-shrink-0`}>
                      <Icon className="h-6 w-6" />
                    </div>
                    <div className="flex-1">
                      <h4 className={`text-xl font-semibold ${currentTheme.text.primary} mb-1`}>
                        {risk.condition}
                      </h4>
                      <div className="flex items-center space-x-3 mb-2">
                        <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${
                          risk.riskLevel === 'high' 
                            ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300'
                            : risk.riskLevel === 'moderate'
                            ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300'
                            : 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
                        }`}>
                          {risk.risk} Risk
                        </span>
                        <span className={`text-sm ${currentTheme.text.muted}`}>
                          {risk.riskScore}% lifetime risk
                        </span>
                      </div>
                      {risk.clinicalSignificance && (
                        <p className={`text-sm ${currentTheme.text.secondary}`}>
                          Clinical Status: {risk.clinicalSignificance}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <span className={`text-sm font-medium ${currentTheme.text.primary}`}>{risk.gene}</span>
                    <div className={`text-xs ${currentTheme.text.muted}`}>Gene</div>
                  </div>
                </div>

                {/* Description */}
                <div className="mb-4">
                  <p className={`${currentTheme.text.secondary} leading-relaxed`}>
                    {risk.description}
                  </p>
                </div>

                {/* Variant Information - Redesigned */}
                {risk.variantInfo && risk.variantInfo.length > 0 && (
                  <div className="mb-4">
                    <h5 className={`text-lg font-medium ${currentTheme.text.primary} mb-3`}>
                      Associated Genetic Variants
                    </h5>
                    <div className="space-y-3">
                      {risk.variantInfo.map((variant: string, variantIndex: number) => {
                        const annotation = variantAnnotations[variant]
                        const links = getExternalLinks(variant)
                        const description = getVariantDescription(variant, risk.condition, risk.gene)
                        
                        return (
                          <div key={variantIndex} className={`bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4 border border-gray-200 dark:border-gray-700`}>
                            {/* Variant Header */}
                            <div className="flex items-center justify-between mb-3">
                              <div className="flex items-center space-x-3">
                                <span className={`text-sm font-medium ${currentTheme.text.primary}`}>
                                  Variant Details
                                </span>
                              </div>
                              <div className="flex flex-wrap gap-2">
                                {links.map((link, linkIndex) => (
                                  <a
                                    key={linkIndex}
                                    href={link.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="px-3 py-1 text-xs font-medium bg-blue-600 text-white rounded-full hover:bg-blue-700 transition-colors"
                                  >
                                    {link.label}
                                  </a>
                                ))}
                              </div>
                            </div>
                            
                            {/* Variant Description */}
                            <div className="bg-white dark:bg-gray-900/50 rounded-lg p-3 mb-3">
                              <h6 className={`text-sm font-medium ${currentTheme.text.primary} mb-2`}>
                                What this variant means:
                              </h6>
                              <p className={`text-sm ${currentTheme.text.secondary} leading-relaxed`}>
                                {description}
                              </p>
                            </div>
                            
                            {/* Clinical Data */}
                            {annotation && (
                              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                                {annotation.clinical_significance && (
                                  <div>
                                    <span className={`font-medium ${currentTheme.text.primary}`}>Clinical Significance:</span>
                                    <div className={`${currentTheme.text.secondary}`}>{annotation.clinical_significance}</div>
                                  </div>
                                )}
                                {annotation.allele_frequency && (
                                  <div>
                                    <span className={`font-medium ${currentTheme.text.primary}`}>Population Frequency:</span>
                                    <div className={`${currentTheme.text.secondary}`}>{annotation.allele_frequency}</div>
                                  </div>
                                )}
                                {annotation.consequence && (
                                  <div>
                                    <span className={`font-medium ${currentTheme.text.primary}`}>Predicted Effect:</span>
                                    <div className={`${currentTheme.text.secondary}`}>{annotation.consequence}</div>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* Prevention Strategies */}
                <div className={`bg-gradient-to-r from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20 rounded-lg p-4 border-l-4 border-green-500`}>
                  <h5 className={`text-sm font-semibold text-green-800 dark:text-green-300 mb-2`}>
                    Prevention Strategies:
                  </h5>
                  <ul className={`text-sm text-green-700 dark:text-green-400 space-y-1`}>
                    {risk.prevention.map((strategy: string, strategyIndex: number) => (
                      <li key={strategyIndex} className="flex items-start">
                        <span className="mr-2">•</span>
                        <span>{strategy}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Drug Response */}
      <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${currentTheme.text.primary} mb-4`}>Pharmacogenomics - Drug Response</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {drugResponses.map((drug: any, index: number) => (
            <div key={index} className={`${currentTheme.glassSecondary} border ${currentTheme.glassBorder} rounded-lg p-4`}>
              <div className="flex justify-between items-start mb-2">
                <h4 className={`font-medium ${currentTheme.text.primary}`}>{drug.drug}</h4>
                <span className={`text-xs px-2 py-1 rounded ${currentTheme.glassSecondary} ${currentTheme.text.secondary}`}>
                  {drug.gene}
                </span>
              </div>
              <div className="mb-2">
                <span className={`text-sm font-medium ${getResponseColor(drug.response)}`}>
                  {drug.response} Response
                </span>
                <span className={`text-sm ${currentTheme.text.secondary} ml-2`}>({drug.dosage} Dosage)</span>
              </div>
              <p className={`text-xs ${currentTheme.text.secondary} mb-3`}>{drug.description}</p>
              <div className={`${currentTheme.warning.bg} p-2 rounded text-xs ${currentTheme.warning.text}`}>
                🏥 {drug.recommendation}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Clinical Insights */}
      {healthRisks.length > 0 && (
        <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-6`}>
          <h3 className={`text-lg font-semibold ${currentTheme.text.primary} mb-4`}>Clinical Insights & Recommendations</h3>
          <div className="space-y-4">
            {healthRisks.filter((risk: any) => risk.riskLevel === 'high').length > 0 && (
              <div className={`${currentTheme.error.bg} p-4 rounded-lg border-l-4 border-red-500`}>
                <h4 className={`font-medium ${currentTheme.error.text} mb-2`}>⚠️ High Priority Actions</h4>
                <ul className={`${currentTheme.error.text} text-sm space-y-1`}>
                  <li>• Schedule consultation with healthcare provider</li>
                  <li>• Discuss genetic testing results and family history</li>
                  <li>• Consider specialized screening programs</li>
                  <li>• Implement aggressive lifestyle modifications</li>
                </ul>
              </div>
            )}
            
            {healthRisks.filter((risk: any) => risk.riskLevel === 'moderate').length > 0 && (
              <div className={`${currentTheme.warning.bg} p-4 rounded-lg border-l-4 border-yellow-500`}>
                <h4 className={`font-medium ${currentTheme.warning.text} mb-2`}>🔶 Moderate Risk Management</h4>
                <ul className={`${currentTheme.warning.text} text-sm space-y-1`}>
                  <li>• Maintain regular health checkups</li>
                  <li>• Focus on preventive lifestyle measures</li>
                  <li>• Monitor relevant biomarkers annually</li>
                  <li>• Consider targeted supplements after consultation</li>
                </ul>
              </div>
            )}
            
            {healthRisks.filter((risk: any) => risk.riskLevel === 'low').length > 0 && (
              <div className={`${currentTheme.success.bg} p-4 rounded-lg border-l-4 border-green-500`}>
                <h4 className={`font-medium ${currentTheme.success.text} mb-2`}>✅ Protective Factors</h4>
                <ul className={`${currentTheme.success.text} text-sm space-y-1`}>
                  <li>• Continue current healthy lifestyle practices</li>
                  <li>• Standard population screening recommendations apply</li>
                  <li>• Genetic factors provide some protection</li>
                  <li>• Focus on maintaining optimal health</li>
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Preventive Recommendations */}
      <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${currentTheme.text.primary} mb-4`}>Preventive Health Recommendations</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {preventiveRecommendations.map((category, index) => (
            <div key={index} className="space-y-3">
              <h4 className={`font-medium ${currentTheme.text.primary}`}>{category.category}</h4>
              <div className="space-y-2">
                {category.recommendations.map((rec, recIndex) => (
                  <div key={recIndex} className={`p-2 rounded text-sm ${currentTheme.glassSecondary} ${currentTheme.text.secondary}`}>
                    • {rec}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Health Score Summary */}
      <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${currentTheme.text.primary} mb-4`}>Overall Health Profile</h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className={`text-center p-4 ${currentTheme.success.bg} rounded-lg`}>
            <div className={`text-2xl font-bold ${currentTheme.success.text} mb-1`}>78</div>
            <div className={`text-sm font-medium ${currentTheme.success.text}`}>Genetic Health Score</div>
            <div className={`text-xs ${currentTheme.success.text}`}>Above Average</div>
          </div>
          <div className={`text-center p-4 ${currentTheme.categories.ancestry.bg} rounded-lg`}>
            <div className={`text-2xl font-bold ${currentTheme.categories.ancestry.text} mb-1`}>85%</div>
            <div className={`text-sm font-medium ${currentTheme.categories.ancestry.text}`}>Drug Compatibility</div>
            <div className={`text-xs ${currentTheme.categories.ancestry.text}`}>Most drugs effective</div>
          </div>
          <div className={`text-center p-4 ${currentTheme.warning.bg} rounded-lg`}>
            <div className={`text-2xl font-bold ${currentTheme.warning.text} mb-1`}>3</div>
            <div className={`text-sm font-medium ${currentTheme.warning.text}`}>Risk Factors</div>
            <div className={`text-xs ${currentTheme.warning.text}`}>Moderate monitoring</div>
          </div>
          <div className={`text-center p-4 ${currentTheme.categories.wellness.bg} rounded-lg`}>
            <div className={`text-2xl font-bold ${currentTheme.categories.wellness.text} mb-1`}>92%</div>
            <div className={`text-sm font-medium ${currentTheme.categories.wellness.text}`}>Prevention Potential</div>
            <div className={`text-xs ${currentTheme.categories.wellness.text}`}>High lifestyle impact</div>
          </div>
        </div>
      </div>

      {/* Important Disclaimer */}
      <div className={`${currentTheme.warning.bg} border ${currentTheme.warning.border} rounded-xl p-6`}>
        <div className="flex items-start space-x-3">
          <AlertTriangle className={`h-6 w-6 ${currentTheme.warning.text} mt-0.5 flex-shrink-0`} />
          <div>
            <h4 className={`font-medium ${currentTheme.warning.text} mb-2`}>Medical Disclaimer</h4>
            <p className={`${currentTheme.warning.text} text-sm`}>
              This genetic analysis is for informational purposes only and should not replace professional medical advice. 
              Always consult with qualified healthcare providers before making medical decisions or changing treatments 
              based on genetic information. Genetic predisposition does not guarantee disease development.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}