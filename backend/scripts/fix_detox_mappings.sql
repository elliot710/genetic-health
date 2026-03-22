-- Add Phase III transporter gene mappings
INSERT INTO variant_mappings (category, map_type, key, data, is_active) VALUES
('detox', 'rsid', 'rs1045642', '{"phase": "phase3", "gene": "ABCB1", "capacity": "variant_detected", "sensitivity": "moderate", "recommendations": ["ABCB1/MDR1 drug efflux transporter", "May affect drug absorption and distribution", "Discuss medication adjustments with physician"]}', true),
('detox', 'rsid', 'rs717620', '{"phase": "phase3", "gene": "ABCC2", "capacity": "variant_detected", "sensitivity": "moderate", "recommendations": ["ABCC2/MRP2 organic anion transporter", "May affect bilirubin and drug excretion", "Monitor liver function markers"]}', true),
('detox', 'rsid', 'rs4149056', '{"phase": "phase3", "gene": "SLCO1B1", "capacity": "variant_detected", "sensitivity": "high", "recommendations": ["SLCO1B1 hepatic uptake transporter", "Key for statin metabolism - myopathy risk", "Consider lower statin doses or alternatives"]}', true),
('detox', 'rsid', 'rs1751034', '{"phase": "phase3", "gene": "ABCC4", "capacity": "variant_detected", "sensitivity": "moderate", "recommendations": ["ABCC4/MRP4 drug efflux transporter", "Affects nucleoside analog drug levels", "Monitor tenofovir and similar drug response"]}', true)
ON CONFLICT DO NOTHING;

-- Also add Phase III gene-map entries so gene-based matching works too
INSERT INTO variant_mappings (category, map_type, key, data, is_active) VALUES
('detox', 'gene', 'ABCB1', '{"phase": "phase3", "gene": "ABCB1", "capacity": "variant_detected", "sensitivity": "moderate", "recommendations": ["ABCB1/MDR1 drug efflux transporter", "May affect drug absorption and distribution", "Discuss medication adjustments with physician"]}', true),
('detox', 'gene', 'ABCC2', '{"phase": "phase3", "gene": "ABCC2", "capacity": "variant_detected", "sensitivity": "moderate", "recommendations": ["ABCC2/MRP2 organic anion transporter", "May affect bilirubin and drug excretion", "Monitor liver function markers"]}', true),
('detox', 'gene', 'SLCO1B1', '{"phase": "phase3", "gene": "SLCO1B1", "capacity": "variant_detected", "sensitivity": "high", "recommendations": ["SLCO1B1 hepatic uptake transporter", "Key for statin metabolism - myopathy risk", "Consider lower statin doses or alternatives"]}', true),
('detox', 'gene', 'ABCC4', '{"phase": "phase3", "gene": "ABCC4", "capacity": "variant_detected", "sensitivity": "moderate", "recommendations": ["ABCC4/MRP4 drug efflux transporter", "Affects nucleoside analog drug levels", "Monitor tenofovir and similar drug response"]}', true)
ON CONFLICT DO NOTHING;

-- Fix auto-discovered genes with proper phase assignments
-- Phase I: CYP enzymes (oxidation), ALDH2 (oxidation), EPHX1 (hydrolysis), NQO1 (reduction), PON1 (hydrolysis)
UPDATE variant_mappings SET data = jsonb_set(jsonb_set(data::jsonb, '{phase}', '"phase1"'), '{capacity}', '"variable"')::json
WHERE category = 'detox' AND map_type = 'gene' AND key IN ('CYP1A1', 'CYP1A2', 'CYP1B1', 'CYP2A6', 'CYP2E1', 'ALDH2', 'EPHX1', 'NQO1', 'PON1')
AND data->>'phase' = 'variable';

-- Phase II: NAT1/NAT2 (acetylation), GSTM1/GSTP1 (glutathione conjugation)
UPDATE variant_mappings SET data = jsonb_set(jsonb_set(data::jsonb, '{phase}', '"phase2"'), '{capacity}', '"variable"')::json
WHERE category = 'detox' AND map_type = 'gene' AND key IN ('NAT1', 'NAT2', 'GSTM1', 'GSTP1')
AND data->>'phase' = 'variable';

-- Antioxidant: GPX1 (glutathione peroxidase), SOD2 (superoxide dismutase), CAT (catalase)
UPDATE variant_mappings SET data = jsonb_set(jsonb_set(data::jsonb, '{phase}', '"antioxidant"'), '{capacity}', '"variable"')::json
WHERE category = 'detox' AND map_type = 'gene' AND key IN ('GPX1', 'SOD2', 'CAT')
AND data->>'phase' = 'variable';

-- Backfill analysis_variants.genotype from info.original_genotype
UPDATE analysis_variants
SET genotype = info->>'original_genotype'
WHERE genotype IS NULL AND info->>'original_genotype' IS NOT NULL AND info->>'original_genotype' != '';

-- Verify results
SELECT 'Phase III mappings:' as check, COUNT(*) as count FROM variant_mappings WHERE category='detox' AND data->>'phase'='phase3';
SELECT 'Remaining variable:' as check, COUNT(*) as count FROM variant_mappings WHERE category='detox' AND data->>'phase'='variable';
SELECT 'Genotypes backfilled:' as check, COUNT(*) as count FROM analysis_variants WHERE genotype IS NOT NULL AND genotype != '';
