#!/usr/bin/env python3
"""Quick VEP environment check."""
from pathlib import Path
import re

vep_dir = Path('/app/data_sources/ensembl/homo_sapiens/variation/vcf_vep')
cache_dir = Path('/app/data_sources/ensembl/.vep_cache')

print(f"VCF dir exists: {vep_dir.exists()}")
print(f"Cache dir exists: {cache_dir.exists()}")

if cache_dir.exists():
    for f in cache_dir.iterdir():
        print(f"  cache: {f.name} ({f.stat().st_size} bytes)")

pattern = re.compile(r'homo_sapiens_incl_consequences-chr\w+\.vcf\.gz$')
if vep_dir.exists():
    vcf_files = sorted(p for p in vep_dir.iterdir() if pattern.match(p.name))
    print(f"Chr VCF files: {len(vcf_files)}")
    
    clinical = vep_dir / 'homo_sapiens_clinically_associated.vcf.gz'
    phenotype = vep_dir / 'homo_sapiens_phenotype_associated.vcf.gz'
    print(f"clinically_associated: {clinical.exists()}")
    print(f"phenotype_associated: {phenotype.exists()}")

# Check writable
try:
    cache_dir.mkdir(parents=True, exist_ok=True)
    t = cache_dir / '.test'
    t.write_text('ok')
    t.unlink()
    print("Cache dir writable: YES")
except Exception as e:
    print(f"Cache dir writable: NO ({e})")
