'use client'

import { useState } from 'react'
import { Search, Loader2, AlertCircle, CheckCircle, Info, ExternalLink, AlertTriangle } from 'lucide-react'

interface VariantSearchProps {
  token?: string
  isDarkMode?: boolean
  theme?: any
}

export default function VariantSearch({ token, isDarkMode = false, theme }: VariantSearchProps) {
  // Default theme if not provided
  const defaultTheme = {
    glass: isDarkMode ? 'bg-slate-800/40 backdrop-blur-xl' : 'bg-white/40 backdrop-blur-xl',
    glassBorder: isDarkMode ? 'border-slate-700/50' : 'border-gray-200/30',
    text: {
      primary: isDarkMode ? 'text-white' : 'text-slate-900',
      secondary: isDarkMode ? 'text-slate-300' : 'text-slate-600',
      muted: isDarkMode ? 'text-slate-400' : 'text-slate-500'
    }
  }
  
  const currentTheme = theme || defaultTheme
  const [searchTerm, setSearchTerm] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [results, setResults] = useState<any>(null)
  const [error, setError] = useState('')

  const searchVariant = async () => {
    if (!searchTerm.trim()) {
      setError('Please enter a variant ID (e.g., rs53576)')
      return
    }

    setIsLoading(true)
    setError('')
    setResults(null)

    try {
      // Call the new comprehensive variant lookup endpoint
      const response = await fetch('http://localhost:8000/api/variants/lookup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token && { 'Authorization': `Bearer ${token}` })
        },
        body: JSON.stringify({ 
          variant_id: searchTerm.trim(),
          include_literature: true,
          include_pharmgkb: true
        })
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to search for variant')
      }

      const data = await response.json()
      setResults(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed')
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      searchVariant()
    }
  }

  return (
    <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-2xl shadow-xl p-6`}>
      <div className="flex items-center space-x-3 mb-6">
        <div className="p-2 bg-gradient-to-r from-indigo-500 to-purple-500 rounded-xl">
          <Search className="h-5 w-5 text-white" />
        </div>
        <h3 className={`text-xl font-bold ${currentTheme.text.primary}`}>
          Variant Lookup
        </h3>
      </div>

      {/* Search Input */}
      <div className="flex space-x-3 mb-6">
        <div className="flex-1">
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Enter variant ID (e.g., rs53576, rs1695, rs429358)"
            className={`w-full px-4 py-3 rounded-xl border ${currentTheme.glassBorder} focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent ${currentTheme.glass} backdrop-blur-sm ${currentTheme.text.primary} placeholder-gray-400`}
          />
        </div>
        <button
          onClick={searchVariant}
          disabled={isLoading}
          className="px-6 py-3 bg-gradient-to-r from-indigo-500/80 to-purple-600/80 text-white rounded-xl hover:from-purple-600/80 hover:to-indigo-500/80 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2 backdrop-blur-xl border border-white/20 shadow-lg"
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Search className="h-4 w-4" />
          )}
          <span>{isLoading ? 'Searching...' : 'Search'}</span>
        </button>
      </div>

      {/* Error State */}
      {error && (
        <div className={`mb-6 p-4 ${isDarkMode ? 'bg-red-500/20 border-red-500/30' : 'bg-red-50 border-red-200'} border rounded-xl flex items-start space-x-3`}>
          <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div className={`${isDarkMode ? 'text-red-200' : 'text-red-700'} text-sm`}>{error}</div>
        </div>
      )}

      {/* Results */}
      {results && (
        <div className="space-y-4">
          {/* Basic Info */}
          <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-4`}>
            <h4 className={`font-bold ${currentTheme.text.primary} mb-3 flex items-center space-x-2`}>
              <CheckCircle className="h-4 w-4 text-green-600" />
              <span>Variant Information</span>
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              <div>
                <span className={currentTheme.text.secondary}>Variant ID:</span>
                <span className={`ml-2 font-medium ${currentTheme.text.primary}`}>{results.variant_id || searchTerm}</span>
              </div>
              <div>
                <span className={currentTheme.text.secondary}>Source:</span>
                <span className={`ml-2 font-medium ${currentTheme.text.primary}`}>{results.source || 'Multiple databases'}</span>
              </div>
              {results.basic_info?.name && (
                <div>
                  <span className={currentTheme.text.secondary}>Name:</span>
                  <span className={`ml-2 font-medium ${currentTheme.text.primary}`}>{results.basic_info.name}</span>
                </div>
              )}
              {results.basic_info?.most_severe_consequence && (
                <div>
                  <span className={currentTheme.text.secondary}>Consequence:</span>
                  <span className={`ml-2 font-medium ${currentTheme.text.primary}`}>{results.basic_info.most_severe_consequence}</span>
                </div>
              )}
              {results.population_data?.minor_allele && (
                <div>
                  <span className={currentTheme.text.secondary}>Minor Allele:</span>
                  <span className={`ml-2 font-medium ${currentTheme.text.primary}`}>{results.population_data.minor_allele}</span>
                </div>
              )}
              {results.population_data?.minor_allele_frequency && (
                <div>
                  <span className={currentTheme.text.secondary}>MAF:</span>
                  <span className={`ml-2 font-medium ${currentTheme.text.primary}`}>{(results.population_data.minor_allele_frequency * 100).toFixed(2)}%</span>
                </div>
              )}
            </div>
          </div>

          {/* Clinical Significance */}
          {results.clinical_significance && results.clinical_significance.length > 0 && (
            <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-4`}>
              <h4 className={`font-bold ${currentTheme.text.primary} mb-3 flex items-center space-x-2`}>
                <AlertTriangle className="h-4 w-4 text-amber-600" />
                <span>Clinical Significance</span>
              </h4>
              <div className="space-y-2">
                {results.clinical_significance.map((sig: string, index: number) => (
                  <div key={index} className="flex items-center space-x-2">
                    <div className={`w-2 h-2 rounded-full ${
                      sig.toLowerCase().includes('pathogenic') ? 'bg-red-500' :
                      sig.toLowerCase().includes('risk') ? 'bg-orange-500' :
                      sig.toLowerCase().includes('benign') ? 'bg-green-500' :
                      'bg-gray-400'
                    }`} />
                    <span className={`text-sm ${currentTheme.text.secondary}`}>{sig}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* PharmGKB Information */}
          {results.pharmacogenomics?.found && (
            <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-4`}>
              <h4 className={`font-bold ${currentTheme.text.primary} mb-3 flex items-center space-x-2`}>
                <Info className="h-4 w-4 text-purple-600" />
                <span>Pharmacogenomic Data</span>
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                {results.pharmacogenomics.gene && (
                  <div>
                    <span className={currentTheme.text.secondary}>Gene:</span>
                    <span className={`ml-2 font-medium ${currentTheme.text.primary}`}>{results.pharmacogenomics.gene}</span>
                  </div>
                )}
                {results.pharmacogenomics.clinical_significance && (
                  <div>
                    <span className={currentTheme.text.secondary}>Clinical Significance:</span>
                    <span className={`ml-2 font-medium ${currentTheme.text.primary}`}>{results.pharmacogenomics.clinical_significance}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Literature Information */}
          {results.literature?.total_publications !== undefined && (
            <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-4`}>
              <h4 className={`font-bold ${currentTheme.text.primary} mb-3 flex items-center space-x-2`}>
                <Info className="h-4 w-4 text-blue-600" />
                <span>Literature Evidence</span>
              </h4>
              <div className="text-sm">
                <span className={currentTheme.text.secondary}>Publications found:</span>
                <span className={`ml-2 font-medium ${currentTheme.text.primary}`}>
                  {results.literature.total_publications} {results.literature.total_publications === 1 ? 'publication' : 'publications'}
                </span>
                {results.literature.source && (
                  <div className="mt-1">
                    <span className={currentTheme.text.secondary}>Source:</span>
                    <span className={`ml-2 text-sm ${currentTheme.text.primary}`}>{results.literature.source}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* External Links */}
          <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-4`}>
            <h4 className={`font-bold ${currentTheme.text.primary} mb-3 flex items-center space-x-2`}>
              <ExternalLink className="h-4 w-4 text-purple-600" />
              <span>External Resources</span>
            </h4>
            <div className="flex flex-wrap gap-2">
              <a
                href={`https://www.ncbi.nlm.nih.gov/snp/${searchTerm}`}
                target="_blank"
                rel="noopener noreferrer"
                className={`px-3 py-2 ${isDarkMode ? 'bg-blue-500/20 hover:bg-blue-500/30 text-blue-300' : 'bg-blue-100 hover:bg-blue-200 text-blue-800'} rounded-lg text-xs font-medium transition-colors`}
              >
                dbSNP
              </a>
              <a
                href={`https://www.ensembl.org/Homo_sapiens/Variation/Summary?v=${searchTerm}`}
                target="_blank"
                rel="noopener noreferrer"
                className={`px-3 py-2 ${isDarkMode ? 'bg-green-500/20 hover:bg-green-500/30 text-green-300' : 'bg-green-100 hover:bg-green-200 text-green-800'} rounded-lg text-xs font-medium transition-colors`}
              >
                Ensembl
              </a>
              <a
                href={`https://www.pharmgkb.org/variant/${searchTerm}`}
                target="_blank"
                rel="noopener noreferrer"
                className={`px-3 py-2 ${isDarkMode ? 'bg-purple-500/20 hover:bg-purple-500/30 text-purple-300' : 'bg-purple-100 hover:bg-purple-200 text-purple-800'} rounded-lg text-xs font-medium transition-colors`}
              >
                PharmGKB
              </a>
              <a
                href={`https://www.ncbi.nlm.nih.gov/clinvar/?term=${searchTerm}`}
                target="_blank"
                rel="noopener noreferrer"
                className={`px-3 py-2 ${isDarkMode ? 'bg-red-500/20 hover:bg-red-500/30 text-red-300' : 'bg-red-100 hover:bg-red-200 text-red-800'} rounded-lg text-xs font-medium transition-colors`}
              >
                ClinVar
              </a>
              <a
                href={`https://www.snpedia.com/index.php/${searchTerm}`}
                target="_blank"
                rel="noopener noreferrer"
                className={`px-3 py-2 ${isDarkMode ? 'bg-orange-500/20 hover:bg-orange-500/30 text-orange-300' : 'bg-orange-100 hover:bg-orange-200 text-orange-800'} rounded-lg text-xs font-medium transition-colors`}
              >
                SNPedia
              </a>
            </div>
          </div>
        </div>
      )}

      {/* No Results or Not Found */}
      {results && !results.found && (
        <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-6 text-center`}>
          <AlertCircle className={`h-12 w-12 mx-auto mb-4 ${currentTheme.text.secondary} opacity-50`} />
          <h3 className={`text-lg font-semibold ${currentTheme.text.primary} mb-2`}>Variant Not Found</h3>
          <p className={currentTheme.text.secondary}>
            No information found for variant <span className="font-mono">{results.variant_id}</span> in our databases.
          </p>
          <p className={`${currentTheme.text.secondary} text-sm mt-2`}>
            Try checking the variant ID spelling or use the external links below to search directly.
          </p>
          
          {/* External Links for not found variants */}
          <div className="mt-4">
            <div className="flex flex-wrap gap-2 justify-center">
              <a
                href={`https://www.ncbi.nlm.nih.gov/snp/${searchTerm}`}
                target="_blank"
                rel="noopener noreferrer"
                className={`px-3 py-2 ${isDarkMode ? 'bg-blue-500/20 hover:bg-blue-500/30 text-blue-300' : 'bg-blue-100 hover:bg-blue-200 text-blue-800'} rounded-lg text-xs font-medium transition-colors`}
              >
                Search dbSNP
              </a>
              <a
                href={`https://www.ensembl.org/Homo_sapiens/Variation/Summary?v=${searchTerm}`}
                target="_blank"
                rel="noopener noreferrer"
                className={`px-3 py-2 ${isDarkMode ? 'bg-green-500/20 hover:bg-green-500/30 text-green-300' : 'bg-green-100 hover:bg-green-200 text-green-800'} rounded-lg text-xs font-medium transition-colors`}
              >
                Search Ensembl
              </a>
            </div>
          </div>
        </div>
      )}

      {/* Initial Help Text */}
      {results === null && !isLoading && !error && (
        <div className="text-center py-8">
          <Search className={`h-12 w-12 mx-auto mb-4 ${currentTheme.text.secondary} opacity-50`} />
          <h3 className={`text-lg font-semibold ${currentTheme.text.primary} mb-2`}>Search Genetic Variants</h3>
          <p className={currentTheme.text.secondary}>Enter a variant ID to search for genetic information</p>
          <div className={`text-sm mt-4 ${currentTheme.text.secondary}`}>
            <p className="mb-2">Examples:</p>
            <div className="flex flex-wrap gap-2 justify-center">
              <code className={`px-2 py-1 ${currentTheme.glass} border ${currentTheme.glassBorder} rounded text-xs`}>rs53576</code>
              <code className={`px-2 py-1 ${currentTheme.glass} border ${currentTheme.glassBorder} rounded text-xs`}>rs1695</code>
              <code className={`px-2 py-1 ${currentTheme.glass} border ${currentTheme.glassBorder} rounded text-xs`}>rs429358</code>
              <code className={`px-2 py-1 ${currentTheme.glass} border ${currentTheme.glassBorder} rounded text-xs`}>rs12202969</code>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}