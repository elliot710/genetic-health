# Card Production Audit

End-to-end pipeline for all 14 dashboard card types: annotation sources → mapping logic → generator → DB table → serializer → frontend panel.

## Production Pipeline Table

| Category | Annotation Source | Mapping Type | Generator + AF Gate | DB Table | Serializer Dedup | Frontend Panel |
|---|---|---|---|---|---|---|
| health_risks | variant_mappings | Map-driven | `generate_health_risks()` + 0.05 | health_risks | condition | HealthPanel.tsx |
| drug_responses | variant_mappings | Bespoke | `generate_drug_responses()` custom loop | drug_responses | drug | DrugResponsesPanel.tsx |
| physical_traits | variant_mappings | Map-driven | `generate_physical_traits()` + 0.20 | physical_traits | trait_name | PhysicalTraitsPanel.tsx |
| nutrition_traits | variant_mappings | Map-driven | `generate_nutrition_traits()` + 0.20 | nutrition_traits | nutrient | FoodNutritionPanel.tsx |
| sports_performance | variant_mappings | Map-driven | `generate_sports_performance()` + 0.20 | sports_performance | category | SportsPanel.tsx |
| cognitive_profiles | variant_mappings | Map-driven | `generate_cognitive_profiles()` + 0.20 | cognitive_profiles | trait_name | IntelligencePanel.tsx |
| personality_traits | variant_mappings | Map-driven | `generate_personality_traits()` + 0.20 | personality_traits | trait | PersonalityPanel.tsx |
| ancestry_results | AIMs panel + Neanderthal markers | Bespoke | `generate_ancestry_results()` three-phase estimation | ancestry_results | population | AncestryPanel.tsx |
| carrier_status | variant_mappings + ClinVar-local | Bespoke | `generate_carrier_status()` custom discovery | carrier_status | condition | CarrierStatusPanel.tsx |
| wellness_metrics | variant_mappings | Map-driven | `generate_wellness_metrics()` + 0.20 | wellness_metrics | metric_name | WellnessPanel.tsx |
| methylation_profiles | variant_mappings | Map-driven | `generate_methylation_profiles()` + 0.20 | methylation_profiles | gene | MethylationPanel.tsx |
| detox_profiles | variant_mappings | Map-driven | `generate_detox_profiles()` + 0.20 | detoxification_profiles | gene | DetoxPanel.tsx |
| rare_mutations | ClinVar-local annotation | Bespoke | `generate_rare_mutations()` custom + AF < 0.01 hard gate | rare_mutations | mutation_name | RareMutationsPanel.tsx |
| uncommon_mutations | Ensembl VEP + ClinVar-local + gnomAD | Bespoke | `generate_uncommon_mutations()` custom + AF 0.001-0.05 gate | uncommon_mutations | mutation_name | UncommonMutationsPanel.tsx |

## Map-Driven Generation (9 categories)

All map-driven generators share `generate_from_maps()` (backend/services/insight_generators/base/map_generation.py:51) with rsid-based and gene-based matching:

- **Clinical panels** (health_risks): `max_population_af=0.05` (backend/services/insight_generators/health.py:86)
  - Hardest frequency gate (R3 hard cap: AF > 0.10 blocked unless ClinVar pathogenic; backend/services/insight_generators/base/map_generation.py:34)
  - Benign exclusion: only for clinical AF ≤ 0.05 (backend/services/insight_generators/base/map_generation.py:37-48)

- **Lifestyle panels** (nutrition, sports, cognitive, personality, physical, wellness, methylation, detox): `max_population_af=0.20`
  - Report benign-by-nature variants (e.g. ACTN3 MTHFR); benign-exclusion filter disabled (backend/services/insight_generators/base/map_generation.py:39-42)
  - Rarity hard cap still applies: benign ClinVar pathogenic bypasses soft ceiling only to 0.10 (backend/services/insight_generators/base/map_generation.py:122)

**Common gates across all map-driven:**
- Homozygous-reference skip (backend/services/insight_generators/base/map_generation.py:101)
- Benign classification veto (backend/services/insight_generators/base/map_generation.py:132)
- Allele verification: SNP alt-allele carry check + indel D/I code validation (backend/services/insight_generators/base/map_generation.py:145-199)
- Unknown variant/generic condition filters (backend/services/insight_generators/base/map_generation.py:214-243)

## Correctness Risks by Card

### Health Risks (health_risks)
- **Risk-level multiplier ceiling**: `assess_risk_level()` applies pathogenicity score scaling; check cap_risk_for_rarity() inheritance in gene-based path (health.py:68 calls cap_risk_for_rarity but from_rsid does not—asymmetry?)
- **ClinVar Clingen disputed filter**: X-linked variants with "Disputed"/"Refuted" ClinVar validity are silently dropped (health.py:27-34); confirm sex-linked condition filtering still applies (map_generation.py:140)
- **Composite pathogenicity score threading**: must use `info['_pathogenicity_score']` from build_variant_profiles, not annotation_data (health.py:35-41); None → "moderate" fallback risk level is correct per ARCH-06

