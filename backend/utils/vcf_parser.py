"""
VCF file parser for genetic variant data
"""
import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

RSID_PATTERN = re.compile(r'^rs\d+$')
VALID_CHROMOSOMES = frozenset(
    [str(i) for i in range(1, 23)] + ['X', 'Y', 'MT']
)
MIN_POSITION = 1
MAX_POSITION = 300_000_000  # longest human chromosome is ~249M bp
VALID_BASES = frozenset('ATGCN')


class VCFParser:
    def __init__(self):
        self.header_lines = []
        self.sample_names = []
        self._skipped_count = 0
    
    async def parse_vcf_content(self, content: bytes) -> List[Dict[str, Any]]:
        """Parse genetic data file content (VCF or CSV) and return variants"""
        variants = []
        
        try:
            # Decode content
            content_text = content.decode('utf-8')
            lines = content_text.strip().split('\n')
            
            # Better format detection - look for actual VCF structure
            has_vcf_header = False
            has_tab_separated = False
            
            for line in lines[:20]:  # Check first 20 lines
                if line.startswith('#CHROM\tPOS\tID\tREF\tALT'):
                    has_vcf_header = True
                    break
                elif not line.startswith('#') and '\t' in line and len(line.split('\t')) >= 8:
                    has_tab_separated = True
                    break
            
            # Check if it looks like a CSV with comma separation
            has_csv_structure = False
            for line in lines:
                if not line.startswith('#') and ',' in line:
                    has_csv_structure = True
                    break
            
            # Decide format based on structure
            if has_vcf_header or (has_tab_separated and not has_csv_structure):
                variants = await self._parse_vcf_format(content_text)
            else:
                # Assume CSV format
                variants = await self._parse_csv_format(content_text)
                
        except Exception as e:
            print(f"Error parsing genetic data: {e}")
            # Return mock data for demo
            variants = self._generate_mock_variants()
        
        return variants

    async def _parse_vcf_format(self, vcf_text: str) -> List[Dict[str, Any]]:
        """Parse VCF format specifically"""
        variants = []
        lines = vcf_text.strip().split('\n')
        
        # Parse header
        data_lines = []
        for line in lines:
            if line.startswith('##'):
                self.header_lines.append(line)
            elif line.startswith('#CHROM'):
                # Column headers
                columns = line.strip().split('\t')
                self.sample_names = columns[9:] if len(columns) > 9 else []
            else:
                # Data lines
                data_lines.append(line)
        
        # Parse variants
        for line_num, line in enumerate(data_lines):
            if line.strip():
                variant = self._parse_variant_line(line, line_num)
                if variant is not None:
                    variants.append(variant)
        
        if self._skipped_count > 0:
            logger.info(f"Skipped {self._skipped_count} variants that failed validation")

        return variants

    async def _parse_csv_format(self, csv_text: str) -> List[Dict[str, Any]]:
        """Parse CSV format (23andMe, AncestryDNA, etc.)"""
        import csv
        import io
        
        variants = []
        lines = csv_text.strip().split('\n')
        
        # Skip comment lines and find header
        data_lines = []
        header_line = None
        last_comment = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith('#'):
                last_comment = line
                continue
            if header_line is None:
                header_line = line
            else:
                data_lines.append(line)
        
        if not header_line or not data_lines:
            print("No valid CSV data found")
            return []
        
        # Detect delimiter: tab-separated (23andMe, AncestryDNA .txt) vs comma-separated
        delimiter = ','
        if '\t' in header_line and ',' not in header_line:
            delimiter = '\t'
            # Check if last comment line is a column header (e.g. "# rsid	chromosome	position	genotype")
            if last_comment:
                comment_text = last_comment.lstrip('#').strip()
                if '\t' in comment_text:
                    known_headers = {'rsid', 'chromosome', 'position', 'genotype', 'snp', 'chr', 'pos', 'allele1', 'allele2'}
                    comment_cols = [c.strip().lower() for c in comment_text.split('\t')]
                    if any(col in known_headers for col in comment_cols):
                        # Use comment line as header, move first data line back to data
                        data_lines.insert(0, header_line)
                        header_line = comment_text
        
        # Parse data with detected delimiter
        csv_reader = csv.DictReader(io.StringIO('\n'.join([header_line] + data_lines)), delimiter=delimiter)
        
        for row_num, row in enumerate(csv_reader):
            try:
                variant = self._parse_csv_row(row, row_num)
                if variant:
                    variants.append(variant)
            except Exception as e:
                print(f"Error parsing CSV row {row_num}: {e}")
                continue
        
        if self._skipped_count > 0:
            logger.info(f"Skipped {self._skipped_count} variants that failed validation")

        logger.info(f"Parsed {len(variants)} variants from CSV")
        return variants

    def _parse_csv_row(self, row: Dict[str, str], row_num: int) -> Optional[Dict[str, Any]]:
        """Parse a single CSV row into variant format - supports multiple provider formats"""
        try:
            # Handle different CSV column name variations from various providers
            # RSID/SNP identifiers
            rsid = (row.get('rsid') or row.get('RSID') or row.get('rs') or 
                   row.get('SNP') or row.get('snp') or row.get('name') or 
                   row.get('Name') or row.get('ID'))
            
            # Chromosome variations
            chromosome = (row.get('chromosome') or row.get('CHROMOSOME') or 
                         row.get('chr') or row.get('Chr') or row.get('CHR') or
                         row.get('chrom') or row.get('Chrom') or row.get('CHROM'))
            
            # Position variations  
            position = (row.get('position') or row.get('POSITION') or 
                       row.get('pos') or row.get('Pos') or row.get('POS') or
                       row.get('bp') or row.get('BP') or row.get('coordinate'))
            
            # Genotype/Allele variations
            genotype = (row.get('genotype') or row.get('GENOTYPE') or 
                       row.get('Genotype') or row.get('GT') or row.get('gt') or
                       row.get('result') or row.get('RESULT') or row.get('Result') or
                       row.get('alleles') or row.get('ALLELES') or row.get('call'))
            
            # Some providers have separate allele columns
            if not genotype:
                allele1 = (row.get('allele1') or row.get('ALLELE1') or 
                          row.get('A1') or row.get('a1'))
                allele2 = (row.get('allele2') or row.get('ALLELE2') or 
                          row.get('A2') or row.get('a2'))
                if allele1 and allele2:
                    genotype = allele1 + allele2
            
            # Clean and normalize genotype
            ref_allele = None
            alt_allele = None
            
            if genotype:
                # Remove quotes and whitespace
                genotype = genotype.strip('"').strip()
                
                if genotype and genotype not in ['--', 'NN', '00', './.', '.|.']:
                    # Handle different genotype formats
                    if '/' in genotype:
                        alleles = genotype.split('/')
                    elif '|' in genotype:
                        alleles = genotype.split('|')
                    elif '\t' in genotype:
                        alleles = genotype.split('\t')
                    elif ' ' in genotype:
                        alleles = genotype.split(' ')
                    elif len(genotype) == 2:
                        alleles = [genotype[0], genotype[1]]
                    elif len(genotype) == 1:
                        alleles = [genotype, genotype]  # Homozygous
                    else:
                        # For longer strings, try to extract valid nucleotides
                        valid_bases = set('ATGC')
                        extracted = [c for c in genotype if c in valid_bases]
                        if len(extracted) >= 2:
                            alleles = extracted[:2]
                        elif len(extracted) == 1:
                            alleles = [extracted[0], extracted[0]]
                        else:
                            alleles = ['N', 'N']
                    
                    # Clean alleles
                    if len(alleles) >= 2:
                        alleles = [a.strip().upper() for a in alleles if a.strip()]
                        if alleles and all(a in 'ATGCN-' for a in alleles):
                            ref_allele = alleles[0] if alleles[0] != '-' else 'N'
                            alt_allele = alleles[1] if alleles[1] != '-' else alleles[0]
            
            # Skip if essential data is missing
            if not chromosome or not position:
                return None
                
            # Normalize and validate chromosome
            chromosome = self._normalize_chromosome(chromosome)
            if chromosome is None:
                self._skipped_count += 1
                return None
            
            # Convert position to integer
            try:
                position = str(position).strip('"').strip()
                position = int(float(position))  # Handle scientific notation
            except (ValueError, TypeError):
                return None
            
            # Clean RSID
            if rsid:
                rsid = str(rsid).strip('"').strip()
                if not rsid.startswith('rs') and rsid.isdigit():
                    rsid = f"rs{rsid}"
                # Drop rsid if it doesn't match expected pattern
                if not RSID_PATTERN.match(rsid):
                    rsid = None
            
            variant = {
                "line_number": row_num + 1,
                "chromosome": chromosome,
                "position": position,
                "id": rsid or f"variant_{row_num}",
                "rsid": rsid,  # Add rsid field for database compatibility
                "genotype": genotype,  # Store genotype at top level for analysis_variants
                "ref_allele": ref_allele or "N",
                "alt_allele": alt_allele or "N", 
                "quality": None,
                "filter": "PASS",
                "info": {"source": "csv_upload", "original_genotype": genotype}
            }

            if not self._validate_variant(variant):
                return None

            return variant
            
        except Exception as e:
            print(f"Error parsing CSV row {row_num}: {e}")
            return None
    
    @staticmethod
    def _normalize_chromosome(chrom: str) -> Optional[str]:
        """Normalize chromosome value to standard form (1-22, X, Y, MT). Returns None if invalid."""
        chrom = str(chrom).strip().strip('"')
        if chrom.lower().startswith('chr'):
            chrom = chrom[3:]
        chrom = chrom.upper()
        if chrom in ('23', 'XX', 'X_CHROMOSOME'):
            chrom = 'X'
        elif chrom in ('24', 'XY', 'Y_CHROMOSOME'):
            chrom = 'Y'
        elif chrom in ('25', 'MT', 'M', 'MITOCHONDRIAL'):
            chrom = 'MT'
        return chrom if chrom in VALID_CHROMOSOMES else None

    def _validate_variant(self, variant: Dict[str, Any]) -> bool:
        """Validate that a parsed variant has well-formed fields."""
        # Validate chromosome
        chrom = variant.get('chromosome')
        if chrom not in VALID_CHROMOSOMES:
            self._skipped_count += 1
            return False

        # Validate position
        pos = variant.get('position')
        if not isinstance(pos, int) or pos < MIN_POSITION or pos > MAX_POSITION:
            self._skipped_count += 1
            return False

        # Validate rsid if present (must match rs\d+ or be a generated placeholder)
        rsid = variant.get('rsid') or variant.get('id', '')
        if rsid and not rsid.startswith('variant_') and not RSID_PATTERN.match(rsid):
            # Drop the invalid rsid so it won't pollute the marker catalog
            variant['rsid'] = None
            variant['id'] = f"variant_{variant.get('line_number', 0)}"

        # Validate alleles contain only valid bases
        for key in ('ref_allele', 'alt_allele'):
            allele = str(variant.get(key, 'N')).upper()
            if not allele or not all(c in VALID_BASES or c in ('-', '.', '*') for c in allele):
                variant[key] = 'N'

        return True

    def _parse_variant_line(self, line: str, line_num: int) -> Optional[Dict[str, Any]]:
        """Parse a single variant line from VCF"""
        try:
            fields = line.strip().split('\t')
            
            if len(fields) < 8:
                return None

            # Normalize chromosome
            chrom = self._normalize_chromosome(fields[0])
            if chrom is None:
                self._skipped_count += 1
                return None

            # Parse position safely
            try:
                position = int(fields[1])
            except (ValueError, TypeError):
                self._skipped_count += 1
                return None

            # Determine rsid
            raw_id = fields[2]
            rsid = raw_id if raw_id != '.' and RSID_PATTERN.match(raw_id) else None

            variant = {
                "line_number": line_num + 1,
                "chromosome": chrom,
                "position": position,
                "id": rsid or f"variant_{line_num}",
                "rsid": rsid,
                "ref_allele": fields[3],
                "alt_allele": fields[4],
                "quality": fields[5] if fields[5] != '.' else None,
                "filter": fields[6],
                "info": self._parse_info_field(fields[7])
            }
            
            # Add genotype information if available
            if len(fields) > 9 and self.sample_names:
                format_fields = fields[8].split(':') if len(fields) > 8 else []
                for i, sample in enumerate(self.sample_names):
                    if i + 9 < len(fields):
                        sample_data = fields[i + 9].split(':')
                        variant[f"sample_{sample}"] = dict(zip(format_fields, sample_data))

            if not self._validate_variant(variant):
                return None

            return variant
            
        except Exception as e:
            print(f"Error parsing variant line {line_num}: {e}")
            return None
    
    def _parse_info_field(self, info_str: str) -> Dict[str, Any]:
        """Parse the INFO field from VCF"""
        info_dict = {}
        
        if info_str == '.':
            return info_dict
        
        for item in info_str.split(';'):
            if '=' in item:
                key, value = item.split('=', 1)
                # Try to convert to appropriate type
                if value.isdigit():
                    info_dict[key] = int(value)
                elif value.replace('.', '').isdigit():
                    info_dict[key] = float(value)
                else:
                    info_dict[key] = value
            else:
                # Flag field
                info_dict[item] = True
        
        return info_dict
    
    def _generate_mock_variants(self) -> List[Dict[str, Any]]:
        """Generate mock variants for demonstration"""
        import random
        
        mock_variants = []
        chromosomes = [str(i) for i in range(1, 23)] + ['X', 'Y']
        
        for i in range(50):
            variant = {
                "line_number": i + 1,
                "chromosome": random.choice(chromosomes),
                "position": random.randint(10000, 250000000),
                "id": f"rs{random.randint(1000000, 99999999)}",
                "ref_allele": random.choice(['A', 'T', 'G', 'C']),
                "alt_allele": random.choice(['A', 'T', 'G', 'C']),
                "quality": round(random.uniform(20, 999), 2),
                "filter": random.choice(['PASS', 'LowQual', '.']),
                "info": {
                    "AF": round(random.uniform(0.001, 0.5), 4),
                    "AC": random.randint(1, 10),
                    "AN": random.randint(10, 1000)
                }
            }
            mock_variants.append(variant)
        
        return mock_variants
    
    async def get_variant_statistics(self, variants: List[Dict]) -> Dict[str, Any]:
        """Get statistics about parsed variants"""
        if not variants:
            return {}
        
        stats = {
            "total_variants": len(variants),
            "chromosomes": {},
            "variant_types": {},
            "quality_stats": {}
        }
        
        # Chromosome distribution
        for variant in variants:
            chrom = variant["chromosome"]
            stats["chromosomes"][chrom] = stats["chromosomes"].get(chrom, 0) + 1
        
        # Variant types (based on ref/alt length)
        for variant in variants:
            ref_len = len(variant["ref_allele"])
            alt_len = len(variant["alt_allele"])
            
            if ref_len == alt_len == 1:
                variant_type = "SNV"
            elif ref_len > alt_len:
                variant_type = "Deletion"
            elif ref_len < alt_len:
                variant_type = "Insertion"
            else:
                variant_type = "Complex"
            
            stats["variant_types"][variant_type] = stats["variant_types"].get(variant_type, 0) + 1
        
        # Quality statistics
        qualities = [v["quality"] for v in variants if v["quality"] is not None]
        if qualities:
            stats["quality_stats"] = {
                "mean": round(sum(qualities) / len(qualities), 2),
                "min": min(qualities),
                "max": max(qualities)
            }
        
        return stats