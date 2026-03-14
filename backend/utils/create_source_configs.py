"""Create annotation_source_configs table."""
from sqlalchemy import create_engine, text
import os

engine = create_engine(os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@postgres:5432/genetic_health_db'))

with engine.connect() as conn:
    result = conn.execute(text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'annotation_source_configs')"))
    exists = result.scalar()
    print(f'Table exists: {exists}')
    
    if not exists:
        conn.execute(text("""
            CREATE TABLE annotation_source_configs (
                id SERIAL PRIMARY KEY,
                source_name VARCHAR UNIQUE NOT NULL,
                display_name VARCHAR NOT NULL,
                is_enabled BOOLEAN NOT NULL DEFAULT true,
                description VARCHAR,
                rate_limit FLOAT,
                priority INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ
            )
        """))
        conn.execute(text("CREATE UNIQUE INDEX ix_annotation_source_configs_source_name ON annotation_source_configs (source_name)"))
        conn.execute(text("""
            INSERT INTO annotation_source_configs (source_name, display_name, is_enabled, description, rate_limit, priority) VALUES
            ('ensembl', 'Ensembl VEP', true, 'Variant Effect Predictor — gene consequences, transcript impact, regulatory annotations', 15.0, 1),
            ('clinvar', 'ClinVar (NCBI)', true, 'Clinical significance classifications, disease associations, review status', 10.0, 2),
            ('clinpgx', 'ClinPGx', true, 'Pharmacogenomic annotations — drug-gene interactions and dosing guidelines', 1.0, 3),
            ('snpedia', 'SNPedia', true, 'Community-curated variant wiki — genotype-phenotype associations and research summaries', 2.0, 4)
        """))
        conn.commit()
        print('Table created and seeded successfully')
    else:
        result = conn.execute(text('SELECT source_name, is_enabled FROM annotation_source_configs ORDER BY priority'))
        for row in result:
            print(f'  {row[0]}: enabled={row[1]}')
