CREATE TABLE IF NOT EXISTS annotation_source_configs (
    id SERIAL PRIMARY KEY,
    source_name VARCHAR UNIQUE NOT NULL,
    display_name VARCHAR NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    description VARCHAR,
    rate_limit FLOAT,
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_annotation_source_configs_source_name ON annotation_source_configs (source_name);
INSERT INTO annotation_source_configs (source_name, display_name, is_enabled, description, rate_limit, priority) VALUES
('ensembl', 'Ensembl VEP', true, 'Variant Effect Predictor', 15.0, 1),
('clinvar', 'ClinVar (NCBI)', true, 'Clinical significance classifications', 10.0, 2),
('clinpgx', 'ClinPGx', true, 'Pharmacogenomic annotations', 1.0, 3),
('snpedia', 'SNPedia', true, 'Community-curated variant wiki', 2.0, 4)
ON CONFLICT (source_name) DO NOTHING;
SELECT source_name, display_name, is_enabled FROM annotation_source_configs ORDER BY priority;
