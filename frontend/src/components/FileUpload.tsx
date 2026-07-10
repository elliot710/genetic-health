'use client'

import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { 
  Upload, File, AlertCircle, CheckCircle, 
  Dna, Shield, Info, ExternalLink 
} from 'lucide-react'
import { getTheme } from '../utils/theme'
import { apiUrl } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Disclaimer } from '@/components/Disclaimer'
import type { DashboardData } from '@/components/categories/types'

interface FileUploadProps {
  onAnalysisComplete: (data: DashboardData, analysisId?: number) => void
  token: string
  isDarkMode: boolean
}

export default function FileUpload({ onAnalysisComplete, token, isDarkMode }: FileUploadProps) {
  const [isLoading, setIsLoading] = useState(false)
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'processing' | 'success' | 'error'>('idle')
  const [fileName, setFileName] = useState('')
  const [error, setError] = useState('')
  const [progress, setProgress] = useState(0)
  const theme = getTheme(isDarkMode)

  const handleFileUpload = useCallback(async (file: File, fileType: 'vcf' | 'csv') => {
    setIsLoading(true)
    setUploadStatus('uploading')
    setFileName(file.name)
    setError('')
    setProgress(0)

    try {
      const formData = new FormData()
      formData.append('file', file)

      // Simulate brief upload progress while file bytes are sent
      const progressInterval = setInterval(() => {
        setProgress(prev => Math.min(prev + 15, 90))
      }, 150)

      // Upload file to backend — returns immediately after parsing
      const uploadResponse = await fetch(apiUrl(`/upload/${fileType}`), {
        method: 'POST',
        credentials: 'include',
        body: formData,
      })

      clearInterval(progressInterval)
      setProgress(100)

      if (!uploadResponse.ok) {
        const errorData = await uploadResponse.json()
        throw new Error(errorData.detail || 'Upload failed')
      }

      const uploadResult = await uploadResponse.json()
      const analysisId = uploadResult.analysis_id
      
      setUploadStatus('success')

      // Build minimal dashboard data for the transition
      const dashboardData: DashboardData = {
        summary: {
          total_variants: uploadResult.total_variants || 0,
          data_sources: [file.name],
          analysis_id: analysisId,
          status: 'processing',
        },
        drug_interactions: {
          high_risk_genes: [],
          moderate_risk_genes: [],
          affected_drug_classes: []
        },
        real_data: {
          variants: [],
          upload_result: uploadResult
        }
      }
      
      // Transition to AnalysisProgressLoader immediately —
      // variant processing and analysis run in the background with SSE progress
      onAnalysisComplete(dashboardData, analysisId)

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
  }, [token, onAnalysisComplete])

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
  }, [handleFileUpload])

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
              <Upload className={`h-8 w-8 animate-bounce ${theme.primary.text}`} />
            </div>
            <div className="space-y-2">
              <p className={`text-lg font-medium ${theme.text.primary}`}>Uploading {fileName}</p>
              <div className={`w-64 rounded-full h-2 mx-auto ${theme.glassSecondary}`}>
                <div 
                  className={`h-2 rounded-full transition-all duration-300 ${theme.primary.bg}`}
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className={`text-sm ${theme.text.tertiary}`}>{progress}% complete</p>
            </div>
          </div>
        )
      case 'processing':
        return (
          <div className="text-center space-y-4">
            <div className="flex items-center justify-center">
              <Dna className={`h-8 w-8 animate-spin ${theme.text.accent}`} />
            </div>
            <div className="space-y-2">
              <p className={`text-lg font-medium ${theme.text.primary}`}>Analyzing genetic data</p>
              <div className={`w-64 rounded-full h-2 mx-auto ${theme.glassSecondary}`}>
                <div 
                  className="h-2 rounded-full transition-all duration-300 bg-gradient-to-r from-teal-500 to-cyan-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className={`text-sm ${theme.text.tertiary}`}>Processing {fileName}...</p>
            </div>
          </div>
        )
      case 'success':
        return (
          <div className={`text-center space-y-4 ${theme.success.text}`}>
            <CheckCircle className="h-12 w-12 mx-auto animate-pulse" />
            <div>
              <p className="text-lg font-medium">Upload complete!</p>
              <p className={`text-sm ${theme.text.tertiary}`}>Analyzing your data...</p>
            </div>
          </div>
        )
      case 'error':
        return (
          <div className="text-center space-y-4">
            <AlertCircle className={`h-8 w-8 mx-auto ${theme.error.text}`} />
            <div className="space-y-2">
              <p className={`text-lg font-medium ${theme.error.text}`}>Upload failed</p>
              <p className={`text-sm max-w-md mx-auto ${theme.text.tertiary}`}>{error}</p>
            </div>
            <Button onClick={resetUpload} size="sm">
              Try again
            </Button>
          </div>
        )
      default:
        return (
          <div className="text-center space-y-6">
            <div className="space-y-4">
              <Upload className={`h-16 w-16 mx-auto transition-colors ${
                isDragActive ? theme.primary.text : theme.text.muted
              }`} />
              <div>
                <p className={`text-2xl font-bold mb-2 ${theme.text.primary}`}>
                  {isDragActive ? 'Drop your file here' : 'Upload your genetic data'}
                </p>
                <p className={`text-lg ${theme.text.tertiary}`}>
                  {isDragActive ? 'Release to start analysis' : 'Drag and drop or click to browse'}
                </p>
              </div>
            </div>
            
            <div className="grid grid-cols-2 gap-4 max-w-md mx-auto text-sm">
              <div className={`p-3 rounded-lg border ${theme.glassSecondary} ${theme.primary.border}`}>
                <File className={`h-5 w-5 mx-auto mb-1 ${theme.primary.text}`} />
                <p className={`font-medium ${theme.text.primary}`}>VCF Files</p>
                <p className={theme.text.secondary}>Raw genetic variants</p>
              </div>
              <div className={`p-3 rounded-lg border ${theme.glassSecondary} ${theme.primary.border}`}>
                <File className={`h-5 w-5 mx-auto mb-1 ${theme.text.accent}`} />
                <p className={`font-medium ${theme.text.primary}`}>CSV/TXT Files</p>
                <p className={theme.text.secondary}>Genetic data tables</p>
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
    },
    {
      name: 'AncestryDNA',
      description: 'Request raw data download from settings',
      url: 'https://www.ancestry.com/dna/',
    },
    {
      name: 'MyHeritage',
      description: 'Export raw DNA data from your account',
      url: 'https://www.myheritage.com/dna',
    },
    {
      name: 'FamilyTreeDNA',
      description: 'Download from your results page',
      url: 'https://www.familytreedna.com/',
    }
  ]

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <Disclaimer />

      {/* Main Upload Area */}
      <div className={`rounded-2xl shadow-lg border overflow-hidden backdrop-blur-xl ${theme.glass} ${theme.glassBorder}`}>
        <div
          {...getRootProps()}
          className={`
            p-12 text-center cursor-pointer transition-all duration-200
            ${isDragActive 
              ? isDarkMode ? 'bg-teal-500/20' : 'bg-teal-50'
              : theme.interactive.hover
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
          <div className={`rounded-xl shadow-sm border p-6 backdrop-blur-xl ${theme.glass} ${theme.glassBorder}`}>
            <div className="flex items-center mb-4">
              <Dna className={`h-6 w-6 mr-2 ${theme.primary.text}`} />
              <h3 className={`text-lg font-semibold ${theme.text.primary}`}>
                Get Your Genetic Data
              </h3>
            </div>
            <div className="space-y-3">
              {dataProviders.map((provider, index) => (
                <div key={index} className={`p-3 rounded-lg border ${theme.glassSecondary} ${theme.glassSecondaryBorder}`}>
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <h4 className={`font-medium ${theme.text.primary}`}>{provider.name}</h4>
                      <p className={`text-sm ${theme.text.tertiary}`}>{provider.description}</p>
                    </div>
                    <a 
                      href={provider.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={`ml-2 p-1 rounded transition-colors ${theme.interactive.hover}`}
                    >
                      <ExternalLink className={`h-4 w-4 ${theme.text.secondary}`} />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Privacy & Security */}
          <div className={`rounded-xl shadow-sm border p-6 backdrop-blur-xl ${theme.glass} ${theme.glassBorder}`}>
            <div className="flex items-center mb-4">
              <Shield className={`h-6 w-6 mr-2 ${theme.success.text}`} />
              <h3 className={`text-lg font-semibold ${theme.text.primary}`}>
                Privacy & Security
              </h3>
            </div>
            <div className="space-y-4">
              <div className="flex items-start space-x-3">
                <CheckCircle className={`h-5 w-5 mt-0.5 flex-shrink-0 ${theme.success.text}`} />
                <div>
                  <p className={`font-medium ${theme.text.primary}`}>Data Processing</p>
                  <p className={`text-sm ${theme.text.tertiary}`}>Your data is not stored permanently.</p>
                </div>
              </div>
              <div className="flex items-start space-x-3">
                <CheckCircle className={`h-5 w-5 mt-0.5 flex-shrink-0 ${theme.success.text}`} />
                <div>
                  <p className={`font-medium ${theme.text.primary}`}>Encrypted Transfer</p>
                  <p className={`text-sm ${theme.text.tertiary}`}>All data transfers use HTTPS encryption</p>
                </div>
              </div>
              <div className="flex items-start space-x-3">
                <CheckCircle className={`h-5 w-5 mt-0.5 flex-shrink-0 ${theme.success.text}`} />
                <div>
                  <p className={`font-medium ${theme.text.primary}`}>User Control</p>
                  <p className={`text-sm ${theme.text.tertiary}`}>You can delete your data at any time</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* File Format Information */}
      {uploadStatus === 'idle' && (
        <div className={`border rounded-xl p-6 backdrop-blur-xl ${theme.glass} ${theme.primary.border}`}>
          <div className="flex items-start space-x-3">
            <Info className={`h-6 w-6 mt-0.5 flex-shrink-0 ${theme.primary.text}`} />
            <div>
              <h3 className={`text-lg font-semibold mb-2 ${theme.text.primary}`}>
                Supported File Formats
              </h3>
              <div className={`grid grid-cols-1 md:grid-cols-2 gap-4 text-sm ${theme.text.secondary}`}>
                <div>
                  <p className={`font-medium ${theme.text.primary}`}>VCF Files (.vcf)</p>
                  <p>Standard format for genetic variants with detailed annotations</p>
                </div>
                <div>
                  <p className={`font-medium ${theme.text.primary}`}>CSV/TXT Files (.csv, .txt)</p>
                  <p>Tabular genetic data from testing companies</p>
                </div>
              </div>
              <div className={`mt-4 p-3 rounded-lg ${theme.glassSecondary}`}>
                <p className={`text-sm ${theme.text.secondary}`}>
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