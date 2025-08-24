'use client'

'use client'

import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, File, AlertCircle, CheckCircle } from 'lucide-react'

interface FileUploadProps {
  onAnalysisComplete: (data: any) => void
  token: string
}

export default function FileUpload({ onAnalysisComplete, token }: FileUploadProps) {
  const [isLoading, setIsLoading] = useState(false)
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'processing' | 'success' | 'error'>('idle')
  const [fileName, setFileName] = useState('')
  const [error, setError] = useState('')

  const handleFileUpload = async (file: File, fileType: 'vcf' | 'csv') => {
    setIsLoading(true)
    setUploadStatus('uploading')
    setFileName(file.name)
    setError('')

    try {
      const formData = new FormData()
      formData.append('file', file)

      // Upload file to backend with authentication
      const uploadResponse = await fetch(`http://localhost:8000/upload/${fileType}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData,
      })

      if (!uploadResponse.ok) {
        const errorData = await uploadResponse.json()
        throw new Error(errorData.detail || 'Upload failed')
      }

      const uploadResult = await uploadResponse.json()
      setUploadStatus('processing')

      // Get the actual analysis data from the uploaded file
      const analysisId = uploadResult.analysis_id
      
      // Fetch the real analysis results from the database
      const analysisResponse = await fetch(`http://localhost:8000/upload/analysis/${analysisId}`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })

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
      onAnalysisComplete(dashboardData)
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
      } else if (fileExtension === 'csv') {
        handleFileUpload(file, 'csv')
      } else {
        setError('Please upload a VCF or CSV file')
        setUploadStatus('error')
      }
    }
  }, [token])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/plain': ['.vcf'],
      'text/csv': ['.csv']
    },
    multiple: false,
    disabled: isLoading
  })

  const getStatusDisplay = () => {
    switch (uploadStatus) {
      case 'uploading':
        return (
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-2"></div>
            <p className="text-sm text-gray-600">Uploading {fileName}...</p>
          </div>
        )
      case 'processing':
        return (
          <div className="text-center">
            <div className="animate-pulse flex items-center justify-center mb-2">
              <File className="h-8 w-8 text-blue-600" />
            </div>
            <p className="text-sm text-gray-600">Analyzing genetic data...</p>
          </div>
        )
      case 'success':
        return (
          <div className="text-center text-green-600">
            <CheckCircle className="h-8 w-8 mx-auto mb-2" />
            <p className="text-sm">Analysis complete!</p>
          </div>
        )
      case 'error':
        return (
          <div className="text-center text-red-600">
            <AlertCircle className="h-8 w-8 mx-auto mb-2" />
            <p className="text-sm">{error}</p>
            <button
              onClick={() => {
                setUploadStatus('idle')
                setError('')
                setFileName('')
              }}
              className="mt-2 text-sm text-blue-600 hover:text-blue-700 underline"
            >
              Try again
            </button>
          </div>
        )
      default:
        return (
          <div className="text-center">
            <Upload className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <p className="text-xl font-semibold text-gray-900 mb-2">
              Upload your genetic data
            </p>
            <p className="text-gray-600 mb-4">
              Drop your VCF or CSV file here, or click to browse
            </p>
            <div className="text-sm text-gray-500">
              <p>Supported formats:</p>
              <p>• VCF files from genetic testing companies</p>
              <p>• CSV files with genetic variant data</p>
            </div>
          </div>
        )
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div
        {...getRootProps()}
        className={`
          border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors
          ${isDragActive ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-gray-400'}
          ${isLoading ? 'cursor-not-allowed opacity-50' : ''}
        `}
      >
        <input {...getInputProps()} />
        {getStatusDisplay()}
      </div>

      {uploadStatus === 'idle' && (
        <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
          <h3 className="text-lg font-semibold text-blue-900 mb-2">
            How to get your genetic data:
          </h3>
          <div className="text-sm text-blue-800 space-y-2">
            <p>• <strong>23andMe:</strong> Download raw data from your account</p>
            <p>• <strong>AncestryDNA:</strong> Request raw data download</p>
            <p>• <strong>MyHeritage:</strong> Export your raw DNA data</p>
            <p>• <strong>FamilyTreeDNA:</strong> Download your raw data file</p>
          </div>
        </div>
      )}
    </div>
  )
}