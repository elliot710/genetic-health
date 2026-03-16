import React, { useState, useEffect } from 'react';
import { AlertCircle, Check, ChevronLeft, ChevronRight, Clock, Info, Loader2 } from 'lucide-react';
import { getTheme } from '../utils/theme';
import { Button } from '@/components/ui/button';
import { apiUrl } from '@/lib/api';

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
  isDarkMode?: boolean;
  onComplete?: (results: Record<string, unknown>) => void;
  onError?: (error: string) => void;
  onBack?: () => void;
}

export default function AnalysisProgressLoader({ 
  analysisId, 
  isDarkMode: isDarkModeProp,
  onComplete, 
  onError,
  onBack
}: AnalysisProgressLoaderProps) {
  const [progress, setProgress] = useState<AnalysisProgress | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Use prop if provided, otherwise read from localStorage
  const [localDarkMode, setLocalDarkMode] = useState(false);
  useEffect(() => {
    if (isDarkModeProp === undefined) {
      const saved = localStorage.getItem('darkMode');
      if (saved) setLocalDarkMode(JSON.parse(saved));
    }
  }, [isDarkModeProp]);
  const isDarkMode = isDarkModeProp ?? localDarkMode;
  const theme = getTheme(isDarkMode);

  useEffect(() => {
    if (!analysisId) return;

    const checkProgress = async () => {
      try {
        console.log('🔍 Making request to:', apiUrl(`/api/analysis/status/${analysisId}`));

        const response = await fetch(apiUrl(`/api/analysis/status/${analysisId}`), {
          method: 'GET',
          credentials: 'include',
        });

        console.log('📡 Response status:', response.status);
        console.log('📡 Response ok:', response.ok);

        if (!response.ok) {
          const errorText = await response.text();
          console.error('❌ Response error:', errorText);
          throw new Error(`HTTP error! status: ${response.status} - ${errorText}`);
        }

        const data: AnalysisProgress = await response.json();
        setProgress(data);

        // Check if analysis is complete
        if (data.status === 'completed') {
          setIsLoading(false);
          if (onComplete) {
            // Fetch full results
            const resultsResponse = await fetch(apiUrl('/api/analysis/dashboard-data'), {
              credentials: 'include',
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
        } else if (data.status === 'pending') {
          // Analysis is queued but not yet started - this is normal
          console.log('Analysis is pending/queued, waiting for processing to start...');
        } else if (data.status === 'processing') {
          // Analysis is actively running - this is normal
          console.log('Analysis is processing...');
        } else {
          // Handle any other unexpected status
          console.warn('Unexpected analysis status:', data.status);
        }

      } catch (err) {
        console.error('Error checking progress:', err);
        
        // Don't immediately fail on network errors - they might be temporary
        // Only fail after multiple consecutive failures
        const errorMsg = err instanceof Error ? err.message : 'Unknown error occurred';
        
        // For now, just log the error but continue polling
        // The user will see the error in console but won't get the "failed" UI
        // unless the backend explicitly returns status 'failed'
        console.warn('Temporary error checking analysis progress, will retry...', errorMsg);
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
        <div className={`${theme.error.bg} border ${theme.error.border} rounded-lg p-4`}>
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <AlertCircle className={`h-5 w-5 ${theme.error.text}`} />
            </div>
            <div className="ml-3">
              <h3 className={`text-sm font-medium ${theme.error.text}`}>
                Analysis Error
              </h3>
              <div className={`mt-2 text-sm ${theme.text.secondary}`}>
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
        <div className="animate-pulse space-y-4">
          <div className={`h-4 ${theme.glassSecondary} rounded w-3/4`}></div>
          <div className={`h-4 ${theme.glassSecondary} rounded w-1/2`}></div>
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
      <div className={`${theme.glass} rounded-lg shadow-lg border ${theme.glassBorder}`}>
        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center space-x-3">
              {onBack && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onBack}
                  title="Back to dashboard"
                  className="h-8 w-8"
                >
                  <ChevronLeft className={`w-4 h-4 ${theme.text.secondary}`} />
                </Button>
              )}
              <div>
                <h2 className={`text-xl font-semibold ${theme.text.primary}`}>
                  {progress.status === 'pending' ? 'Preparing Genetic Analysis' : 'Analyzing Genetic Data'}
                </h2>
                <p className={`text-sm ${theme.text.tertiary} mt-1`}>
                  {progress.filename}
                </p>
              </div>
            </div>
            <div className="flex items-center">
              {(progress.status === 'processing' || progress.status === 'pending') && (
                <Loader2 className={`h-6 w-6 animate-spin ${theme.primary.text}`} />
              )}
            </div>
          </div>

          {/* Progress Bar */}
          <div className="mb-6">
            <div className="flex justify-between items-center mb-2">
              <span className={`text-sm font-medium ${theme.text.secondary}`}>
                Progress
              </span>
              <span className={`text-sm font-medium ${theme.text.secondary}`}>
                {progressPercentage}%
              </span>
            </div>
            <div className={`w-full ${theme.glassSecondary} rounded-full h-3`}>
              <div
                className="bg-gradient-to-r from-teal-500 to-cyan-500 h-3 rounded-full transition-all duration-500"
                style={{ width: `${progressPercentage}%` }}
              />
            </div>
          </div>

          {/* Current Step */}
          <div className="mb-6">
            <div className={`flex items-center text-sm ${theme.text.tertiary}`}>
              <ChevronRight className="w-4 h-4 mr-2" />
              {(progress.current_step || '').replace(/_/g, ' ')}
            </div>
          </div>

          {/* Statistics Grid */}
          <div className="grid grid-cols-2 gap-4 mb-6">
            <div className={`${theme.glassSecondary} rounded-lg p-4`}>
              <div className={`text-2xl font-bold ${theme.text.primary}`}>
                {progress.total_variants.toLocaleString()}
              </div>
              <div className={`text-sm ${theme.text.tertiary}`}>
                Total Variants
              </div>
            </div>
            <div className={`${theme.glassSecondary} rounded-lg p-4`}>
              <div className={`text-2xl font-bold ${theme.text.primary}`}>
                {progress.processed_variants.toLocaleString()}
              </div>
              <div className={`text-sm ${theme.text.tertiary}`}>
                Processed
              </div>
            </div>
          </div>

          {/* Time Remaining */}
          {remainingTime && remainingTime > 0 && (
            <div className="mb-6">
              <div className={`flex items-center text-sm ${theme.text.tertiary}`}>
                <Clock className="w-4 h-4 mr-2" />
                {formatTimeRemaining(remainingTime)}
              </div>
            </div>
          )}

          {/* Processing Steps */}
          <div className="space-y-3">
            <div className={`text-sm font-medium ${theme.text.secondary} mb-3`}>
              Analysis Steps
            </div>
            
            {[
              { step: 'Variant Classification', status: progressPercentage > 5 ? 'completed' : progressPercentage > 0 ? 'current' : 'pending' },
              { step: 'API Annotation', status: progressPercentage > 15 ? 'completed' : progressPercentage > 5 ? 'current' : 'pending' },
              { step: 'Health & Wellness Analysis', status: progressPercentage > 25 ? 'completed' : progressPercentage > 15 ? 'current' : 'pending' },
              { step: 'Food & Nutrition Insights', status: progressPercentage > 35 ? 'completed' : progressPercentage > 25 ? 'current' : 'pending' },
              { step: 'Drug Response Prediction', status: progressPercentage > 45 ? 'completed' : progressPercentage > 35 ? 'current' : 'pending' },
              { step: 'Physical Traits Analysis', status: progressPercentage > 55 ? 'completed' : progressPercentage > 45 ? 'current' : 'pending' },
              { step: 'Sports & Fitness Insights', status: progressPercentage > 65 ? 'completed' : progressPercentage > 55 ? 'current' : 'pending' },
              { step: 'Intelligence Analysis', status: progressPercentage > 70 ? 'completed' : progressPercentage > 65 ? 'current' : 'pending' },
              { step: 'Personality Traits', status: progressPercentage > 75 ? 'completed' : progressPercentage > 70 ? 'current' : 'pending' },
              { step: 'Ancestry & Origins', status: progressPercentage > 80 ? 'completed' : progressPercentage > 75 ? 'current' : 'pending' },
              { step: 'Carrier Status Assessment', status: progressPercentage > 85 ? 'completed' : progressPercentage > 80 ? 'current' : 'pending' },
              { step: 'Wellness Reports', status: progressPercentage > 90 ? 'completed' : progressPercentage > 85 ? 'current' : 'pending' },
              { step: 'Methylation Pathways', status: progressPercentage > 95 ? 'completed' : progressPercentage > 90 ? 'current' : 'pending' },
              { step: 'Detoxification Analysis', status: progressPercentage > 98 ? 'completed' : progressPercentage > 95 ? 'current' : 'pending' },
              { step: 'Report Generation', status: progressPercentage >= 100 ? 'completed' : progressPercentage > 98 ? 'current' : 'pending' },
            ].map((item, index) => (
              <div key={index} className="flex items-center">
                <div className={`w-4 h-4 rounded-full mr-3 flex items-center justify-center ${
                  item.status === 'completed' 
                    ? 'bg-teal-500' 
                    : item.status === 'current' 
                      ? 'bg-cyan-500 animate-pulse' 
                      : theme.glassSecondary
                }`}>
                  {item.status === 'completed' && (
                    <Check className="w-2.5 h-2.5 text-white" />
                  )}
                </div>
                <span className={`text-sm ${
                  item.status === 'completed' 
                    ? theme.success.text 
                    : item.status === 'current'
                      ? `${theme.primary.text} font-medium`
                      : theme.text.muted
                }`}>
                  {item.step}
                </span>
              </div>
            ))}
          </div>

          {/* Status Message */}
          <div className={`mt-6 p-4 ${theme.glass} border ${theme.primary.border} rounded-lg`}>
            <div className="flex items-center">
              <Info className={`w-5 h-5 ${theme.primary.text} mr-3 flex-shrink-0`} />
              <div className={`text-sm ${theme.text.secondary}`}>
                {progress.status === 'pending' ? (
                  <div>
                    <strong>Analysis queued...</strong> Your genetic data has been uploaded successfully and is waiting in the processing queue. 
                    We'll begin analyzing your {progress.total_variants.toLocaleString()} variants shortly.
                  </div>
                ) : (
                  <div>
                    <strong>Processing your genetic data...</strong> We're analyzing {progress.total_variants.toLocaleString()} variants 
                    across 14 comprehensive categories including health, nutrition, drug responses, physical traits, sports performance, 
                    intelligence, personality, ancestry, wellness, methylation, and detoxification pathways.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}