"""
External API integrations for genetic variant annotation and drug response
Includes NCBI E-utilities, LitVar, SNPedia, ClinVar, and Ensembl APIs
Uses centralized endpoint configuration
"""
import aiohttp
import asyncio
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional
import re
from .api_endpoints import APIEndpoints

class GeneticAPIService:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.endpoints = APIEndpoints()
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _ensure_session(self):
        """Ensure session is initialized"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
    
    async def close(self):
        """Close the HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def _make_api_request(self, service: str, endpoint_name: str, params: Optional[Dict] = None, **url_params) -> Dict[str, Any]:
        """
        Generic method to make API requests using endpoint configurations
        """
        try:
            await self._ensure_session()
            if self.session is None:
                return {'error': 'Failed to initialize HTTP session'}
            
            endpoint = self.endpoints.get_endpoint(service, endpoint_name)
            if not endpoint:
                return {'error': f'Unknown endpoint: {service}.{endpoint_name}'}
            
            # Format URL with parameters
            url = self.endpoints.format_url(endpoint.url, **url_params) if url_params else endpoint.url
            
            # Prepare headers
            headers = endpoint.headers or {}
            
            # Create timeout object
            timeout = aiohttp.ClientTimeout(total=endpoint.timeout)
            
            async with self.session.get(url, params=params, headers=headers, timeout=timeout) as response:
                if response.status == 200:
                    if 'application/json' in response.headers.get('content-type', ''):
                        return await response.json()
                    else:
                        text_content = await response.text()
                        return {'content': text_content, 'content_type': response.headers.get('content-type')}
                else:
                    return {'error': f'{service} API failed with status {response.status}', 'status': response.status}
                    
        except Exception as e:
            return {'error': f'{service} API error: {str(e)}'}

    async def ncbi_esearch(self, database: str, term: str, retmax: int = 20) -> Dict[str, Any]:
        """
        Use NCBI E-utilities ESearch to find UIDs for a search term
        """
        params = {
            'db': database,
            'term': term,
            'retmode': 'json',
            'retmax': retmax,
            'usehistory': 'y'
        }
        
        result = await self._make_api_request('ncbi', 'esearch', params=params)
        
        if 'error' not in result:
            # Parse the response
            search_result = result.get('esearchresult', {})
            return {
                'database': database,
                'term': term,
                'count': int(search_result.get('count', 0)),
                'ids': search_result.get('idlist', []),
                'webenv': search_result.get('webenv'),
                'query_key': search_result.get('querykey')
            }
        
        return result

    async def ncbi_efetch(self, database: str, ids: List[str], rettype: str = 'xml') -> Dict[str, Any]:
        """
        Use NCBI E-utilities EFetch to retrieve full records for given UIDs
        """
        params = {
            'db': database,
            'id': ','.join(ids),
            'rettype': rettype,
            'retmode': 'xml' if rettype == 'xml' else 'text'
        }
        
        result = await self._make_api_request('ncbi', 'efetch', params=params)
        
        if 'error' not in result:
            return {
                'database': database,
                'xml_content' if rettype == 'xml' else 'content': result.get('content', '')
            }
        
        return result

    async def get_variant_info_from_clinvar(self, rsid: str) -> Dict[str, Any]:
        """
        Get variant information from ClinVar using NCBI E-utilities
        """
        try:
            # Search for the variant in ClinVar
            search_result = await self.ncbi_esearch('clinvar', rsid)
            
            if search_result.get('error'):
                return search_result
                
            if not search_result.get('ids'):
                return {'source': 'ClinVar', 'rsid': rsid, 'found': False, 'message': 'No entries found'}
            
            # Fetch detailed information
            fetch_result = await self.ncbi_efetch('clinvar', search_result['ids'][:5])  # Limit to first 5
            
            if fetch_result.get('error'):
                return fetch_result
                
            # Parse XML content (simplified parsing)
            clinvar_data = {
                'source': 'ClinVar',
                'rsid': rsid,
                'found': True,
                'entry_count': len(search_result['ids']),
                'entries': []
            }
            
            if 'xml_content' in fetch_result:
                try:
                    root = ET.fromstring(fetch_result['xml_content'])
                    for variation_set in root.findall('.//VariationArchive'):
                        entry = {
                            'accession': variation_set.get('Accession'),
                            'version': variation_set.get('Version'),
                            'variation_id': variation_set.get('VariationID'),
                            'clinical_significance': [],
                            'conditions': []
                        }
                        
                        # Extract clinical significance
                        for clin_sig in variation_set.findall('.//ClinicalSignificance'):
                            description = clin_sig.find('.//Description')
                            if description is not None:
                                entry['clinical_significance'].append(description.text)
                        
                        # Extract associated conditions
                        for trait in variation_set.findall('.//Trait'):
                            name_elem = trait.find('.//Name/ElementValue')
                            if name_elem is not None:
                                entry['conditions'].append(name_elem.text)
                        
                        clinvar_data['entries'].append(entry)
                        
                except ET.ParseError:
                    clinvar_data['parse_error'] = 'XML parsing error occurred'
            
            return clinvar_data
            
        except Exception as e:
            return {'error': f'ClinVar API error: {str(e)}'}

    async def get_litvar_publications(self, rsid: str) -> Dict[str, Any]:
        """
        Get publications related to a variant from LitVar API (with PubMed fallback)
        """
        try:
            await self._ensure_session()
            if self.session is None:
                return {'error': 'Failed to initialize HTTP session'}
                
            # Search for variant in LitVar
            params = {
                'query': rsid,
                'format': 'json'
            }
            
            result = await self._make_api_request('litvar', 'variant_search', params=params)
            
            if 'error' not in result:
                litvar_result = {
                    'source': 'LitVar',
                    'rsid': rsid,
                    'publications': [],
                    'total_publications': 0
                }
                
                if 'results' in result and result['results']:
                    for res in result['results'][:10]:  # Limit to first 10
                        pub_info = {
                            'pmid': res.get('pmid'),
                            'title': res.get('title'),
                            'authors': res.get('authors', []),
                            'journal': res.get('journal'),
                            'pub_date': res.get('pub_date'),
                            'abstract': res.get('abstract', '')[:500] + '...' if res.get('abstract') and len(res.get('abstract', '')) > 500 else res.get('abstract')
                        }
                        litvar_result['publications'].append(pub_info)
                    
                    litvar_result['total_publications'] = len(result['results'])
                
                return litvar_result
            else:
                # Fallback to PubMed search
                return await self.search_pubmed_for_variant(rsid)
                    
        except Exception:
            # LitVar API might not be available, so we'll use PubMed search as fallback
            return await self.search_pubmed_for_variant(rsid)

    async def search_pubmed_for_variant(self, rsid: str) -> Dict[str, Any]:
        """
        Search PubMed for publications mentioning a specific variant using NCBI E-utilities
        """
        try:
            # Search PubMed for the rsID
            search_term = f'"{rsid}"[All Fields] OR "{rsid}"[Title/Abstract]'
            search_result = await self.ncbi_esearch('pubmed', search_term, retmax=10)
            
            if search_result.get('error'):
                return search_result
                
            if not search_result.get('ids'):
                return {
                    'source': 'PubMed',
                    'rsid': rsid,
                    'publications': [],
                    'total_publications': 0,
                    'message': 'No publications found'
                }
            
            # Fetch publication details
            fetch_result = await self.ncbi_efetch('pubmed', search_result['ids'], rettype='xml')
            
            pubmed_result = {
                'source': 'PubMed',
                'rsid': rsid,
                'publications': [],
                'total_publications': search_result.get('count', 0)
            }
            
            if 'xml_content' in fetch_result:
                try:
                    root = ET.fromstring(fetch_result['xml_content'])
                    for article in root.findall('.//PubmedArticle'):
                        pub_info = {
                            'pmid': '',
                            'title': '',
                            'authors': [],
                            'journal': '',
                            'pub_date': '',
                            'abstract': ''
                        }
                        
                        # Extract PMID
                        pmid_elem = article.find('.//PMID')
                        if pmid_elem is not None:
                            pub_info['pmid'] = pmid_elem.text
                        
                        # Extract title
                        title_elem = article.find('.//ArticleTitle')
                        if title_elem is not None:
                            pub_info['title'] = title_elem.text or ''
                        
                        # Extract authors
                        for author in article.findall('.//Author'):
                            last_name = author.find('.//LastName')
                            first_name = author.find('.//ForeName')
                            if last_name is not None and last_name.text:
                                author_name = last_name.text
                                if first_name is not None and first_name.text:
                                    author_name += f", {first_name.text}"
                                pub_info['authors'].append(author_name)
                        
                        # Extract journal
                        journal_elem = article.find('.//Journal/Title')
                        if journal_elem is not None:
                            pub_info['journal'] = journal_elem.text
                        
                        # Extract publication date
                        pub_date_elem = article.find('.//PubDate/Year')
                        if pub_date_elem is not None:
                            pub_info['pub_date'] = pub_date_elem.text
                        
                        # Extract abstract
                        abstract_elem = article.find('.//Abstract/AbstractText')
                        if abstract_elem is not None:
                            abstract_text = abstract_elem.text or ''
                            pub_info['abstract'] = abstract_text[:500] + '...' if len(abstract_text) > 500 else abstract_text
                        
                        pubmed_result['publications'].append(pub_info)
                        
                except ET.ParseError:
                    pubmed_result['parse_error'] = 'XML parsing error occurred'
            
            return pubmed_result
            
        except Exception as e:
            return {'error': f'PubMed search error: {str(e)}'}

    async def get_snpedia_info(self, rsid: str) -> Dict[str, Any]:
        """
        Get variant information from SNPedia using MediaWiki API
        """
        try:
            await self._ensure_session()
            if self.session is None:
                return {'error': 'Failed to initialize HTTP session'}
                
            # Query SNPedia MediaWiki API
            params = {
                'action': 'query',
                'format': 'json',
                'titles': rsid,
                'prop': 'extracts|pageprops',
                'exintro': True,
                'explaintext': True,
                'exsectionformat': 'plain'
            }
            
            result = await self._make_api_request('snpedia', 'query', params=params)
            
            if 'error' not in result:
                snpedia_result = {
                    'source': 'SNPedia',
                    'rsid': rsid,
                    'found': False
                }
                
                pages = result.get('query', {}).get('pages', {})
                for page_id, page_data in pages.items():
                    if page_id != '-1':  # Page exists
                        snpedia_result['found'] = True
                        snpedia_result['title'] = page_data.get('title')
                        extract = page_data.get('extract', '')
                        snpedia_result['extract'] = extract[:500] + '...' if extract and len(extract) > 500 else extract
                        
                        # Try to extract structured data from page properties
                        pageprops = page_data.get('pageprops', {})
                        snpedia_result['properties'] = pageprops
                        
                        # Parse common SNPedia template data from extract
                        if extract:
                            # Look for magnitude
                            magnitude_match = re.search(r'magnitude[:\s]*(\d+)', extract, re.IGNORECASE)
                            if magnitude_match:
                                snpedia_result['magnitude'] = int(magnitude_match.group(1))
                            
                            # Look for frequency
                            freq_match = re.search(r'frequency[:\s]*([0-9.]+)', extract, re.IGNORECASE)
                            if freq_match:
                                snpedia_result['frequency'] = float(freq_match.group(1))
                        
                        break
                
                if not snpedia_result['found']:
                    snpedia_result['message'] = 'No SNPedia page found for this variant'
                
                return snpedia_result
            else:
                return result  # Return the error from _make_api_request
                    
        except Exception as e:
            return {'error': f'SNPedia API error: {str(e)}'}

    async def get_variant_info_from_ensembl(self, rsid: str) -> Dict[str, Any]:
        """
        Get variant information from Ensembl REST API with enhanced data extraction
        """
        result = await self._make_api_request('ensembl', 'variation', rsid=rsid)
        
        if 'error' not in result:
            ensembl_result = {
                'source': 'Ensembl',
                'rsid': rsid,
                'name': result.get('name'),
                'most_severe_consequence': result.get('most_severe_consequence'),
                'minor_allele': result.get('minor_allele'),
                'minor_allele_freq': result.get('minor_allele_freq'),
                'clinical_significance': result.get('clinical_significance', []),
                'synonyms': result.get('synonyms', []),
                'populations': {},
                'consequences': []
            }
            
            # Extract population frequencies
            populations = result.get('populations', [])
            for pop in populations:
                pop_name = pop.get('population')
                if pop_name:
                    ensembl_result['populations'][pop_name] = {
                        'frequency': pop.get('frequency'),
                        'allele': pop.get('allele'),
                        'allele_count': pop.get('allele_count'),
                        'total_count': pop.get('total_count')
                    }
            
            # Extract consequence predictions
            mappings = result.get('mappings', [])
            for mapping in mappings[:5]:  # Limit to first 5
                if 'consequence_type' in mapping:
                    ensembl_result['consequences'].append({
                        'gene': mapping.get('gene_name'),
                        'consequence': mapping.get('consequence_type'),
                        'impact': mapping.get('impact'),
                        'biotype': mapping.get('biotype')
                    })
            
            return ensembl_result
        else:
            # Check if it's a 404 error (variant not found)
            if 'status' in result and result['status'] == 404:
                return {
                    'source': 'Ensembl',
                    'rsid': rsid,
                    'found': False,
                    'message': 'Variant not found in Ensembl'
                }
            else:
                return result  # Return the error from _make_api_request

    async def get_pharmgkb_drug_info(self, gene: str) -> Dict[str, Any]:
        """
        Get pharmacogenomic information from PharmGKB API
        """
        try:
            await self._ensure_session()
            if self.session is None:
                return {'error': 'Failed to initialize HTTP session'}
                
            # PharmGKB API base URL
            pharmgkb_base_url = "https://api.pharmgkb.org"
            
            # Search for gene information
            gene_url = f"{pharmgkb_base_url}/v1/gene/{gene.upper()}"
            
            async with self.session.get(gene_url) as response:
                if response.status == 200:
                    gene_data = await response.json()
                    
                    pharmgkb_result = {
                        'source': 'PharmGKB',
                        'gene': gene,
                        'found': True,
                        'gene_id': gene_data.get('id'),
                        'name': gene_data.get('name'),
                        'symbol': gene_data.get('symbol'),
                        'drugs': [],
                        'drug_count': 0,
                        'clinical_annotations': [],
                        'function': gene_data.get('function', ''),
                        'clinical_significance': 'Unknown'
                    }
                    
                    # Get drug associations for this gene
                    drugs_url = f"{pharmgkb_base_url}/v1/gene/{gene.upper()}/drugs"
                    try:
                        async with self.session.get(drugs_url) as drug_response:
                            if drug_response.status == 200:
                                drug_data = await drug_response.json()
                                if 'data' in drug_data:
                                    pharmgkb_result['drugs'] = [
                                        {
                                            'name': drug.get('name'),
                                            'id': drug.get('id'),
                                            'type': drug.get('type')
                                        }
                                        for drug in drug_data['data'][:10]  # Limit to first 10
                                    ]
                                    pharmgkb_result['drug_count'] = len(drug_data['data'])
                    except Exception:
                        # Continue if drug lookup fails
                        pass
                    
                    # Get clinical annotations for this gene
                    annotations_url = f"{pharmgkb_base_url}/v1/gene/{gene.upper()}/clinicalAnnotations"
                    try:
                        async with self.session.get(annotations_url) as ann_response:
                            if ann_response.status == 200:
                                ann_data = await ann_response.json()
                                if 'data' in ann_data:
                                    pharmgkb_result['clinical_annotations'] = [
                                        {
                                            'id': ann.get('id'),
                                            'text': ann.get('summaryMarkdown', ann.get('textMarkdown', ''))[:200] + '...' if ann.get('summaryMarkdown') or ann.get('textMarkdown') else '',
                                            'level': ann.get('level'),
                                            'type': ann.get('type'),
                                            'drugs': [drug.get('name') for drug in ann.get('relatedChemicals', [])]
                                        }
                                        for ann in ann_data['data'][:5]  # Limit to first 5
                                    ]
                                    
                                    # Determine clinical significance based on annotations
                                    if pharmgkb_result['clinical_annotations']:
                                        levels = [ann.get('level') for ann in pharmgkb_result['clinical_annotations'] if ann.get('level')]
                                        if any(level in ['1A', '1B', '2A'] for level in levels):
                                            pharmgkb_result['clinical_significance'] = 'High'
                                        elif any(level in ['2B', '3'] for level in levels):
                                            pharmgkb_result['clinical_significance'] = 'Moderate'
                                        else:
                                            pharmgkb_result['clinical_significance'] = 'Limited'
                    except Exception:
                        # Continue if annotations lookup fails
                        pass
                    
                    return pharmgkb_result
                    
                elif response.status == 404:
                    return {
                        'source': 'PharmGKB',
                        'gene': gene,
                        'found': False,
                        'message': f'Gene {gene} not found in PharmGKB'
                    }
                else:
                    return {'error': f'PharmGKB API failed with status {response.status}'}
                    
        except Exception as e:
            return {'error': f'PharmGKB API error: {str(e)}'}

    async def get_pharmgkb_variant_info(self, rsid: str) -> Dict[str, Any]:
        """
        Get variant-specific information from PharmGKB API
        """
        try:
            await self._ensure_session()
            if self.session is None:
                return {'error': 'Failed to initialize HTTP session'}
                
            pharmgkb_base_url = "https://api.pharmgkb.org"
            
            # Search for variant by rsID
            variant_url = f"{pharmgkb_base_url}/v1/variant/{rsid}"
            
            async with self.session.get(variant_url) as response:
                if response.status == 200:
                    variant_data = await response.json()
                    
                    pharmgkb_result = {
                        'source': 'PharmGKB',
                        'rsid': rsid,
                        'found': True,
                        'variant_id': variant_data.get('id'),
                        'name': variant_data.get('name'),
                        'gene': variant_data.get('gene', {}).get('symbol') if variant_data.get('gene') else None,
                        'chromosome': variant_data.get('chromosome'),
                        'position': variant_data.get('position'),
                        'clinical_annotations': [],
                        'drug_labels': [],
                        'clinical_significance': 'Unknown'
                    }
                    
                    # Get clinical annotations for this variant
                    annotations_url = f"{pharmgkb_base_url}/v1/variant/{rsid}/clinicalAnnotations"
                    try:
                        async with self.session.get(annotations_url) as ann_response:
                            if ann_response.status == 200:
                                ann_data = await ann_response.json()
                                if 'data' in ann_data:
                                    pharmgkb_result['clinical_annotations'] = [
                                        {
                                            'id': ann.get('id'),
                                            'text': ann.get('summaryMarkdown', ann.get('textMarkdown', ''))[:200] + '...' if ann.get('summaryMarkdown') or ann.get('textMarkdown') else '',
                                            'level': ann.get('level'),
                                            'drugs': [drug.get('name') for drug in ann.get('relatedChemicals', [])]
                                        }
                                        for ann in ann_data['data'][:5]
                                    ]
                    except Exception:
                        pass
                    
                    # Get drug labels for this variant
                    labels_url = f"{pharmgkb_base_url}/v1/variant/{rsid}/drugLabels"
                    try:
                        async with self.session.get(labels_url) as label_response:
                            if label_response.status == 200:
                                label_data = await label_response.json()
                                if 'data' in label_data:
                                    pharmgkb_result['drug_labels'] = [
                                        {
                                            'id': label.get('id'),
                                            'name': label.get('name'),
                                            'source': label.get('source'),
                                            'text_markdown': label.get('textMarkdown', '')[:200] + '...' if label.get('textMarkdown') else ''
                                        }
                                        for label in label_data['data'][:5]
                                    ]
                    except Exception:
                        pass
                    
                    # Determine clinical significance
                    if pharmgkb_result['clinical_annotations'] or pharmgkb_result['drug_labels']:
                        if pharmgkb_result['clinical_annotations']:
                            levels = [ann.get('level') for ann in pharmgkb_result['clinical_annotations'] if ann.get('level')]
                            if any(level in ['1A', '1B', '2A'] for level in levels):
                                pharmgkb_result['clinical_significance'] = 'High'
                            elif any(level in ['2B', '3'] for level in levels):
                                pharmgkb_result['clinical_significance'] = 'Moderate'
                            else:
                                pharmgkb_result['clinical_significance'] = 'Limited'
                        else:
                            pharmgkb_result['clinical_significance'] = 'Moderate'
                    
                    return pharmgkb_result
                    
                elif response.status == 404:
                    return {
                        'source': 'PharmGKB',
                        'rsid': rsid,
                        'found': False,
                        'message': f'Variant {rsid} not found in PharmGKB'
                    }
                else:
                    return {'error': f'PharmGKB variant API failed with status {response.status}'}
                    
        except Exception as e:
            return {'error': f'PharmGKB variant API error: {str(e)}'}

    async def search_pharmgkb_drugs(self, query: str) -> Dict[str, Any]:
        """
        Search for drugs in PharmGKB
        """
        try:
            await self._ensure_session()
            if self.session is None:
                return {'error': 'Failed to initialize HTTP session'}
                
            pharmgkb_base_url = "https://api.pharmgkb.org"
            
            # Search drugs
            search_url = f"{pharmgkb_base_url}/v1/drug/search"
            params = {'q': query, 'limit': 10}
            
            async with self.session.get(search_url, params=params) as response:
                if response.status == 200:
                    search_data = await response.json()
                    
                    return {
                        'source': 'PharmGKB',
                        'query': query,
                        'found': len(search_data.get('data', [])) > 0,
                        'drugs': [
                            {
                                'id': drug.get('id'),
                                'name': drug.get('name'),
                                'type': drug.get('type'),
                                'trade_names': drug.get('tradeNames', [])
                            }
                            for drug in search_data.get('data', [])
                        ]
                    }
                else:
                    return {'error': f'PharmGKB drug search failed with status {response.status}'}
                    
        except Exception as e:
            return {'error': f'PharmGKB drug search error: {str(e)}'}

    async def get_pharmgkb_guidelines(self, gene: Optional[str] = None, drug: Optional[str] = None) -> Dict[str, Any]:
        """
        Get clinical guidelines from PharmGKB
        """
        try:
            await self._ensure_session()
            if self.session is None:
                return {'error': 'Failed to initialize HTTP session'}
                
            pharmgkb_base_url = "https://api.pharmgkb.org"
            
            # Get guidelines
            guidelines_url = f"{pharmgkb_base_url}/v1/guideline"
            params = {}
            if gene:
                params['gene'] = gene.upper()
            if drug:
                params['drug'] = drug
            
            async with self.session.get(guidelines_url, params=params) as response:
                if response.status == 200:
                    guidelines_data = await response.json()
                    
                    return {
                        'source': 'PharmGKB',
                        'gene': gene,
                        'drug': drug,
                        'guidelines': [
                            {
                                'id': guideline.get('id'),
                                'name': guideline.get('name'),
                                'source': guideline.get('source'),
                                'text': guideline.get('summaryMarkdown', '')[:300] + '...' if guideline.get('summaryMarkdown') else '',
                                'drugs': [drug.get('name') for drug in guideline.get('relatedChemicals', [])],
                                'genes': [gene.get('symbol') for gene in guideline.get('relatedGenes', [])]
                            }
                            for guideline in guidelines_data.get('data', [])[:5]
                        ]
                    }
                else:
                    return {'error': f'PharmGKB guidelines API failed with status {response.status}'}
                    
        except Exception as e:
            return {'error': f'PharmGKB guidelines API error: {str(e)}'}
    
    async def annotate_variant(self, rsid: str, gene: Optional[str] = None) -> Dict[str, Any]:
        """
        Comprehensive variant annotation using multiple sources including real PharmGKB API
        """
        results = {
            'rsid': rsid,
            'gene': gene,
            'annotations': {}
        }
        
        # Gather data from multiple sources concurrently
        tasks = [
            self.get_variant_info_from_ensembl(rsid),
            self.get_variant_info_from_clinvar(rsid),
            self.get_snpedia_info(rsid),
            self.get_litvar_publications(rsid),
            self.get_pharmgkb_variant_info(rsid)
        ]
        
        if gene:
            tasks.append(self.get_pharmgkb_drug_info(gene))
        
        try:
            annotations = await asyncio.gather(*tasks, return_exceptions=True)
            
            results['annotations']['ensembl'] = annotations[0] if len(annotations) > 0 else {}
            results['annotations']['clinvar'] = annotations[1] if len(annotations) > 1 else {}
            results['annotations']['snpedia'] = annotations[2] if len(annotations) > 2 else {}
            results['annotations']['literature'] = annotations[3] if len(annotations) > 3 else {}
            results['annotations']['pharmgkb_variant'] = annotations[4] if len(annotations) > 4 else {}
            
            if gene and len(annotations) > 5:
                results['annotations']['pharmgkb_gene'] = annotations[5]
                
        except Exception as e:
            results['error'] = f'Annotation error: {str(e)}'
        
        return results
    
    async def batch_annotate_variants(self, variants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Annotate multiple variants in batch with improved rate limiting
        """
        annotated_variants = []
        
        # Limit batch size to avoid overwhelming APIs
        batch_size = 5  # Reduced for better API compliance
        for i in range(0, len(variants), batch_size):
            batch = variants[i:i + batch_size]
            
            tasks = []
            for variant in batch:
                rsid = variant.get('rsid') or variant.get('id')
                gene = variant.get('gene')
                if rsid:
                    tasks.append(self.annotate_variant(rsid, gene if gene else None))
            
            if tasks:
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                annotated_variants.extend(batch_results)
            
            # Enhanced rate limiting - pause between batches
            await asyncio.sleep(1.0)  # Increased delay for API compliance
        
        return annotated_variants

    async def get_variant_clinical_summary(self, rsid: str, gene: Optional[str] = None) -> Dict[str, Any]:
        """
        Get a comprehensive clinical summary combining all data sources
        """
        annotation_result = await self.annotate_variant(rsid, gene)
        
        summary = {
            'rsid': rsid,
            'gene': gene,
            'clinical_significance': 'Unknown',
            'drug_responses': [],
            'population_frequency': None,
            'literature_count': 0,
            'evidence_level': 'Limited',
            'recommendations': []
        }
        
        if 'annotations' in annotation_result:
            annotations = annotation_result['annotations']
            
            # Extract clinical significance from ClinVar
            if 'clinvar' in annotations and annotations['clinvar'].get('found'):
                entries = annotations['clinvar'].get('entries', [])
                if entries:
                    clinical_sigs = []
                    for entry in entries:
                        clinical_sigs.extend(entry.get('clinical_significance', []))
                    if clinical_sigs:
                        summary['clinical_significance'] = ', '.join(set(clinical_sigs))
            
            # Extract population frequency from Ensembl
            if 'ensembl' in annotations:
                freq = annotations['ensembl'].get('minor_allele_freq')
                if freq:
                    summary['population_frequency'] = freq
            
            # Extract literature count
            if 'literature' in annotations:
                summary['literature_count'] = annotations['literature'].get('total_publications', 0)
            
            # Extract drug response information
            if 'pharmgkb' in annotations and 'drugs' in annotations['pharmgkb']:
                summary['drug_responses'] = annotations['pharmgkb']['drugs']
                summary['evidence_level'] = annotations['pharmgkb'].get('clinical_significance', 'Limited')
            
            # Generate recommendations
            if summary['clinical_significance'] != 'Unknown':
                summary['recommendations'].append('Consult healthcare provider for clinical interpretation')
            if summary['drug_responses']:
                summary['recommendations'].append('Consider pharmacogenomic testing for personalized dosing')
            if summary['literature_count'] > 5:
                summary['recommendations'].append('Well-studied variant with substantial literature')
        
        return summary