"""
Optimized genetic API service with connection pooling, rate limiting, and batch processing.
"""
import asyncio
import aiohttp
import logging
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from asyncio import Semaphore

from ..core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class APIEndpoint:
    """Configuration for an API endpoint."""
    url: str
    headers: Optional[Dict[str, str]] = None
    timeout: float = 30.0
    rate_limit: float = 1.0  # requests per second
    max_retries: int = 3


@dataclass
class APIResponse:
    """Standardized API response."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    status_code: Optional[int] = None
    response_time: float = 0.0


class RateLimiter:
    """Rate limiter for API requests."""
    
    def __init__(self, rate: float):
        self.rate = rate  # requests per second
        self.min_interval = 1.0 / rate if rate > 0 else 0
        self.last_request = 0.0
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Acquire permission to make a request."""
        async with self._lock:
            now = time.time()
            time_since_last = now - self.last_request
            
            if time_since_last < self.min_interval:
                sleep_time = self.min_interval - time_since_last
                # Yield control more frequently during rate limiting
                if sleep_time > 0.1:
                    # For longer sleeps, yield control periodically
                    while sleep_time > 0.1:
                        await asyncio.sleep(0.1)
                        sleep_time -= 0.1
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)
                else:
                    await asyncio.sleep(sleep_time)
            
            self.last_request = time.time()


