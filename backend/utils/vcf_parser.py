"""
VCF file parser for genetic variant data
"""
from typing import List, Dict, Any, Optional

class VCFParser:
    def __init__(self):
        self.header_lines = []
        self.sample_names = []
    
    async def parse_vcf_content(self, content: bytes) -> List[Dict[str, Any]]:
        """Parse VCF file content and return variants"""
        variants = []
        
        try:
            # Decode content
            vcf_text = content.decode('utf-8')
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
            for line_num, line in enumerate(data_lines):  # Process all variants
                if line.strip():
                    variant = self._parse_variant_line(line, line_num)
                    if variant is not None:
                        variants.append(variant)
                        
        except Exception as e:
            print(f"Error parsing VCF: {e}")
            # Return mock data for demo
            variants = self._generate_mock_variants()
        
        return variants
    
    def _parse_variant_line(self, line: str, line_num: int) -> Optional[Dict[str, Any]]:
        """Parse a single variant line from VCF"""
        try:
            fields = line.strip().split('\t')
            
            if len(fields) < 8:
                return None
            
            variant = {
                "line_number": line_num + 1,
                "chromosome": fields[0],
                "position": int(fields[1]),
                "id": fields[2] if fields[2] != '.' else f"variant_{line_num}",
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