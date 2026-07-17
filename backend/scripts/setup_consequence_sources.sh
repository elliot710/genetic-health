#!/usr/bin/env bash
# Download + build the offline molecular-consequence sources (U6).
#
# Sources (all commercial-safe, GRCh37 to match the consumer-array marker set):
#   MANE Select     ~1 MB    gene -> canonical transcript
#   dbSNP b151 VCF  ~16 GB   rsid -> molecular consequence (function-class flags)
#   Ensembl VEP     ~18 GB   offline cache + tool (position-based consequence)
#   SnpEff          ~1 GB    LGPL annotator + GRCh37.75 genome db
#
# Idempotent: skips a download whose target already exists. `--check` resolves
# every URL (HEAD) without downloading. Run on the machine that holds the
# data_sources/ volume (the worker box). ~35 GB disk + VEP(Perl)/SnpEff(Java).
#
# Usage:
#   bash backend/scripts/setup_consequence_sources.sh            # download + build MANE/dbSNP caches
#   bash backend/scripts/setup_consequence_sources.sh --check    # dry-run: verify URLs only
set -euo pipefail

DATA=data_sources
MANE_URL="https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/current/MANE.GRCh38.v1.5.summary.txt.gz"
DBSNP_URL="https://ftp.ncbi.nlm.nih.gov/snp/organisms/human_9606_b151_GRCh37p13/VCF/00-All.vcf.gz"
VEP_URL="https://ftp.ensembl.org/pub/release-113/variation/indexed_vep_cache/homo_sapiens_vep_113_GRCh37.tar.gz"
SNPEFF_URL="https://snpeff.blob.core.windows.net/versions/snpEff_latest_core.zip"

CHECK="${1:-}"

_head() { curl -sIL --connect-timeout 15 "$1" | grep -iE "^HTTP/|content-length" | tail -2; }
_get()  { # url dest
  if [ -s "$2" ]; then echo "  exists, skip: $2"; return; fi
  echo "  downloading -> $2"; mkdir -p "$(dirname "$2")"; curl -fSL --retry 3 -o "$2" "$1"
}

if [ "$CHECK" = "--check" ]; then
  echo "URL check (no download):"
  for u in "$MANE_URL" "$DBSNP_URL" "$VEP_URL" "$SNPEFF_URL"; do echo "$u"; _head "$u"; done
  exit 0
fi

echo "[1/4] MANE Select"
_get "$MANE_URL" "$DATA/mane/MANE.GRCh38.v1.5.summary.txt.gz"

echo "[2/4] dbSNP GRCh37 (b151)"
_get "$DBSNP_URL" "$DATA/dbsnp/00-All.GRCh37.vcf.gz"

echo "[3/4] Ensembl VEP offline cache (GRCh37) + tool"
_get "$VEP_URL" "$DATA/ensembl/vep_cache/homo_sapiens_vep_113_GRCh37.tar.gz"
tar -xzf "$DATA/ensembl/vep_cache/homo_sapiens_vep_113_GRCh37.tar.gz" -C "$DATA/ensembl/vep_cache/" 2>/dev/null || true
command -v vep >/dev/null || echo "  NOTE: install Ensembl VEP (Perl) — https://www.ensembl.org/info/docs/tools/vep/script/vep_download.html"

echo "[4/4] SnpEff (LGPL) + GRCh37.75 db"
_get "$SNPEFF_URL" "$DATA/snpeff/snpEff_latest_core.zip"
(cd "$DATA/snpeff" && unzip -oq snpEff_latest_core.zip)
command -v java >/dev/null && java -jar "$DATA/snpeff/snpEff/snpEff.jar" download -v GRCh37.75 || \
  echo "  NOTE: install Java, then: java -jar $DATA/snpeff/snpEff/snpEff.jar download GRCh37.75"

echo "Building file-based caches (MANE, dbSNP MC)..."
uv run python -c "from backend.services.annotation_sources.mane_cache import build_mane_cache; \
print('MANE genes:', build_mane_cache('$DATA/mane/MANE.GRCh38.v1.5.summary.txt.gz', '.mane_cache/mane.db'))"
uv run python -c "from backend.services.annotation_sources.dbsnp_mc_cache import build_dbsnp_mc_cache; \
print('dbSNP MC rows:', build_dbsnp_mc_cache('$DATA/dbsnp/00-All.GRCh37.vcf.gz', '.dbsnp_cache/dbsnp_mc.db'))"

echo "Done. VEP + SnpEff consequence caches are built over the marker set by:"
echo "  uv run python -m backend.scripts.refresh_consequence_caches"
