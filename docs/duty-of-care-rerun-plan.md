# Duty-of-care plan: re-run corrected analyses and notify affected users

The analysis-correctness fixes (U2–U7 on `refactor/analysis-correctness`) change
some stored health-risk and drug-response verdicts. Production accounts are a mix
of test and real users, so some real people saw a verdict that the corrected logic
now produces differently. This plan is how we handle that responsibly.

This is an **out-of-band operator procedure**, not a pipeline step. Nothing here
runs automatically and no user is contacted by the tooling.

## Tooling

`backend/scripts/rerun_corrected_analyses.py`:

```bash
docker exec dna_toolkit-backend-1 \
  uv run python -m backend.scripts.rerun_corrected_analyses <analysis_id> [<analysis_id> ...]
```

For each analysis it: snapshots the currently stored verdicts, re-generates them
under the corrected logic (via the existing `regenerate_insights` dispatcher, which
persists the corrected rows), reads them back, and prints a **PII-free** report of
material changes:

```
analysis 128: 2 material change(s)
  [health_risk] Hereditary haemochromatosis · risk_level: 'high' -> 'moderate'
  [drug_response] CYP2D6 / codeine · response_type: 'normal' -> 'poor'
```

The report contains only: analysis id, condition/gene/drug reference labels, and
old→new verdict strings. It never contains genotype, alleles, rsids, names, or
emails. Re-running an analysis with no material change prints `no material change`.

## Procedure

1. **Backup first.** Take a database backup before running (the re-run persists the
   corrected verdicts). Confirm the backup restores.
2. **Scope the affected set.** Identify the analyses to re-run. Start with real
   (non-test) accounts. Keep the analysis-id → user mapping in a separate,
   access-controlled place — it is not in the report and must not be pasted into
   shared channels.
3. **Run per analysis**, off-peak. Capture the printed reports.
4. **Classify materiality.** A change is user-relevant when a `risk_level` or
   `response_type` flips, or a `pathogenicity` classification crosses the
   benign ↔ uncertain ↔ pathogenic boundary. Cosmetic or ordering-only differences
   are not material (the tool already reports only verdict-field changes).
5. **Notify only affected real users** (see wording below). Do not notify test
   accounts.
6. **Record** which analyses were re-run and which users were notified, for audit.

## Notification

- **Channel:** the user's registered email (the account's own verified address).
  One message per affected user. No third party is contacted.
- **Who:** only real users whose analysis showed a material change. Test accounts,
  and analyses with no material change, are excluded.
- **Tone:** factual, non-alarming, educational-framing consistent with the product
  (this is not a medical device; results are informational).

Suggested wording (adapt per case; keep it specific to what changed without
restating raw genetic data):

> Subject: An update to your genetic insights
>
> We improved how we calculate part of your genetic analysis and re-ran yours. As
> a result, one or more of your previous results has changed. Your dashboard now
> shows the updated, more accurate information.
>
> As a reminder, these insights are for educational purposes only and are not
> medical advice. If a result concerns you, please discuss it with a qualified
> healthcare professional.
>
> You can view your updated results, export your data, or delete your account at
> any time from your account settings.

## Data protection

- Genetic data is special-category personal data (EU). The report is PII-free by
  construction; keep the analysis-id → user mapping access-controlled.
- The re-run only touches the target analysis's own insight rows; shared reference
  caches are not modified (verified by the U7 cascade tests and the regeneration
  path, which reads cached annotations rather than rewriting them).
- Self-service export and deletion (U7) remain available to every user throughout.
