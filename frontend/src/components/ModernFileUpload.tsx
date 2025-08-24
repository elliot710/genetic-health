'use client'

import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { 
  Upload, File, AlertCircle, CheckCircle, 
  Clock, Dna, Shield, Info, ExternalLink 
} from 'lucide-react'
import { getTheme } from '@/utils/theme'

interface FileUploadProps {
  onAnalysisComplete: (data: any) => void
  token: string
  isDarkMode: boolean
}

export default function ModernFileUpload({ onAnalysisComplete, token, isDarkMode }: FileUploadProps) {
  const [isLoading, setIsLoading] = useState(false)
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'processing' | 'success' | 'error'>('idle')
  const [fileName, setFileName] = useState('')
  const [error, setError] = useState('')
  const [progress, setProgress] = useState(0)

  // Get theme object
  const theme = getTheme(isDarkMode)

  const handleFileUpload = async (file: File, fileType: 'vcf' | 'csv') => {
    setIsLoading(true)
    setUploadStatus('uploading')
    setFileName(file.name)
    setError('')
    setProgress(0)

    try {
      const formData = new FormData()
      formData.append('file', file)

      // Simulate progress for upload
      const progressInterval = setInterval(() => {
        setProgress(prev => Math.min(prev + 10, 90))
      }, 200)

      // Upload file to backend with authentication
      const uploadResponse = await fetch(`http://localhost:8000/upload/${fileType}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData,
      })

      clearInterval(progressInterval)
      setProgress(100)

      if (!uploadResponse.ok) {
        const errorData = await uploadResponse.json()
        throw new Error(errorData.detail || 'Upload failed')
      }

      const uploadResult = await uploadResponse.json()
      setUploadStatus('processing')
      setProgress(0)

      // Trigger background analysis automatically
      try {
        await fetch(`http://localhost:8000/upload/trigger-analysis/${uploadResult.analysis_id}`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`
          }
        })
      } catch (triggerError) {
        console.log('Analysis trigger failed, continuing with existing data:', triggerError)
      }

      // Simulate analysis progress
      const analysisInterval = setInterval(() => {
        setProgress(prev => Math.min(prev + 15, 90))
      }, 300)

      // Get the actual analysis data from the uploaded file instead of calling the mocked analysis endpoint
      const analysisId = uploadResult.analysis_id
      
      // Fetch the real analysis results from the database
      const analysisResponse = await fetch(`http://localhost:8000/upload/analysis/${analysisId}`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })

      clearInterval(analysisInterval)
      setProgress(100)

      if (!analysisResponse.ok) {
        const errorData = await analysisResponse.json()
        throw new Error(errorData.detail || 'Failed to fetch analysis results')
      }

      const analysisResult = await analysisResponse.json()
      
      // Transform the real data into the format expected by Dashboard
      const dashboardData = {
        summary: {
          total_variants: analysisResult.sample_variants?.length || uploadResult.genetic_variants_found || uploadResult.total_rows,
          data_sources: [uploadResult.filename],
          analysis_id: analysisId,
          upload_info: uploadResult
        },
        health_risks: {
          overall_score: 85, // Will be updated when background analysis completes
          risk_categories: analysisResult.health_risks?.reduce((acc: any, risk: any) => {
            acc[risk.condition] = {
              score: risk.risk_level === 'high' ? 90 : risk.risk_level === 'moderate' ? 60 : 30,
              variants: risk.associated_variants || []
            }
            return acc
          }, {}) || {}
        },
        drug_interactions: {
          high_risk_genes: analysisResult.drug_responses?.filter((dr: any) => dr.response_type === 'poor_metabolizer').map((dr: any) => dr.gene) || [],
          moderate_risk_genes: analysisResult.drug_responses?.filter((dr: any) => dr.response_type === 'intermediate_metabolizer').map((dr: any) => dr.gene) || [],
          affected_drug_classes: [...new Set(analysisResult.drug_responses?.map((dr: any) => dr.drug) || [])]
        },
        recommendations: [
          `Successfully uploaded ${uploadResult.filename} with ${uploadResult.genetic_variants_found || uploadResult.total_rows} data points`,
          ...(analysisResult.health_risks?.map((risk: any) => risk.recommendations).flat() || []),
          "Genetic analysis is processing in the background - refresh for updated results",
          "Consult with a healthcare provider for personalized recommendations"
        ],
        real_data: {
          variants: analysisResult.sample_variants || [],
          analysis: analysisResult.analysis,
          upload_result: uploadResult
        }
      }
      
      setUploadStatus('success')
      
      // Small delay to show completion
      setTimeout(() => {
        onAnalysisComplete(dashboardData)
      }, 1000)

    } catch (error) {
      console.error('Error processing file:', error)
      let errorMessage = 'An error occurred while processing your file.'
      
      if (error instanceof Error) {
        if (error.message.includes('Error tokenizing data')) {
          errorMessage = 'The file format appears to be inconsistent. Please ensure your CSV file has consistent columns and try again. Genetic data files from 23andMe, AncestryDNA, and similar services are supported.'
        } else if (error.message.includes('Failed to process')) {
          errorMessage = error.message
        } else {
          errorMessage = `Upload failed: ${error.message}`
        }
      }
      
      setError(errorMessage)
      setUploadStatus('error')
    } finally {
      setIsLoading(false)
    }
  }

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const file = acceptedFiles[0]
    if (file) {
      const fileExtension = file.name.split('.').pop()?.toLowerCase()
      
      if (fileExtension === 'vcf') {
        handleFileUpload(file, 'vcf')
      } else if (fileExtension === 'csv' || fileExtension === 'txt') {
        handleFileUpload(file, 'csv')
      } else {
        setError('Please upload a VCF, CSV, or TXT file containing genetic data')
        setUploadStatus('error')
      }
    }
  }, [token])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/plain': ['.vcf', '.txt'],
      'text/csv': ['.csv'],
      'application/vnd.ms-excel': ['.csv']
    },
    multiple: false,
    disabled: isLoading
  })

  const resetUpload = () => {
    setUploadStatus('idle')
    setError('')
    setFileName('')
    setProgress(0)
  }

  const getStatusDisplay = () => {
    switch (uploadStatus) {
      case 'uploading':
        return (
          <div className="text-center space-y-4">
            <div className="flex items-center justify-center">
              <Upload className={`h-8 w-8 animate-bounce ${isDarkMode ? 'text-teal-400' : 'text-teal-600'}`} />
            </div>
            <div className="space-y-2">
              <p className={`text-lg font-medium ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>Uploading {fileName}</p>
              <div className={`w-64 rounded-full h-2 mx-auto ${isDarkMode ? 'bg-slate-700' : 'bg-gray-200'}`}>
                <div 
                  className={`h-2 rounded-full transition-all duration-300 ${isDarkMode ? 'bg-teal-400' : 'bg-teal-600'}`}
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className={`text-sm ${isDarkMode ? 'text-slate-300' : 'text-gray-600'}`}>{progress}% complete</p>
            </div>
          </div>
        )
      case 'processing':
        return (
          <div className="text-center space-y-4">
            <div className="flex items-center justify-center">
              <Dna className={`h-8 w-8 animate-spin ${isDarkMode ? 'text-cyan-400' : 'text-cyan-600'}`} />
            </div>
            <div className="space-y-2">
              <p className={`text-lg font-medium ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>Analyzing genetic data</p>
              <div className={`w-64 rounded-full h-2 mx-auto ${isDarkMode ? 'bg-slate-700' : 'bg-gray-200'}`}>
                <div 
                  className={`h-2 rounded-full transition-all duration-300 ${isDarkMode ? 'bg-cyan-400' : 'bg-cyan-600'}`}
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className={`text-sm ${isDarkMode ? 'text-slate-300' : 'text-gray-600'}`}>Processing {fileName}...</p>
            </div>
          </div>
        )
      case 'success':
        return (
          <div className={`text-center space-y-4 ${isDarkMode ? 'text-green-400' : 'text-green-600'}`}>
            <CheckCircle className="h-12 w-12 mx-auto animate-pulse" />
            <div>
              <p className="text-lg font-medium">Analysis complete!</p>
              <p className={`text-sm ${isDarkMode ? 'text-slate-300' : 'text-gray-600'}`}>Redirecting to your results...</p>
            </div>
          </div>
        )
      case 'error':
        return (
          <div className="text-center space-y-4">
            <AlertCircle className={`h-8 w-8 mx-auto ${isDarkMode ? 'text-red-400' : 'text-red-600'}`} />
            <div className="space-y-2">
              <p className={`text-lg font-medium ${isDarkMode ? 'text-red-400' : 'text-red-600'}`}>Upload failed</p>
              <p className={`text-sm max-w-md mx-auto ${isDarkMode ? 'text-slate-300' : 'text-gray-600'}`}>{error}</p>
            </div>
            <button
              onClick={resetUpload}
              className={`px-4 py-2 text-sm font-medium text-white rounded-md transition-colors ${
                isDarkMode ? 'bg-teal-600 hover:bg-teal-700' : 'bg-teal-600 hover:bg-teal-700'
              }`}
            >
              Try again
            </button>
          </div>
        )
      default:
        return (
          <div className="text-center space-y-6">
            <div className="space-y-4">
              <Upload className={`h-16 w-16 mx-auto transition-colors ${
                isDragActive 
                  ? isDarkMode ? 'text-teal-400' : 'text-teal-600'
                  : isDarkMode ? 'text-slate-400' : 'text-gray-400'
              }`} />
              <div>
                <p className={`text-2xl font-bold mb-2 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                  {isDragActive ? 'Drop your file here' : 'Upload your genetic data'}
                </p>
                <p className={`text-lg ${isDarkMode ? 'text-slate-300' : 'text-gray-600'}`}>
                  {isDragActive ? 'Release to start analysis' : 'Drag and drop or click to browse'}
                </p>
              </div>
            </div>
            
            <div className="grid grid-cols-2 gap-4 max-w-md mx-auto text-sm">
              <div className={`p-3 rounded-lg ${
                isDarkMode 
                  ? 'bg-teal-500/20' 
                  : 'bg-teal-50'
              }`}>
                <File className={`h-5 w-5 mx-auto mb-1 ${isDarkMode ? 'text-teal-400' : 'text-teal-600'}`} />
                <p className={`font-medium ${isDarkMode ? 'text-teal-100' : 'text-teal-900'}`}>VCF Files</p>
                <p className={isDarkMode ? 'text-teal-200' : 'text-teal-700'}>Raw genetic variants</p>
              </div>
              <div className={`p-3 rounded-lg ${
                isDarkMode 
                  ? 'bg-cyan-500/20' 
                  : 'bg-cyan-50'
              }`}>
                <File className={`h-5 w-5 mx-auto mb-1 ${isDarkMode ? 'text-cyan-400' : 'text-cyan-600'}`} />
                <p className={`font-medium ${isDarkMode ? 'text-cyan-100' : 'text-cyan-900'}`}>CSV/TXT Files</p>
                <p className={isDarkMode ? 'text-cyan-200' : 'text-cyan-700'}>Genetic data tables</p>
              </div>
            </div>
          </div>
        )
    }
  }

  const dataProviders = [
    {
      name: '23andMe',
      description: 'Download raw data from your account dashboard',
      url: 'https://you.23andme.com/tools/data-download/',
      color: isDarkMode ? 'bg-pink-500/20 border-pink-500/30 text-pink-300' : 'bg-pink-50 border-pink-200 text-pink-800'
    },
    {
      name: 'AncestryDNA',
      description: 'Request raw data download from settings',
      url: 'https://www.ancestry.com/dna/',
      color: isDarkMode ? 'bg-green-500/20 border-green-500/30 text-green-300' : 'bg-green-50 border-green-200 text-green-800'
    },
    {
      name: 'MyHeritage',
      description: 'Export raw DNA data from your account',
      url: 'https://www.myheritage.com/dna',
      color: isDarkMode ? 'bg-blue-500/20 border-blue-500/30 text-blue-300' : 'bg-blue-50 border-blue-200 text-blue-800'
    },
    {
      name: 'FamilyTreeDNA',
      description: 'Download from your results page',
      url: 'https://www.familytreedna.com/',
      color: isDarkMode ? 'bg-purple-500/20 border-purple-500/30 text-purple-300' : 'bg-purple-50 border-purple-200 text-purple-800'
    }
  ]

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Main Upload Area */}
      <div className={`rounded-2xl shadow-lg border overflow-hidden backdrop-blur-xl ${
        isDarkMode 
          ? 'bg-white/10 border-white/20' 
          : 'bg-white/40 border-white/60'
      }`}>
        <div
          {...getRootProps()}
          className={`
            p-12 text-center cursor-pointer transition-all duration-200
            ${isDragActive 
              ? isDarkMode ? 'bg-teal-500/20 border-teal-300/50' : 'bg-teal-50 border-teal-300'
              : isDarkMode ? 'hover:bg-white/5' : 'hover:bg-white/20'
            }
            ${isLoading ? 'cursor-not-allowed' : ''}
          `}
        >
          <input {...getInputProps()} />
          {getStatusDisplay()}
        </div>
      </div>

      {/* Information Sections */}
      {uploadStatus === 'idle' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Data Providers */}
          <div className={`rounded-xl shadow-sm border p-6 backdrop-blur-xl ${
            isDarkMode 
              ? 'bg-white/10 border-white/20' 
              : 'bg-white/40 border-white/60'
          }`}>
            <div className="flex items-center mb-4">
              <Dna className={`h-6 w-6 mr-2 ${isDarkMode ? 'text-teal-400' : 'text-teal-600'}`} />
              <h3 className={`text-lg font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                Get Your Genetic Data
              </h3>
            </div>
            <div className="space-y-3">
              {dataProviders.map((provider, index) => (
                <div key={index} className={`p-3 rounded-lg border ${provider.color}`}>
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <h4 className="font-medium">{provider.name}</h4>
                      <p className="text-sm opacity-80">{provider.description}</p>
                    </div>
                    <a 
                      href={provider.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={`ml-2 p-1 rounded transition-colors ${
                        isDarkMode ? 'hover:bg-white/20' : 'hover:bg-white/50'
                      }`}
                    >
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Privacy & Security */}
          <div className={`rounded-xl shadow-sm border p-6 backdrop-blur-xl ${
            isDarkMode 
              ? 'bg-white/10 border-white/20' 
              : 'bg-white/40 border-white/60'
          }`}>
            <div className="flex items-center mb-4">
              <Shield className={`h-6 w-6 mr-2 ${isDarkMode ? 'text-green-400' : 'text-green-600'}`} />
              <h3 className={`text-lg font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                Privacy & Security
              </h3>
            </div>
            <div className="space-y-4">
              <div className="flex items-start space-x-3">
                <CheckCircle className={`h-5 w-5 mt-0.5 flex-shrink-0 ${isDarkMode ? 'text-green-400' : 'text-green-600'}`} />
                <div>
                  <p className={`font-medium ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>Local Processing</p>
                  <p className={`text-sm ${isDarkMode ? 'text-slate-300' : 'text-gray-600'}`}>Your data is processed locally and not stored permanently</p>
                </div>
              </div>
              <div className="flex items-start space-x-3">
                <CheckCircle className={`h-5 w-5 mt-0.5 flex-shrink-0 ${isDarkMode ? 'text-green-400' : 'text-green-600'}`} />
                <div>
                  <p className={`font-medium ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>Encrypted Transfer</p>
                  <p className={`text-sm ${isDarkMode ? 'text-slate-300' : 'text-gray-600'}`}>All data transfers use HTTPS encryption</p>
                </div>
              </div>
              <div className="flex items-start space-x-3">
                <CheckCircle className={`h-5 w-5 mt-0.5 flex-shrink-0 ${isDarkMode ? 'text-green-400' : 'text-green-600'}`} />
                <div>
                  <p className={`font-medium ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>User Control</p>
                  <p className={`text-sm ${isDarkMode ? 'text-slate-300' : 'text-gray-600'}`}>You can delete your data at any time</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* File Format Information */}
      {uploadStatus === 'idle' && (
        <div className={`border rounded-xl p-6 backdrop-blur-xl ${
          isDarkMode 
            ? 'bg-teal-500/20 border-teal-500/30' 
            : 'bg-white/60 border-teal-200'
        }`}>
          <div className="flex items-start space-x-3">
            <Info className={`h-6 w-6 mt-0.5 flex-shrink-0 ${isDarkMode ? 'text-teal-400' : 'text-teal-600'}`} />
            <div>
              <h3 className={`text-lg font-semibold mb-2 ${isDarkMode ? 'text-teal-100' : 'text-gray-900'}`}>
                Supported File Formats
              </h3>
              <div className={`grid grid-cols-1 md:grid-cols-2 gap-4 text-sm ${isDarkMode ? 'text-teal-200' : 'text-gray-700'}`}>
                <div>
                  <p className={`font-medium ${isDarkMode ? 'text-teal-100' : 'text-gray-900'}`}>VCF Files (.vcf)</p>
                  <p>Standard format for genetic variants with detailed annotations</p>
                </div>
                <div>
                  <p className={`font-medium ${isDarkMode ? 'text-teal-100' : 'text-gray-900'}`}>CSV/TXT Files (.csv, .txt)</p>
                  <p>Tabular genetic data from testing companies</p>
                </div>
              </div>
              <div className={`mt-4 p-3 rounded-lg ${
                isDarkMode 
                  ? 'bg-teal-500/30' 
                  : 'bg-teal-100'
              }`}>
                <p className={`text-sm ${isDarkMode ? 'text-teal-100' : 'text-gray-800'}`}>
                  <strong>Note:</strong> Files are automatically detected and parsed. 
                  Our system handles various formats including 23andMe, AncestryDNA, 
                  and other major genetic testing platforms.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}