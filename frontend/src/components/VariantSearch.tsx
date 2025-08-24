'use client'

import { useState } from 'react'
import { Search, Loader2, AlertCircle, CheckCircle, Info, ExternalLink, AlertTriangle } from 'lucide-react'

interface VariantSearchProps {
  token?: string
}

export default function VariantSearch({ token }: VariantSearchProps) {
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
      // Call the backend search endpoint
      const response = await fetch('http://localhost:8000/upload/search-variant', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token && { 'Authorization': `Bearer ${token}` })
        },
        body: JSON.stringify({ variant_id: searchTerm.trim() })
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
    <div className="bg-white/70 backdrop-blur-xl rounded-2xl shadow-xl border border-white/30 p-6">
      <div className="flex items-center space-x-3 mb-6">
        <div className="p-2 bg-gradient-to-r from-indigo-500 to-purple-500 rounded-xl">
          <Search className="h-5 w-5 text-white" />
        </div>
        <h3 className="text-xl font-bold bg-gradient-to-r from-gray-900 to-gray-600 bg-clip-text text-transparent">
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
            className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white/80 backdrop-blur-sm"
          />
        </div>
        <button
          onClick={searchVariant}
          disabled={isLoading}
          className="px-6 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-xl hover:from-purple-600 hover:to-indigo-500 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
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
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl flex items-start space-x-3">
          <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div className="text-red-700 text-sm">{error}</div>
        </div>
      )}

      {/* Results */}
      {results && (
        <div className="space-y-4">
          {/* Basic Info */}
          <div className="bg-white/80 rounded-xl p-4">
            <h4 className="font-bold text-gray-900 mb-3 flex items-center space-x-2">
              <CheckCircle className="h-4 w-4 text-green-600" />
              <span>Variant Information</span>
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-600">Variant ID:</span>
                <span className="ml-2 font-medium text-gray-900">{results.rsid || searchTerm}</span>
              </div>
              <div>
                <span className="text-gray-600">Source:</span>
                <span className="ml-2 font-medium text-gray-900">{results.source || 'Multiple databases'}</span>
              </div>
              {results.name && (
                <div>
                  <span className="text-gray-600">Name:</span>
                  <span className="ml-2 font-medium text-gray-900">{results.name}</span>
                </div>
              )}
              {results.most_severe_consequence && (
                <div>
                  <span className="text-gray-600">Consequence:</span>
                  <span className="ml-2 font-medium text-gray-900">{results.most_severe_consequence}</span>
                </div>
              )}
            </div>
          </div>

          {/* Clinical Significance */}
          {results.clinical_significance && results.clinical_significance.length > 0 && (
            <div className="bg-white/80 rounded-xl p-4">
              <h4 className="font-bold text-gray-900 mb-3 flex items-center space-x-2">
                <AlertTriangle className="h-4 w-4 text-amber-600" />
                <span>Clinical Significance</span>
              </h4>
              <div className="space-y-2">
                {results.clinical_significance.map((sig: string, index: number) => (
                  <div key={index} className="flex items-center space-x-2">
                    <div className={`w-2 h-2 rounded-full ${
                      sig.toLowerCase().includes('pathogenic') ? 'bg-red-500' :
                      sig.toLowerCase().includes('risk') ? 'bg-orange-500' :
                      'bg-gray-400'
                    }`} />
                    <span className="text-sm text-gray-700">{sig}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Population Data */}
          {results.minor_allele && (
            <div className="bg-white/80 rounded-xl p-4">
              <h4 className="font-bold text-gray-900 mb-3 flex items-center space-x-2">
                <Info className="h-4 w-4 text-blue-600" />
                <span>Population Data</span>
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-600">Minor Allele:</span>
                  <span className="ml-2 font-medium text-gray-900">{results.minor_allele}</span>
                </div>
                {results.minor_allele_freq && (
                  <div>
                    <span className="text-gray-600">Frequency:</span>
                    <span className="ml-2 font-medium text-gray-900">{(results.minor_allele_freq * 100).toFixed(2)}%</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* External Links */}
          <div className="bg-white/80 rounded-xl p-4">
            <h4 className="font-bold text-gray-900 mb-3 flex items-center space-x-2">
              <ExternalLink className="h-4 w-4 text-purple-600" />
              <span>External Resources</span>
            </h4>
            <div className="flex flex-wrap gap-2">
              <a
                href={`https://www.ncbi.nlm.nih.gov/snp/${searchTerm}`}
                target="_blank"
                rel="noopener noreferrer"
                className="px-3 py-2 bg-blue-100 hover:bg-blue-200 text-blue-800 rounded-lg text-xs font-medium transition-colors"
              >
                dbSNP
              </a>
              <a
                href={`https://www.ensembl.org/Homo_sapiens/Variation/Summary?v=${searchTerm}`}
                target="_blank"
                rel="noopener noreferrer"
                className="px-3 py-2 bg-green-100 hover:bg-green-200 text-green-800 rounded-lg text-xs font-medium transition-colors"
              >
                Ensembl
              </a>
              <a
                href={`https://www.pharmgkb.org/variant/${searchTerm}`}
                target="_blank"
                rel="noopener noreferrer"
                className="px-3 py-2 bg-purple-100 hover:bg-purple-200 text-purple-800 rounded-lg text-xs font-medium transition-colors"
              >
                PharmGKB
              </a>
              <a
                href={`https://www.clinvar.com/variation/?term=${searchTerm}`}
                target="_blank"
                rel="noopener noreferrer"
                className="px-3 py-2 bg-red-100 hover:bg-red-200 text-red-800 rounded-lg text-xs font-medium transition-colors"
              >
                ClinVar
              </a>
            </div>
          </div>
        </div>
      )}

      {/* No Results */}
      {results === null && !isLoading && !error && (
        <div className="text-center py-8 text-gray-500">
          <Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>Enter a variant ID to search for genetic information</p>
          <p className="text-sm mt-2">Examples: rs53576, rs1695, rs429358, rs7412</p>
        </div>
      )}
    </div>
  )
}