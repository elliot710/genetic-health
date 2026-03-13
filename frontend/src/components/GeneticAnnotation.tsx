import React, { useState } from 'react';

interface EnsemblAnnotation {
  error?: string;
  most_severe_consequence?: string;
  minor_allele?: string;
  clinical_significance?: string[];
}

interface ClinvarAnnotation {
  error?: string;
  found_entries?: number;
  ids?: string[];
}

interface SnpediaAnnotation {
  message?: string;
  magnitude?: number;
  summary?: string;
  frequency?: number;
  clinical_significance?: string;
}

interface ClinpgxAnnotation {
  message?: string;
  function?: string;
  drugs?: string[];
  clinical_annotation?: string;
}

interface AnnotationData {
  rsid: string;
  gene: string | null;
  annotations: {
    ensembl?: EnsemblAnnotation;
    clinvar?: ClinvarAnnotation;
    snpedia?: SnpediaAnnotation;
    clinpgx?: ClinpgxAnnotation;
  };
  error?: string | null;
}

interface GeneticAnnotationProps {
  token: string;
}

export default function GeneticAnnotation({ token }: GeneticAnnotationProps) {
  const [rsid, setRsid] = useState('');
  const [gene, setGene] = useState('');
  const [annotation, setAnnotation] = useState<AnnotationData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleAnnotate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rsid.trim()) {
      setError('Please enter an rsID');
      return;
    }

    setLoading(true);
    setError('');
    setAnnotation(null);

    try {
      const response = await fetch('/api/annotations/variant', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          rsid: rsid.trim(),
          gene: gene.trim() || null,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setAnnotation(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch annotation');
    } finally {
      setLoading(false);
    }
  };

  const exampleVariants = [
    { rsid: 'rs5443', gene: 'GNB3', description: 'Sildenafil response variant' },
    { rsid: 'rs11615', gene: 'ERCC1', description: 'Platinum chemotherapy response' },
    { rsid: 'rs1045642', gene: 'ABCB1', description: 'Drug transport variant' }
  ];

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-2xl font-bold text-gray-900 mb-6">
          Genetic Variant Annotation
        </h2>
        
        {/* Input Form */}
        <form onSubmit={handleAnnotate} className="mb-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label htmlFor="rsid" className="block text-sm font-medium text-gray-700 mb-2">
                rsID (required)
              </label>
              <input
                type="text"
                id="rsid"
                value={rsid}
                onChange={(e) => setRsid(e.target.value)}
                placeholder="e.g., rs5443"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label htmlFor="gene" className="block text-sm font-medium text-gray-700 mb-2">
                Gene (optional)
              </label>
              <input
                type="text"
                id="gene"
                value={gene}
                onChange={(e) => setGene(e.target.value)}
                placeholder="e.g., GNB3"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
          
          <button
            type="submit"
            disabled={loading}
            className="bg-blue-600 text-white px-6 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Annotating...' : 'Annotate Variant'}
          </button>
        </form>

        {/* Example Variants */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-3">Example Variants:</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {exampleVariants.map((variant) => (
              <button
                key={variant.rsid}
                onClick={() => {
                  setRsid(variant.rsid);
                  setGene(variant.gene);
                }}
                className="p-3 border border-gray-200 rounded-md hover:bg-gray-50 text-left"
              >
                <div className="font-medium text-blue-600">{variant.rsid}</div>
                <div className="text-sm text-gray-600">{variant.gene}</div>
                <div className="text-xs text-gray-500">{variant.description}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Error Display */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-md p-4 mb-6">
            <div className="text-red-700">{error}</div>
          </div>
        )}

        {/* Annotation Results */}
        {annotation && (
          <div className="space-y-6">
            <div className="bg-gray-50 rounded-lg p-4">
              <h3 className="text-xl font-semibold text-gray-900 mb-4">
                Annotation Results for {annotation.rsid}
                {annotation.gene && ` (${annotation.gene})`}
              </h3>

              {/* Ensembl Data */}
              {annotation.annotations.ensembl && !annotation.annotations.ensembl.error && (
                <div className="mb-6">
                  <h4 className="text-lg font-medium text-gray-800 mb-2 flex items-center">
                    <span className="w-3 h-3 bg-blue-500 rounded-full mr-2"></span>
                    Ensembl
                  </h4>
                  <div className="bg-white rounded-md p-4 space-y-2">
                    <div><strong>Consequence:</strong> {annotation.annotations.ensembl.most_severe_consequence}</div>
                    {annotation.annotations.ensembl.minor_allele && (
                      <div><strong>Minor Allele:</strong> {annotation.annotations.ensembl.minor_allele}</div>
                    )}
                    {(annotation.annotations.ensembl.clinical_significance?.length ?? 0) > 0 && (
                      <div>
                        <strong>Clinical Significance:</strong>{' '}
                        {annotation.annotations.ensembl.clinical_significance!.join(', ')}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* ClinVar Data */}
              {annotation.annotations.clinvar && !annotation.annotations.clinvar.error && (
                <div className="mb-6">
                  <h4 className="text-lg font-medium text-gray-800 mb-2 flex items-center">
                    <span className="w-3 h-3 bg-green-500 rounded-full mr-2"></span>
                    ClinVar
                  </h4>
                  <div className="bg-white rounded-md p-4">
                    <div><strong>Found Entries:</strong> {annotation.annotations.clinvar.found_entries}</div>
                    {(annotation.annotations.clinvar.found_entries ?? 0) > 0 && (
                      <div className="text-sm text-gray-600 mt-1">
                        ClinVar IDs: {annotation.annotations.clinvar.ids?.join(', ')}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* SNPedia Data */}
              {annotation.annotations.snpedia && !annotation.annotations.snpedia.message && (
                <div className="mb-6">
                  <h4 className="text-lg font-medium text-gray-800 mb-2 flex items-center">
                    <span className="w-3 h-3 bg-purple-500 rounded-full mr-2"></span>
                    SNPedia
                  </h4>
                  <div className="bg-white rounded-md p-4 space-y-2">
                    <div><strong>Magnitude:</strong> {annotation.annotations.snpedia.magnitude}/5</div>
                    <div><strong>Summary:</strong> {annotation.annotations.snpedia.summary}</div>
                    <div><strong>Frequency:</strong> {((annotation.annotations.snpedia.frequency ?? 0) * 100).toFixed(1)}%</div>
                    <div><strong>Clinical Significance:</strong> {annotation.annotations.snpedia.clinical_significance}</div>
                  </div>
                </div>
              )}

              {/* ClinPGx Data */}
              {annotation.annotations.clinpgx && !annotation.annotations.clinpgx.message && (
                <div className="mb-6">
                  <h4 className="text-lg font-medium text-gray-800 mb-2 flex items-center">
                    <span className="w-3 h-3 bg-red-500 rounded-full mr-2"></span>
                    ClinPGx
                  </h4>
                  <div className="bg-white rounded-md p-4 space-y-2">
                    <div><strong>Function:</strong> {annotation.annotations.clinpgx.function}</div>
                    <div><strong>Associated Drugs:</strong> {annotation.annotations.clinpgx.drugs?.join(', ')}</div>
                    <div><strong>Clinical Annotation:</strong> {annotation.annotations.clinpgx.clinical_annotation}</div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}