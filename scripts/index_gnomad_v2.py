#!/usr/bin/env python3
"""Index gnomAD v2 VCF files (create .tbi tabix indexes)."""
import asyncio
import sys
sys.path.insert(0, "/app")

from backend.services.gnomad_v2_local import get_gnomad_v2_service

async def main():
    svc = get_gnomad_v2_service()
    await svc.ensure_loaded()
    print(f"Files: {svc.file_count}, Indexed: {svc.indexed_count}", flush=True)
    result = await svc.index_all_files()
    print(f"Result: {result}", flush=True)

asyncio.run(main())