### Drug Responses (drug_responses)
- **Custom benign gate weaker than health**: uses profile.is_benign check, skips placeholders but no AF gate; common CYP alleles (e.g. CYP2D6 rearrangements) may surface (drug_response.py:49-95)
- **Multiple drugs per gene**: loops over info['drugs'] list; dedup key is `gene_drug` pair, not rsid (drug_response.py:58-59, 83-84); confirm variant de-duplication does not drop legitimate multi-drug edges (e.g. CYP2C19 warfarin + clopidogrel)
- **No population frequency filter**: risk assessment may report common alleles if in pharmacogene mappings; intended for evidence-driven drug interactions (drug_response.py:61-63)

### Physical Traits (physical_traits)
- **Trait name dedups on trait_name alone**: same gene/variant reported under different categories will be folded (dashboard_serializers.py:154); check if "blonde hair" + "fair skin" from same variant are both desired or should split serializer
- **Confidence zygosity scaling**: het reduces confidence vs hom-alt (physical_traits.py:12, 21); validate that "high" from gene-match is not muted below "moderate"
- **Missing description fallback**: from_gene uses info['description'] (already in mapping) but from_rsid calls get_trait_description() (physical_traits.py:14, 26)—descriptions may differ for same trait from rsid vs gene path

### Nutrition Traits (nutrition_traits)
- **Metabolism type enum**: stored as string ('slow', 'fast', 'normal', 'deficient'); confirm variant_mappings values match schema and serializer assumptions (nutrition_traits.py:11-15, dashboard_serializers.py:79)
- **Sensitivity level boost**: applies boost_if_pathogenic() on top of zygosity_adjust (nutrition_traits.py:14, 26); high-pathogenicity rare variants may over-scale sensitivity (e.g. iron-metabolism ClinVar pathogenic → "extreme"?)
- **Dedup by nutrient alone**: if a nutrient (e.g. "Vitamin B12") has multiple metabolic pathways, only first is reported (dashboard_serializers.py:83)

### Sports Performance (sports_performance)
- **Category dedups on performance_category**: ACTN3 R/X polymorphism reports "endurance" vs "power" under same analysis; category-dedup favors first match only (dashboard_serializers.py:74)
- **Strand flip risk**: athletic variants are often microarray-friendly (common SNPs) but may be reported on minus strand; no strand-flip validation in generate_sports_performance() (sports.py:30-35 uses base generate_from_maps which validates alleles)
- **Training advice**: stored as free-text from mapping; no schema validation; lipstick configs or typos won't be caught at generation time (sports_performance.py in dashboard_traits.py:44)

### Cognitive Profiles (cognitive_profiles)
- **Dedup by trait_name (cognitive_domain)**: percentile scores may vary by dataset; only first variant's percentile reported per domain (dashboard_serializers.py:167)
- **Genetic score parsing**: `genetic_score` is a string ("high", "moderate", "low") but percentile is integer (cognitive_profiles.py:52-55); serializer maps string to percentile only if both present (dashboard_serializers.py:162)
- **Enhancement suggestions array**: if stored as JSON list vs single string, serializer joins with '; ' or passes through; confirm variant_mappings consistency (cognitive.py uses base from_rsid/from_gene; dashboard_serializers.py:164-165 handles both)

### Personality Traits (personality_traits)
- **Score mapping hard-coded**: genetic_tendency → score conversion is frontend logic (dashboard_serializers.py:173: moderate=70, high=85, default=55); backend does not validate genetic_tendency enum (personality_traits.py:63)
- **Marker fallback fragile**: gene field falls back to "Multiple markers" if associated_variants empty (dashboard_serializers.py:175-176); single-variant personality traits may show generic marker text
- **Behavioral insights handling**: stored as JSON list or string; serializer picks first as description and passes list as characteristics (dashboard_serializers.py:178-180); inconsistent field types risk silent data loss

### Ancestry Results (ancestry_results)
- **Three-phase estimation coupling**: super-population → sub-population (if EUR > 50%) → Neanderthal (ancestry.py:5-17); all three are independent SQL writes; if phase 2 fails, user sees phase 1+3 only (no error signaling)
- **AIMs panel in-memory caching**: single server-lifetime dict; updated panels require server restart (ancestry.py:18); stale panels not detected (test with fresh gnomAD data)
- **Haplogroup confidence**: maternal/paternal haplogroups lack confidence scores in schema; ancestry_results.py:81-82 stores raw JSON; frontend may display unvetted mtDNA/Y calls

### Carrier Status (carrier_status)
- **Dual discovery paths**: registry-based (variant_mappings) + ClinVar-local annotation-based (carrier.py:106-211); dedup by condition name only (carrier.py:116-117, 192-194); same disease from rsid + ClinVar may collapse incorrectly
- **Allele classification uncertainty**: _classify_carrier_status() maps user genotype to "affected"/"carrier"/"unaffected" using ref/alt alleles; D/I indels with unknown direction return 'carrier' (fallback; carrier.py:36-37), hiding ambiguity
- **Inheritance pattern inference**: inferred from condition names ("dominant", "x-linked"; carrier.py:197-200); no ClinVar inheritance_pattern metadata used, prone to substring false-positives (e.g. "metabolic disorder" includes "dominant"?)

