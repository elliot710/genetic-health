import React, { useState, useEffect } from 'react';
import { AlertCircle, Check, ChevronLeft, ChevronRight, Clock, Info, Loader2 } from 'lucide-react';
import { getTheme } from '../utils/theme';
import { Button } from '@/components/ui/button';
import { apiUrl } from '@/lib/api';
import type { DashboardData } from '@/components/categories/types';

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
  onComplete?: (results: DashboardData) => void;
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

    const eventSource = new EventSource(
      apiUrl(`/api/analysis/stream/${analysisId}`),
      { withCredentials: true }
    );

    const handleCompleted = async () => {
      setIsLoading(false);
      if (onComplete) {
        const resultsResponse = await fetch(apiUrl('/api/analysis/dashboard-data'), {
          credentials: 'include',
        });
        if (resultsResponse.ok) {
          const results = await resultsResponse.json();
          onComplete(results);
        }
      }
    };

    eventSource.onmessage = (event) => {
      try {
        const data: AnalysisProgress = JSON.parse(event.data);
        setProgress(data);

        if (data.status === 'completed') {
          eventSource.close();
          handleCompleted();
        } else if (data.status === 'failed') {
          eventSource.close();
          setIsLoading(false);
          const errorMsg = 'Analysis failed. Please try again.';
          setError(errorMsg);
          if (onError) onError(errorMsg);
        }
      } catch (err) {
        console.error('Error parsing SSE message:', err);
      }
    };

    eventSource.addEventListener('error', (event) => {
      const data = (event as MessageEvent).data;
      if (data) {
        try {
          const parsed = JSON.parse(data);
          const errorMsg = parsed.error || 'Analysis error occurred.';
          // "Analysis not found" means the data was deleted — close silently without
          // surfacing an error UI; Dashboard.handleAnalysisError will dismiss the loader.
          if (errorMsg.toLowerCase().includes('not found')) {
            eventSource.close();
            if (onError) onError(errorMsg);
            return;
          }
          setError(errorMsg);
          if (onError) onError(errorMsg);
        } catch {
          // ignore parse error
        }
      }
      eventSource.close();
    });

    return () => eventSource.close();
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
  const currentStep = (progress.current_step || '').toLowerCase();
  const isUploadingVariants = currentStep.includes('uploading_variants');

  // Map backend current_step → which checklist label is active.
  // Everything before the active step is marked completed; everything after is pending.
  const STEP_MAP: Record<string, string> = {
    uploading_variants: 'Uploading Variants',
    initializing: 'Variant Classification',
    classifying_variants: 'Variant Classification',
    annotating_variants: 'API Annotation',
    enriching_data: 'Data Enrichment',
    enriching_bigquery: 'Data Enrichment',
    generating_insights: 'Health & Wellness Analysis',
    generating_health_risks: 'Health & Wellness Analysis',
    generating_nutrition_traits: 'Food & Nutrition Insights',
    generating_drug_responses: 'Drug Response Prediction',
    generating_physical_traits: 'Physical Traits Analysis',
    generating_sports_performance: 'Sports & Fitness Insights',
    generating_cognitive_profiles: 'Intelligence Analysis',
    generating_personality_traits: 'Personality Traits',
    generating_ancestry_results: 'Ancestry & Origins',
    generating_carrier_status: 'Carrier Status Assessment',
    generating_wellness_metrics: 'Wellness Reports',
    generating_methylation_profiles: 'Methylation Pathways',
    generating_detox_profiles: 'Detoxification Analysis',
    generating_rare_mutations: 'Report Generation',
    generating_uncommon_mutations: 'Report Generation',
    completed: '',
  };

  const ORDERED_STEPS = [
    'Uploading Variants',
    'Variant Classification',
    'API Annotation',
    'Data Enrichment',
    'Health & Wellness Analysis',
    'Food & Nutrition Insights',
    'Drug Response Prediction',
    'Physical Traits Analysis',
    'Sports & Fitness Insights',
    'Intelligence Analysis',
    'Personality Traits',
    'Ancestry & Origins',
    'Carrier Status Assessment',
    'Wellness Reports',
    'Methylation Pathways',
    'Detoxification Analysis',
    'Report Generation',
  ];

  const activeStepLabel = currentStep === 'completed'
    ? ''
    : (STEP_MAP[currentStep] ?? ORDERED_STEPS[1]);
  const activeIdx = ORDERED_STEPS.indexOf(activeStepLabel);

  const getStepStatus = (label: string): 'completed' | 'current' | 'pending' => {
    if (currentStep === 'completed') return 'completed';
    const idx = ORDERED_STEPS.indexOf(label);
    if (idx < activeIdx) return 'completed';
    if (idx === activeIdx) return 'current';
    return 'pending';
  };
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
                  {isUploadingVariants 
                    ? 'Preparing Genetic Data'
                    : progress.status === 'pending' 
                      ? 'Preparing Genetic Analysis' 
                      : 'Analyzing Genetic Data'}
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
              {activeStepLabel || (currentStep === 'completed' ? 'Completed' : (progress.current_step || '').replace(/_/g, ' '))}
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
              { step: 'Uploading Variants', status: getStepStatus('Uploading Variants') },
              { step: 'Variant Classification', status: getStepStatus('Variant Classification') },
              { step: 'API Annotation', status: getStepStatus('API Annotation') },
              { step: 'Data Enrichment', status: getStepStatus('Data Enrichment') },
              { step: 'Health & Wellness Analysis', status: getStepStatus('Health & Wellness Analysis') },
              { step: 'Food & Nutrition Insights', status: getStepStatus('Food & Nutrition Insights') },
              { step: 'Drug Response Prediction', status: getStepStatus('Drug Response Prediction') },
              { step: 'Physical Traits Analysis', status: getStepStatus('Physical Traits Analysis') },
              { step: 'Sports & Fitness Insights', status: getStepStatus('Sports & Fitness Insights') },
              { step: 'Intelligence Analysis', status: getStepStatus('Intelligence Analysis') },
              { step: 'Personality Traits', status: getStepStatus('Personality Traits') },
              { step: 'Ancestry & Origins', status: getStepStatus('Ancestry & Origins') },
              { step: 'Carrier Status Assessment', status: getStepStatus('Carrier Status Assessment') },
              { step: 'Wellness Reports', status: getStepStatus('Wellness Reports') },
              { step: 'Methylation Pathways', status: getStepStatus('Methylation Pathways') },
              { step: 'Detoxification Analysis', status: getStepStatus('Detoxification Analysis') },
              { step: 'Report Generation', status: getStepStatus('Report Generation') },
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
                ) : isUploadingVariants ? (
                  <div>
                    <strong>Processing your upload...</strong> We're storing and deduplicating your genetic variants.
                    Analysis will begin automatically once processing is complete.
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