import React, { useState, useEffect } from 'react';

interface AnalysisProgress {
  analysis_id: number;
  status: string;
  progress_percentage: number;
  current_step: string;
  total_variants: number;
  processed_variants: number;
  estimated_completion: string | null;
  filename: string;
}

interface AnalysisProgressLoaderProps {
  analysisId: number;
  onComplete?: (results: any) => void;
  onError?: (error: string) => void;
}

export default function AnalysisProgressLoader({ 
  analysisId, 
  onComplete, 
  onError 
}: AnalysisProgressLoaderProps) {
  const [progress, setProgress] = useState<AnalysisProgress | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!analysisId) return;

    const checkProgress = async () => {
      try {
        const token = localStorage.getItem('token');
        if (!token) {
          throw new Error('No authentication token found');
        }

        const response = await fetch(`http://localhost:8000/analyze/progress/${analysisId}`, {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data: AnalysisProgress = await response.json();
        setProgress(data);

        // Check if analysis is complete
        if (data.status === 'completed') {
          setIsLoading(false);
          if (onComplete) {
            // Fetch full results
            const resultsResponse = await fetch(`http://localhost:8000/analyze/dashboard-data`, {
              headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json',
              },
            });

            if (resultsResponse.ok) {
              const results = await resultsResponse.json();
              onComplete(results);
            }
          }
        } else if (data.status === 'failed') {
          setIsLoading(false);
          const errorMsg = 'Analysis failed. Please try again.';
          setError(errorMsg);
          if (onError) {
            onError(errorMsg);
          }
        }

      } catch (err) {
        console.error('Error checking progress:', err);
        const errorMsg = err instanceof Error ? err.message : 'Unknown error occurred';
        setError(errorMsg);
        setIsLoading(false);
        if (onError) {
          onError(errorMsg);
        }
      }
    };

    // Initial check
    checkProgress();

    // Set up polling for progress updates
    const interval = setInterval(checkProgress, 2000); // Check every 2 seconds

    return () => clearInterval(interval);
  }, [analysisId, onComplete, onError]);

  if (error) {
    return (
      <div className="max-w-2xl mx-auto p-6">
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800 dark:text-red-200">
                Analysis Error
              </h3>
              <div className="mt-2 text-sm text-red-700 dark:text-red-300">
                {error}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!progress) {
    return (
      <div className="max-w-2xl mx-auto p-6">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-3/4 mb-4"></div>
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/2"></div>
        </div>
      </div>
    );
  }

  const progressPercentage = Math.max(0, Math.min(100, progress.progress_percentage || 0));
  const remainingTime = progress.estimated_completion 
    ? Math.max(0, new Date(progress.estimated_completion).getTime() - new Date().getTime())
    : null;

  const formatTimeRemaining = (milliseconds: number) => {
    const seconds = Math.floor(milliseconds / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) {
      return `${hours}h ${minutes % 60}m remaining`;
    } else if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s remaining`;
    } else {
      return `${seconds}s remaining`;
    }
  };

  return (
    <div className="max-w-2xl mx-auto p-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700">
        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                Analyzing Genetic Data
              </h2>
              <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                {progress.filename}
              </p>
            </div>
            <div className="flex items-center">
              {progress.status === 'processing' && (
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
              )}
            </div>
          </div>

          {/* Progress Bar */}
          <div className="mb-6">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Progress
              </span>
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                {progressPercentage}%
              </span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3">
              <div
                className="bg-gradient-to-r from-blue-500 to-green-500 h-3 rounded-full transition-all duration-500"
                style={{ width: `${progressPercentage}%` }}
              />
            </div>
          </div>

          {/* Current Step */}
          <div className="mb-6">
            <div className="flex items-center text-sm text-gray-600 dark:text-gray-400">
              <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              {progress.current_step}
            </div>
          </div>

          {/* Statistics Grid */}
          <div className="grid grid-cols-2 gap-4 mb-6">
            <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
              <div className="text-2xl font-bold text-gray-900 dark:text-white">
                {progress.total_variants.toLocaleString()}
              </div>
              <div className="text-sm text-gray-600 dark:text-gray-400">
                Total Variants
              </div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
              <div className="text-2xl font-bold text-gray-900 dark:text-white">
                {progress.processed_variants.toLocaleString()}
              </div>
              <div className="text-sm text-gray-600 dark:text-gray-400">
                Processed
              </div>
            </div>
          </div>

          {/* Time Remaining */}
          {remainingTime && remainingTime > 0 && (
            <div className="mb-6">
              <div className="flex items-center text-sm text-gray-600 dark:text-gray-400">
                <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                {formatTimeRemaining(remainingTime)}
              </div>
            </div>
          )}

          {/* Processing Steps */}
          <div className="space-y-3">
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              Analysis Steps
            </div>
            
            {[
              { step: 'Variant Classification', status: progressPercentage > 10 ? 'completed' : progressPercentage > 0 ? 'current' : 'pending' },
              { step: 'API Annotation', status: progressPercentage > 30 ? 'completed' : progressPercentage > 10 ? 'current' : 'pending' },
              { step: 'Health Risk Analysis', status: progressPercentage > 60 ? 'completed' : progressPercentage > 30 ? 'current' : 'pending' },
              { step: 'Drug Response Prediction', status: progressPercentage > 80 ? 'completed' : progressPercentage > 60 ? 'current' : 'pending' },
              { step: 'Report Generation', status: progressPercentage >= 100 ? 'completed' : progressPercentage > 80 ? 'current' : 'pending' },
            ].map((item, index) => (
              <div key={index} className="flex items-center">
                <div className={`w-4 h-4 rounded-full mr-3 flex items-center justify-center ${
                  item.status === 'completed' 
                    ? 'bg-green-500' 
                    : item.status === 'current' 
                      ? 'bg-blue-500 animate-pulse' 
                      : 'bg-gray-300 dark:bg-gray-600'
                }`}>
                  {item.status === 'completed' && (
                    <svg className="w-2.5 h-2.5 text-white" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  )}
                </div>
                <span className={`text-sm ${
                  item.status === 'completed' 
                    ? 'text-green-700 dark:text-green-400' 
                    : item.status === 'current'
                      ? 'text-blue-700 dark:text-blue-400 font-medium'
                      : 'text-gray-500 dark:text-gray-500'
                }`}>
                  {item.step}
                </span>
              </div>
            ))}
          </div>

          {/* Status Message */}
          <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
            <div className="flex items-center">
              <svg className="w-5 h-5 text-blue-600 dark:text-blue-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div className="text-sm text-blue-800 dark:text-blue-200">
                <strong>Processing your genetic data...</strong> We're analyzing {progress.total_variants.toLocaleString()} variants 
                to provide comprehensive health insights and drug response predictions.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}