### Wellness Metrics (wellness_metrics)
- **Dual serialization**: returns tuple (metabolic dict, wellness_traits list; dashboard_serializers.py:128-144); frontend consumes both separately; dedup key is metric_name for both, risk of field name collision
- **Optimization score string/enum**: stored as string in model but serializer passes as confidence string ("Medium" default); no int/float normalization, may confuse frontend consumers (dashboard_serializers.py:138)
- **Lifestyle recommendations**: stored as JSON list; empty recommendations silently become "Standard healthy lifestyle" in uncommon_mutations path, not wellness (wellness.py uses base generate_from_maps behavior)

### Methylation Profiles (methylation_profiles)
- **Gene dedup collapses variants**: MTHFR C677T + A1298C (separate pathways, same gene) only first is reported (dashboard_serializers.py:101)
- **Methylation capacity enum**: values stored as string (from variant_mappings); no schema validation for 'normal'/'reduced'/'impaired' enum (methylation_profiles.py:114)
- **Supplement recommendations**: free-text from mappings; no dosing/interaction validation; high-pathogenicity methylation cycle variants may over-recommend folate (methylation.py uses base generate_from_maps boost_if_pathogenic)

### Detoxification Profiles (detox_profiles)
- **Detox phase enum**: "phase1"/"phase2"/"phase3" hardcoded in schema; no CYP family specificity (e.g. CYP2C9 phase1 vs CYP2A6 phase1 are conflated; detoxification_profiles.py:123)
- **Capacity scoring**: "normal"/"slow"/"fast"/"impaired"; no quantitative DPYD/NAT2/etc scoring from annotation; variant_mappings provides template only (detox.py:37-41)
- **Toxin sensitivity vs pathogenicity**: toxin_sensitivity is independent field from pathogenicity_score; high-pathogenicity detox variants may report "normal" sensitivity if mapping predates pathogenicity data (detox.py uses base generate_from_maps)

### Rare Mutations (rare_mutations)
- **Frequency hard gate strict**: AF < 0.01 enforced; variants with unknown frequency (None) allowed only if ClinVar explicitly pathogenic (rare_mutations.py:70-73); legitimate rare private variants may be under-reported
- **ClinVar clinical significance enum inflated**: "pathogenic"/"likely_pathogenic"/"conflicting"/"risk_factor"/"uncertain" mapped from raw ClinVar text parsing (rare_mutations.py:106-124); case-sensitivity and synonym handling fragile (e.g. "Likely Pathogenic" vs "likely_pathogenic")
- **Indel evidence threshold**: homozygous D/I indels skip allele verification and require "multiple submitters" or "expert panel" ClinVar review status (rare_mutations.py:179-188); het D/I bypasses evidence gate entirely, false positives possible

### Uncommon Mutations (uncommon_mutations)
- **Functional consequence filter strict**: only 11 VEP consequence types allowed (uncommon_mutations.py:15-20); splice_region_variant included but splice_polypyrimidine_tract_variant excluded; confirm mappings use standardized VEP terms
- **Frequency range 0.001-0.05**: variants outside gate are silently dropped (uncommon_mutations.py:120); AF boundary variants at exactly 0.05 vs 0.051 behave differently despite clinical similarity
- **AF cap enforcement fragile**: extract_frequency() may return None for multi-allelic sites or missing gnomAD data; None frequency causes variant rejection, under-reporting of novel synonymous alleles in functional genes (uncommon_mutations.py:120)

## Data Flow Correctness Checklist

- [ ] **Variant mappings freshness**: confirm `variant_mappings` table is current; if stale, all 9 map-driven cards report outdated associations
- [ ] **Annotation cache population**: ensure `clinvar_local_data` SQLite cache is built before any analysis; missing cache falls back to slow variant-by-variant ClinVar query (rare/uncommon/carrier discovery)
- [ ] **Sex-linked filtering**: verify `inferred_sex` is correctly populated for X-linked conditions (health, carrier, rare); missing/null sex defaults to unsafe "unknown" behavior (map_generation.py:140, carrier.py:201, rare_mutations.py:194)
- [ ] **Dedup collision risk**: serializers dedup by single key per card; verify no legitimate multi-variant/multi-gene findings collapse (e.g. same nutrient from different pathways, same personality domain from different genes)
- [ ] **AF gate consistency**: health=0.05, drug/carrier custom (5% or no gate), lifestyle=0.20, rare<0.01, uncommon=0.001-0.05; minor-allele safeguard (R3) 0.10 hard cap applies only to pathogenic ClinVar bypass, not all cards uniformly
- [ ] **Benign exclusion asymmetry**: clinical panels only (AF ≤ 0.05) exclude benign; lifestyle panels allow benign-by-nature variants; drug_response custom gate may report benign pharmacogenes (intended per pharmacogenomics logic)
