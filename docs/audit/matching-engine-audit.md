# Variant-Matching Engine Gate Audit

## Primary Loop Gates (generate_from_maps)

| Order | Gate | File:Line | Condition | False Positive Prevented |
|-------|------|-----------|-----------|------------------------|
| 1 | No-call genotype skip | backend/services/insight_generators/base/alleles.py:193–198 | `is_no_call_genotype(genotype)` tests for '--', '00', 'NC', './.', '.\|.' | Genotyping failures reported as findings |
| 2 | Homozygous-reference skip | backend/services/insight_generators/base/alleles.py:234–275 | `is_homozygous_reference(genotype, effective_ref, alt_allele)` verifies both alleles match ref (consumer indel codes D/I interpreted via ref/alt lengths) | Risk alleles in non-carriers (user has only reference) |
| 3 | Population-frequency gate (soft ceiling) | backend/services/insight_generators/base/map_generation.py:107–123 | `max_population_af is not None AND _var_freq > max_population_af` (health=0.05, lifestyle=0.20) | Common variants reported as rare findings |
| 4 | ClinVar pathogenic bypass | backend/services/insight_generators/base/map_generation.py:116–122 | `'pathogenic' in _cv_sigs` overrides soft ceiling _only if_ `_var_freq <= _PATHOGENIC_AF_HARD_CAP (0.10)` | Common alleles (>10% AF) wrongly labeled pathogenic |
| 5 | ClinVar-benign exclusion (rsid) | backend/services/insight_generators/base/clinical.py:45–65 | `is_clinvar_benign(annotation_result)` returns True when all sources agree benign AND no computational pathogenicity | Benign variants in manual mappings or ClinVar reclassifications |
| 6 | Sex-linked condition filter | backend/services/insight_generators/base/clinical.py:82–96 | `should_skip_sex_linked()` skips male-only/female-only conditions on wrong sex (e.g. Rett syndrome in males on X chr) | Sex-inappropriate condition assignments |
| 7 | SNP allele verification | backend/services/insight_generators/base/map_generation.py:146–171 | For SNPs: genotype must contain at least one alt allele from annotation; strand-flip (ACGT↔TGCA) checked as fallback | User's genotype doesn't carry the risk allele |
| 8 | Indel D/I code verification | backend/services/insight_generators/base/map_generation.py:173–199 | For D/I codes: must match direction (D=shorter, I=longer via `indel_d_is_ref()`); homozygous D or D skipped if direction unknown (BUG-15) | D/I orientation mismatches; homozygous indel ambiguity (e.g. rs61749708 "II" = hom-ref) |
| 9 | Unknown variant suppression | backend/services/insight_generators/base/map_generation.py:214–222 | Condition name 'unknown variant' or 'unknown' skipped unless composite pathogenicity ≥0.60 | Auto-categorizer failures where no condition resolved |
| 10 | Generic "[Gene] variant" suppression | backend/services/insight_generators/base/map_generation.py:230–243 | Regex `r'\bvariant\s*$'` (e.g. "UBR4 variant") skipped unless ClinVar clinical_significance exists OR composite score ≥0.75 + evidence_count ≥2 | AlphaMissense coordinate mismatches; intergenic fallback names |
| 11 | Benign classification exclusion (clinical AF only) | backend/services/insight_generators/base/map_generation.py:37–48, 247–248 | `_should_exclude_benign()` skips benign/likely_benign ONLY when `max_population_af <= 0.05` (clinical gating); lifestyle panels (0.20) exempt | Benign traits wrongly filtered from lifestyle panels |
| 12 | Unscored variant exclusion (clinical panels) | backend/services/insight_generators/base/map_generation.py:249–256 | For clinical (health/carrier/drug, max_population_af ≤0.05): skip if no pathogenicity_score dict AND no clinical_significance string (RC-7) | Unvalidated variants surfaced as health risks |
| 13 | ClinVar-benign exclusion (gene path) | backend/services/insight_generators/base/clinical.py:45–65 | Same as gate 5, applied during gene-based matching (line 269) | Benign variants in gene discovery path |

## Post-Loop Risk Adjustment Gates