class ConnectionPool:
    """Manages HTTP connections with pooling."""
    
    def __init__(self, max_connections: int = 20):
        self.max_connections = max_connections
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None
        self._semaphore = Semaphore(max_connections)
    
    async def __aenter__(self):
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def initialize(self):
        """Initialize the connection pool."""
        if self._session is None:
            self._connector = aiohttp.TCPConnector(
                limit=self.max_connections,
                limit_per_host=5,
                ttl_dns_cache=300,
                use_dns_cache=True,
            )
            
            timeout = aiohttp.ClientTimeout(total=settings.api.timeout)
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=timeout
            )
        
        return self._session
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get a session from the pool."""
        if self._session is None:
            await self.initialize()
        assert self._session is not None  # Help type checker
        return self._session
    
    async def close(self):
        """Close the connection pool."""
        if self._session:
            await self._session.close()
            self._session = None
        
        if self._connector:
            await self._connector.close()
            self._connector = None


class OptimizedGeneticAPIService:
    """Optimized genetic API service with advanced features."""
    
    def __init__(self):
        self.connection_pool = ConnectionPool(max_connections=settings.api.max_concurrent * 2)
        self.rate_limiters: Dict[str, RateLimiter] = {}
        self.endpoints = self._initialize_endpoints()
        self._cache: Dict[str, APIResponse] = {}
        self._initialized = False
    
    async def __aenter__(self):
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def initialize(self):
        """Initialize the service."""
        if not self._initialized:
            await self.connection_pool.initialize()
            self._initialized = True
    
    async def close(self):
        """Close the service and clean up resources."""
        await self.connection_pool.close()
        self._cache.clear()
        self._initialized = False
    
    def _initialize_endpoints(self) -> Dict[str, APIEndpoint]:
        """Initialize API endpoint configurations with optimized rate limits."""
        return {
            'ensembl_vep': APIEndpoint(
                url='https://rest.ensembl.org/vep/human/id/{rsid}',
                headers={'Content-Type': 'application/json'},
                rate_limit=15.0,  # Ensembl allows 15 requests/second
                timeout=15.0  # Reduced timeout for speed
            ),
            'clinvar': APIEndpoint(
                url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi',
                rate_limit=10.0,  # Increased from 3.0 for speed
                timeout=15.0
            ),
                        'pharmgkb': APIEndpoint(
                url='https://api.pharmgkb.org/v1/data/variant/{rsid}',
                timeout=15,
                rate_limit=2.0,  # Reduced from 10.0 to avoid rate limiting
                headers={'Accept': 'application/json'}
            ),
            'snpedia': APIEndpoint(
                url='https://bots.snpedia.com/api.php',
                rate_limit=2.0,  # Increased from 1.0 for speed
                timeout=15.0
            )
        }
    
    def _get_rate_limiter(self, endpoint_name: str) -> RateLimiter:
        """Get or create a rate limiter for an endpoint."""
        if endpoint_name not in self.rate_limiters:
            endpoint = self.endpoints.get(endpoint_name)
            rate = endpoint.rate_limit if endpoint else 1.0
            self.rate_limiters[endpoint_name] = RateLimiter(rate)
        
        return self.rate_limiters[endpoint_name]
    
    async def _make_request(
        self,
        endpoint_name: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        method: str = 'GET'
    ) -> APIResponse:
        """Make an HTTP request with rate limiting and retries."""
        if not self._initialized:
            await self.initialize()
        
        endpoint = self.endpoints.get(endpoint_name)
        if not endpoint:
            return APIResponse(
                success=False,
                error=f"Unknown endpoint: {endpoint_name}"
            )
        
        # Check cache first
        cache_key = f"{endpoint_name}:{url}:{str(params)}"
        if cache_key in self._cache:
            cached_response = self._cache[cache_key]
            # Use cached response if it's less than 1 hour old
            if time.time() - cached_response.response_time < 3600:
                return cached_response
        
        rate_limiter = self._get_rate_limiter(endpoint_name)
        session = await self.connection_pool.get_session()
        
        # Merge headers
        request_headers = endpoint.headers.copy() if endpoint.headers else {}
        if headers:
            request_headers.update(headers)
        
        start_time = time.time()
        
        for attempt in range(endpoint.max_retries):
            try:
                await rate_limiter.acquire()
                
                async with self.connection_pool._semaphore:
                    timeout = aiohttp.ClientTimeout(total=endpoint.timeout)
                    
                    async with session.request(
                        method=method,
                        url=url,
                        params=params,
                        headers=request_headers,
                        timeout=timeout
                    ) as response:
                        response_time = time.time() - start_time
                        
                        if response.status == 200:
                            try:
                                if 'application/json' in response.headers.get('content-type', ''):
                                    data = await response.json()
                                else:
                                    content = await response.text()
                                    data = {'content': content, 'content_type': response.headers.get('content-type')}
                                
                                api_response = APIResponse(
                                    success=True,
                                    data=data,
                                    status_code=response.status,
                                    response_time=response_time
                                )
                                
                                # Cache successful responses
                                self._cache[cache_key] = api_response
                                return api_response
                                
                            except Exception as e:
                                logger.error(f"Error parsing response from {endpoint_name}: {e}")
                                return APIResponse(
                                    success=False,
                                    error=f"Response parsing error: {str(e)}",
                                    status_code=response.status,
                                    response_time=response_time
                                )
                        
                        elif response.status == 429:  # Rate limited
                            if attempt < endpoint.max_retries - 1:
                                wait_time = (2 ** attempt) * 1.0  # Exponential backoff
                                logger.warning(f"Rate limited by {endpoint_name}, waiting {wait_time}s")
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                return APIResponse(
                                    success=False,
                                    error="Rate limit exceeded",
                                    status_code=response.status,
                                    response_time=response_time
                                )
                        
                        else:
                            error_msg = f"HTTP {response.status}"
                            try:
                                error_text = await response.text()
                                if error_text:
                                    error_msg += f": {error_text[:200]}"
                            except Exception:
                                pass
                            
                            if attempt < endpoint.max_retries - 1:
                                wait_time = (2 ** attempt) * 0.5
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                return APIResponse(
                                    success=False,
                                    error=error_msg,
                                    status_code=response.status,
                                    response_time=response_time
                                )
            
            except asyncio.TimeoutError:
                if attempt < endpoint.max_retries - 1:
                    wait_time = (2 ** attempt) * 1.0
                    logger.warning(f"Timeout for {endpoint_name}, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    return APIResponse(
                        success=False,
                        error="Request timeout",
                        response_time=time.time() - start_time
                    )
            
            except Exception as e:
                if attempt < endpoint.max_retries - 1:
                    wait_time = (2 ** attempt) * 1.0
                    logger.warning(f"Error with {endpoint_name}: {e}, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    return APIResponse(
                        success=False,
                        error=f"Request failed: {str(e)}",
                        response_time=time.time() - start_time
                    )
        
        return APIResponse(
            success=False,
            error="Max retries exceeded",
            response_time=time.time() - start_time
        )
    
    async def annotate_variant(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive annotation for a variant from ALL sources."""
        if not rsid or not rsid.startswith('rs'):
            return None
        
        # Run ALL annotation sources concurrently for maximum speed
        tasks = [
            self._get_ensembl_annotation(rsid),
            self._get_clinvar_annotation(rsid),
            self._get_pharmgkb_annotation(rsid),
            self._get_snpedia_annotation(rsid),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        annotation = {
            'rsid': rsid,
            'annotations': {},
            'sources_queried': ['ensembl', 'clinvar', 'pharmgkb', 'snpedia'],
            'success_count': 0
        }
        
        # Process Ensembl result
        if not isinstance(results[0], Exception) and results[0]:
            annotation['annotations']['ensembl'] = results[0]
            annotation['success_count'] += 1
        
        # Process ClinVar result
        if not isinstance(results[1], Exception) and results[1]:
            annotation['annotations']['clinvar'] = results[1]
            annotation['success_count'] += 1
        
        # Process PharmGKB result
        if not isinstance(results[2], Exception) and results[2]:
            annotation['annotations']['pharmgkb'] = results[2]
            annotation['success_count'] += 1
        
        # Process SNPedia result
        if not isinstance(results[3], Exception) and results[3]:
            annotation['annotations']['snpedia'] = results[3]
            annotation['success_count'] += 1
        
        return annotation if annotation['success_count'] > 0 else None
    
    async def annotate_variant_minimal(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive annotation - no more minimal mode."""
        # Always use full comprehensive annotation
        return await self.annotate_variant(rsid)
    
    async def annotate_variant_comprehensive(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive annotation - same as standard now."""
        # Always use full comprehensive annotation
        return await self.annotate_variant(rsid)
    
    async def _get_ensembl_annotation(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Get Ensembl VEP annotation."""
        try:
            url = self.endpoints['ensembl_vep'].url.format(rsid=rsid)
            response = await self._make_request('ensembl_vep', url)
            
            if response.success and response.data:
                return {
                    'found': True,
                    'source': 'ensembl',
                    'data': response.data
                }
            
            return {'found': False, 'source': 'ensembl', 'error': response.error}
            
        except Exception as e:
            logger.error(f"Ensembl annotation error for {rsid}: {e}")
            return {'found': False, 'source': 'ensembl', 'error': str(e)}
    
    async def _get_clinvar_annotation(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Get ClinVar annotation."""
        try:
            params = {
                'db': 'clinvar',
                'term': f'{rsid}[RS]',
                'retmode': 'json',
                'retmax': 5
            }
            
            response = await self._make_request('clinvar', self.endpoints['clinvar'].url, params=params)
            
            if response.success and response.data:
                search_result = response.data.get('esearchresult', {})
                count = int(search_result.get('count', 0))
                
                return {
                    'found': count > 0,
                    'source': 'clinvar',
                    'count': count,
                    'ids': search_result.get('idlist', [])
                }
            
            return {'found': False, 'source': 'clinvar', 'error': response.error}
            
        except Exception as e:
            logger.error(f"ClinVar annotation error for {rsid}: {e}")
            return {'found': False, 'source': 'clinvar', 'error': str(e)}
    
    async def _get_pharmgkb_annotation(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Get PharmGKB annotation."""
        try:
            url = self.endpoints['pharmgkb'].url.format(rsid=rsid)
            response = await self._make_request('pharmgkb', url)
            
            if response.success and response.data:
                return {
                    'found': True,
                    'source': 'pharmgkb',
                    'data': response.data
                }
            
            return {'found': False, 'source': 'pharmgkb', 'error': response.error}
            
        except Exception as e:
            logger.error(f"PharmGKB annotation error for {rsid}: {e}")
            return {'found': False, 'source': 'pharmgkb', 'error': str(e)}
    
    async def _get_snpedia_annotation(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Get SNPedia annotation."""
        try:
            params = {
                'action': 'query',
                'format': 'json',
                'titles': rsid,
                'prop': 'revisions',
                'rvprop': 'content'
            }
            
            response = await self._make_request('snpedia', self.endpoints['snpedia'].url, params=params)
            
            if response.success and response.data:
                pages = response.data.get('query', {}).get('pages', {})
                if pages:
                    page_data = next(iter(pages.values()))
                    if 'revisions' in page_data:
                        return {
                            'found': True,
                            'source': 'snpedia',
                            'data': page_data
                        }
            
            return {'found': False, 'source': 'snpedia', 'error': response.error}
            
        except Exception as e:
            logger.error(f"SNPedia annotation error for {rsid}: {e}")
            return {'found': False, 'source': 'snpedia', 'error': str(e)}
    
    async def batch_annotate_variants(self, rsids: List[str], strategy: str = 'comprehensive') -> Dict[str, Optional[Dict[str, Any]]]:
        """Annotate multiple variants in batch - always comprehensive."""
        if not rsids:
            return {}
        
        # Always use comprehensive annotation regardless of strategy
        annotation_method = self.annotate_variant
        
        # Process in controlled batches with maximum concurrency
        batch_size = min(settings.api.batch_size, 5)  # Very small batches for responsiveness
        semaphore = Semaphore(min(settings.api.max_concurrent, 3))  # Limit concurrency
        
        async def annotate_with_semaphore(rsid: str):
            async with semaphore:
                return await annotation_method(rsid)
        
        results = {}
        for i in range(0, len(rsids), batch_size):
            batch = rsids[i:i + batch_size]
            tasks = [annotate_with_semaphore(rsid) for rsid in batch]
            
            # Yield control before processing each batch
            await asyncio.sleep(0.01)
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Yield control after processing each batch
            await asyncio.sleep(0.01)
            
            for rsid, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Batch annotation error for {rsid}: {result}")
                    results[rsid] = None
                else:
                    results[rsid] = result
        
        return results


# Legacy compatibility wrapper
class GeneticAPIService:
    """Legacy compatibility wrapper for existing code."""
    
    def __init__(self):
        self.optimized_service = OptimizedGeneticAPIService()
        self._initialized = False
    
    async def initialize(self):
        """Initialize the service."""
        if not self._initialized:
            await self.optimized_service.initialize()
            self._initialized = True
    
    async def close(self):
        """Close the service."""
        await self.optimized_service.close()
        self._initialized = False

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False

    async def annotate_variant(self, rsid: str, gene: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Variant annotation - gene param accepted for API compat but unused."""
        if not self._initialized:
            await self.initialize()
        result = await self.optimized_service.annotate_variant(rsid)
        if result and gene:
            result['gene'] = gene
        return result
    
    async def annotate_variant_minimal(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Legacy method for minimal annotation."""
        if not self._initialized:
            await self.initialize()
        return await self.optimized_service.annotate_variant_minimal(rsid)
    
    async def annotate_variant_comprehensive(self, rsid: str) -> Optional[Dict[str, Any]]:
        """Legacy method for comprehensive annotation."""
        if not self._initialized:
            await self.initialize()
        return await self.optimized_service.annotate_variant_comprehensive(rsid)

    async def batch_annotate_variants(self, variants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Batch annotate variants from a list of dicts with rsid keys."""
        if not self._initialized:
            await self.initialize()
        rsids = [v.get('rsid', '') for v in variants]
        results_dict = await self.optimized_service.batch_annotate_variants(rsids)
        results = []
        for v in variants:
            rsid = v.get('rsid', '')
            annotation = results_dict.get(rsid)
            results.append({
                'rsid': rsid,
                'gene': v.get('gene'),
                'annotations': annotation.get('annotations', {}) if annotation else {},
                'error': None if annotation else 'Annotation not found'
            })
        return results

    async def get_variant_clinical_summary(self, rsid: str, gene: Optional[str] = None) -> Dict[str, Any]:
        """Get clinical summary by aggregating all annotation sources."""
        if not self._initialized:
            await self.initialize()
        annotation = await self.optimized_service.annotate_variant(rsid)
        
        summary: Dict[str, Any] = {
            'rsid': rsid,
            'gene': gene,
            'clinical_significance': 'unknown',
            'population_frequency': None,
            'drug_responses': [],
            'literature_count': 0,
            'sources': [],
        }
        
        if not annotation:
            return summary
        
        annotations = annotation.get('annotations', {})
        
        # Extract ClinVar data
        clinvar = annotations.get('clinvar', {})
        if clinvar.get('found'):
            summary['sources'].append('clinvar')
            summary['clinical_significance'] = 'reported_in_clinvar'
            summary['clinvar_ids'] = clinvar.get('ids', [])
        
        # Extract Ensembl data
        ensembl = annotations.get('ensembl', {})
        if ensembl.get('found'):
            summary['sources'].append('ensembl')
            data = ensembl.get('data', [])
            if isinstance(data, list) and data:
                vep = data[0] if data else {}
                freqs = vep.get('colocated_variants', [{}])
                if freqs:
                    freq_data = freqs[0].get('frequencies', {})
                    if freq_data:
                        summary['population_frequency'] = freq_data
                consequences = vep.get('most_severe_consequence', '')
                if consequences:
                    summary['consequence'] = consequences
        
        # Extract PharmGKB data
        pharmgkb = annotations.get('pharmgkb', {})
        if pharmgkb.get('found'):
            summary['sources'].append('pharmgkb')
        
        # Extract SNPedia data
        snpedia = annotations.get('snpedia', {})
        if snpedia.get('found'):
            summary['sources'].append('snpedia')
        
        return summary

    async def get_litvar_publications(self, rsid: str) -> Dict[str, Any]:
        """Get literature publications for a variant."""
        if not self._initialized:
            await self.initialize()
        # LitVar not implemented in optimized service, return empty result
        return {'rsid': rsid, 'publications': [], 'count': 0}

    async def get_pharmgkb_drug_info(self, gene: str) -> Dict[str, Any]:
        """Get pharmacogenomic info for a gene."""
        if not self._initialized:
            await self.initialize()
        # Delegate to PharmGKB annotation using gene as search term
        result = await self.optimized_service._get_pharmgkb_annotation(gene)
        return result or {'gene': gene, 'found': False, 'drug_responses': []}

    async def get_snpedia_info(self, rsid: str) -> Dict[str, Any]:
        """Get SNPedia info for a variant."""
        if not self._initialized:
            await self.initialize()
        result = await self.optimized_service._get_snpedia_annotation(rsid)
        return result or {'rsid': rsid, 'found': False}

    async def get_variant_info_from_ensembl(self, rsid: str) -> Dict[str, Any]:
        """Get Ensembl VEP info for a variant."""
        if not self._initialized:
            await self.initialize()
        result = await self.optimized_service._get_ensembl_annotation(rsid)
        return result or {'rsid': rsid, 'found': False}

    async def get_variant_info_from_clinvar(self, rsid: str) -> Dict[str, Any]:
        """Get ClinVar info for a variant."""
        if not self._initialized:
            await self.initialize()
        result = await self.optimized_service._get_clinvar_annotation(rsid)
        return result or {'rsid': rsid, 'found': False}