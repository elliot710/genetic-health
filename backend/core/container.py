"""
Dependency injection container for managing service dependencies.
"""
from typing import Dict, Any, Optional, TypeVar, Type, Callable
from abc import ABC, abstractmethod
import asyncio
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ServiceContainer:
    """Simple dependency injection container."""
    
    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._singletons: Dict[str, Any] = {}
        self._transients: set = set()  # factory names that should NOT be cached
        self._initialized: bool = False
    
    def register_singleton(self, service_name: str, instance: Any):
        """Register a singleton service instance."""
        self._singletons[service_name] = instance
    
    def register_factory(self, service_name: str, factory: Callable):
        """Register a factory function for creating service instances."""
        self._factories[service_name] = factory
    
    def register_class(self, service_name: str, service_class: Type[T], *args, **kwargs) -> None:
        """Register a class to be instantiated with given arguments."""
        def factory():
            return service_class(*args, **kwargs)
        self._factories[service_name] = factory
    
    def register_transient(self, service_name: str, service_class: Type[T], *args, **kwargs) -> None:
        """Register a class that creates a new instance on every get() call (not cached)."""
        def factory():
            return service_class(*args, **kwargs)
        self._factories[service_name] = factory
        self._transients.add(service_name)
    
    def get(self, service_name: str) -> Any:
        """Get a service instance."""
        # Check singletons first
        if service_name in self._singletons:
            return self._singletons[service_name]
        
        # Check if we have a factory
        if service_name in self._factories:
            instance = self._factories[service_name]()
            # Only promote to singleton if not registered as transient
            if service_name not in self._transients:
                self._singletons[service_name] = instance
            return instance
        
        raise ValueError(f"Service '{service_name}' not registered")
    
    async def initialize_async_services(self):
        """Initialize all async services."""
        if self._initialized:
            return
        
        for service_name, service in self._singletons.items():
            if hasattr(service, 'initialize') and callable(service.initialize):
                try:
                    if asyncio.iscoroutinefunction(service.initialize):
                        await service.initialize()
                    else:
                        service.initialize()
                    logger.info(f"Initialized service: {service_name}")
                except Exception as e:
                    logger.error(f"Failed to initialize service {service_name}: {e}")
        
        self._initialized = True
    
    async def cleanup(self):
        """Clean up all services."""
        for service_name, service in self._singletons.items():
            if hasattr(service, 'close') and callable(service.close):
                try:
                    if asyncio.iscoroutinefunction(service.close):
                        await service.close()
                    else:
                        service.close()
                    logger.info(f"Cleaned up service: {service_name}")
                except Exception as e:
                    logger.error(f"Failed to cleanup service {service_name}: {e}")
        
        self._singletons.clear()
        self._initialized = False


class ServiceInterface(ABC):
    """Base interface for all services."""
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the service."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close the service and clean up resources."""
        pass


class HealthInsightsServiceInterface(ServiceInterface):
    """Interface for health insights service."""
    
    @abstractmethod
    async def generate_health_insights(self, analysis_id: int) -> Dict[str, Any]:
        """Generate health insights for an analysis."""
        pass


class DrugResponseServiceInterface(ServiceInterface):
    """Interface for drug response service."""
    
    @abstractmethod
    async def generate_drug_responses(self, analysis_id: int) -> Dict[str, Any]:
        """Generate drug response analysis for an analysis."""
        pass


# Global service container
container = ServiceContainer()


def setup_services():
    """Set up all service dependencies."""
    # Import here to avoid circular imports
    from ..services.genetic_api_service import OptimizedGeneticAPIService
    
    # Register services — API service is transient (new instance per consumer)
    # to avoid shared in-memory cache leaking data between users
    container.register_transient('api_service', OptimizedGeneticAPIService)
    
    logger.info("Services registered in container")


async def initialize_services():
    """Initialize all services."""
    await container.initialize_async_services()


async def cleanup_services():
    """Clean up all services."""
    await container.cleanup()


def get_service(service_name: str) -> Any:
    """Get a service from the container."""
    return container.get(service_name)


class ServiceManager:
    """Manages the lifecycle of all services."""
    
    def __init__(self):
        self._initialized = False
    
    async def __aenter__(self):
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
    
    async def initialize(self):
        """Initialize all services."""
        if not self._initialized:
            setup_services()
            await initialize_services()
            self._initialized = True
    
    async def cleanup(self):
        """Clean up all services."""
        if self._initialized:
            await cleanup_services()
            self._initialized = False
    
    def get_analysis_service(self, user_id: Optional[int] = None):
        """Get a configured analysis service."""
        from ..services.analysis_service import ComprehensiveAnalysisService
        
        return ComprehensiveAnalysisService(user_id=user_id)