| Order | Gate | File:Line | Condition | False Positive Prevented |
|-------|------|-----------|-----------|------------------------|
| 14 | Risk-level rarity cap | backend/services/insight_generators/base/zygosity.py:135–152 | `cap_risk_for_rarity()`: risk escalated to 'high'/'very_high' capped at 'moderate' if `population_frequency > _CLINICAL_AF_CEILING (0.05)` | High risk assigned to common variants |

## Bespoke Matcher Gates

### Rare Mutations (rare_mutations.py)

| Order | Gate | File:Line | Condition | False Positive Prevented |
|-------|------|-----------|-----------|------------------------|
| R1 | ClinVar data requirement | backend/services/insight_generators/rare_mutations.py:33–37 | Must have ClinVar local OR ClinVar API data; skip otherwise | Non-clinically-catalogued variants |
| R2 | Rarity gate (<1%) | backend/services/insight_generators/rare_mutations.py:70–74 | `freq is not None AND freq > 0.01` skips; unknown freq allowed with benign handling (R4) | Common variants reported as rare findings |
| R3 | Benign classification skip | backend/services/insight_generators/rare_mutations.py:165–167 | `clinical_significance in ('benign', 'likely_benign')` skipped | Non-clinically-relevant benign mutations |
| R4 | Unknown frequency + non-pathogenic skip | backend/services/insight_generators/rare_mutations.py:169–173 | If `freq is None` AND not ('pathogenic'/'likely_pathogenic'), skip (pathogenic/likely_pathogenic retained without frequency) | Ambiguous classification variants without frequency anchor |
| R5 | Indel without strong evidence skip | backend/services/insight_generators/rare_mutations.py:178–188 | Indel genotype with unknown freq requires 'multiple submitters' OR 'expert panel' OR 'practice guideline' in review_statuses | Ambiguous indel D/I codes without multi-source validation |
| R6 | X-linked carrier female filter | backend/services/insight_generators/rare_mutations.py:190–209 | Heterozygous female on X-linked variant marked as carrier, not affected; heterozygous male on X skipped (genotyping artifact) | False affected status in X-linked carriers |

### Carrier Status (carrier.py)

| Order | Gate | File:Line | Condition | False Positive Prevented |
|-------|------|-----------|-----------|------------------------|
| C1 | Common variant exclusion (rsid) | backend/services/insight_generators/carrier.py:110–113 | `_freq > 0.05` skipped for registry matches (no ClinVar pathogenic bypass documented) | Common alleles in carrier definitions |
| C2 | Benign exclusion (rsid) | backend/services/insight_generators/carrier.py:108–109 | `is_clinvar_benign()` skipped for rsid registry matches (RC-5) | Confirmed benign variants in carrier registry |
| C3 | Unaffected status skip (gene discovery) | backend/services/insight_generators/carrier.py:168–173 | `_classify_carrier_status()` returns 'unaffected' → skip entry | Unaffected genotypes reported as carriers |

### Drug Response (drug_response.py)

| Order | Gate | File:Line | Condition | False Positive Prevented |
|-------|------|-----------|-----------|------------------------|
| D1 | Benign exclusion (rsid & gene) | backend/services/insight_generators/drug_response.py:52–53, 76–77 | `is_clinvar_benign()` skipped for both rsid and gene matches | Drug warnings on confirmed-benign variants |

---

## Residual Risk Notes

The matching engine enforces rarity via two complementary mechanisms: a soft per-category population-frequency ceiling (health 0.05, lifestyle 0.20) that is bypassed only by ClinVar-pathogenic labels, and a hard-cap on that bypass (_PATHOGENIC_AF_HARD_CAP = 0.10) that prevents contradictory "pathogenic >10% AF" classifications from surfacing. Allele verification is strand-aware for SNPs and direction-verified for consumer indel codes (D/I); homozygous indel codes without direction data are conservatively skipped. Benign-classification filtering applies only to clinical panels (AF ≤0.05) to preserve lifestyle trait reporting. For rare mutations, unknown population frequency is tolerated when ClinVar pathogenic/likely_pathogenic classification exists, but required when classification is ambiguous. The engine does not gate on whether a variant is in linkage disequilibrium with the actual causal variant, so rare haplotypes tagged by common proxy SNPs can be incorrectly reported; this is mitigated only by the AF hard-cap and would require explicit LD-aware gating to fully resolve.

