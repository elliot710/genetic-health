"""
Analysis Job Queue Manager for handling concurrent genetic analysis requests
Ensures proper resource allocation and prevents user interference
"""
import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class QueuedAnalysis:
    """Represents a queued analysis job"""
    analysis_id: int
    user_id: int
    priority: int = 0  # Higher numbers = higher priority
    queued_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.queued_at is None:
            self.queued_at = datetime.utcnow()

class AnalysisQueue:
    """
    Manages a queue of analysis jobs to prevent resource conflicts
    between multiple users running analyses simultaneously
    """
    
    def __init__(self, max_concurrent_jobs: int = 3):
        self.max_concurrent_jobs = max_concurrent_jobs
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running_jobs: Dict[int, QueuedAnalysis] = {}  # analysis_id -> QueuedAnalysis
        self._user_running_count: Dict[int, int] = {}  # user_id -> count of running jobs
        self._queued_analysis_ids: set = set()  # Track which analysis IDs are in queue
        self._queued_user_ids: Dict[int, int] = {}  # analysis_id -> user_id for queued items
        self._jobs_lock = asyncio.Lock()  # Protects _running_jobs, _user_running_count, and queued sets
        self._processing_task: Optional[asyncio.Task] = None
        self._shutdown = False
        
    async def start(self):
        """Start the queue processor"""
        if self._processing_task is None or self._processing_task.done():
            self._processing_task = asyncio.create_task(self._process_queue())
            logger.info("Analysis queue processor started")
    
    async def stop(self):
        """Stop the queue processor"""
        self._shutdown = True
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        logger.info("Analysis queue processor stopped")
    
    async def enqueue_analysis(
        self,
        analysis_id: int,
        user_id: int,
        priority: int = 0,
        _bypass_limit: bool = False,
    ) -> bool:
        """
        Add an analysis to the queue
        
        Args:
            analysis_id: ID of the analysis to process
            user_id: ID of the user who owns the analysis
            priority: Priority level (higher = more important)
            _bypass_limit: Skip per-user limit (used for startup recovery)
            
        Returns:
            True if successfully queued, False if already running/queued
        """
        # Check if this analysis is already running or queued
        async with self._jobs_lock:
            if analysis_id in self._running_jobs:
                logger.warning(f"Analysis {analysis_id} is already running")
                return False
            
            # Check for duplicate in queue
            if analysis_id in self._queued_analysis_ids:
                logger.warning(f"Analysis {analysis_id} is already queued")
                return False
            
            if not _bypass_limit:
                # Count this user's queued + running jobs
                user_running_count = self._user_running_count.get(user_id, 0)
                user_queued_count = sum(
                    1 for aid in self._queued_analysis_ids
                    if self._queued_user_ids.get(aid) == user_id
                )
                
                if user_queued_count + user_running_count >= 2:
                    logger.warning(f"User {user_id} has reached maximum concurrent analysis limit")
                    return False
        
            self._queued_analysis_ids.add(analysis_id)
            self._queued_user_ids[analysis_id] = user_id
        
        queued_analysis = QueuedAnalysis(
            analysis_id=analysis_id,
            user_id=user_id,
            priority=priority
        )
        
        await self._queue.put(queued_analysis)
        logger.info(f"Queued analysis {analysis_id} for user {user_id} (priority: {priority})")
        
        # Ensure the processor is running
        await self.start()
        
        return True
    
    async def _process_queue(self):
        """Main queue processing loop"""
        logger.info("Starting analysis queue processing loop")
        
        while not self._shutdown:
            try:
                # Check if we can start more jobs
                if len(self._running_jobs) >= self.max_concurrent_jobs:
                    await asyncio.sleep(1)  # Wait before checking again
                    continue
                
                # Get next job from queue (with timeout to allow checking shutdown)
                try:
                    queued_analysis = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
                # Start the analysis job
                await self._start_analysis_job(queued_analysis)
                
            except Exception as e:
                logger.error(f"Error in queue processing: {e}")
                await asyncio.sleep(1)
    
    async def _start_analysis_job(self, queued_analysis: QueuedAnalysis):
        """Start an individual analysis job"""
        analysis_id = queued_analysis.analysis_id
        user_id = queued_analysis.user_id
        
        # Mark as running (protected by lock for atomic counter updates)
        async with self._jobs_lock:
            queued_analysis.started_at = datetime.utcnow()
            self._running_jobs[analysis_id] = queued_analysis
            self._user_running_count[user_id] = self._user_running_count.get(user_id, 0) + 1
            self._queued_analysis_ids.discard(analysis_id)
            self._queued_user_ids.pop(analysis_id, None)
        
        logger.info(f"Starting analysis {analysis_id} for user {user_id}")
        
        # Import here to avoid circular dependencies
        from .analysis_service import ComprehensiveAnalysisService
        
        # Create and run the comprehensive analysis service
        analysis_service = ComprehensiveAnalysisService(user_id=user_id)
        
        async def run_job():
            try:
                result = await analysis_service.process_analysis(analysis_id)
                logger.info(f"Completed analysis {analysis_id} for user {user_id}")
                return result
            except Exception as e:
                logger.error(f"Analysis {analysis_id} failed for user {user_id}: {e}")
                raise
            finally:
                # Clean up — protected by lock for atomic counter updates
                async with self._jobs_lock:
                    self._running_jobs.pop(analysis_id, None)
                    current_count = self._user_running_count.get(user_id, 0)
                    if current_count > 1:
                        self._user_running_count[user_id] = current_count - 1
                    else:
                        self._user_running_count.pop(user_id, None)
        
        # Start the job as a background task
        asyncio.create_task(run_job())
    
    def get_queue_status(self) -> Dict:
        """Get current queue status"""
        return {
            "queue_size": self._queue.qsize(),
            "running_jobs": len(self._running_jobs),
            "max_concurrent": self.max_concurrent_jobs,
            "running_analyses": [
                {
                    "analysis_id": analysis.analysis_id,
                    "user_id": analysis.user_id,
                    "started_at": analysis.started_at.isoformat() if analysis.started_at else None
                }
                for analysis in self._running_jobs.values()
            ],
            "user_running_counts": dict(self._user_running_count)
        }
    
    def is_analysis_running(self, analysis_id: int) -> bool:
        """Check if a specific analysis is currently running"""
        return analysis_id in self._running_jobs

# Global queue instance
_analysis_queue: Optional[AnalysisQueue] = None

def get_analysis_queue() -> AnalysisQueue:
    """Get or create the global analysis queue"""
    global _analysis_queue
    if _analysis_queue is None:
        _analysis_queue = AnalysisQueue(max_concurrent_jobs=3)
    return _analysis_queue

async def queue_analysis(analysis_id: int, user_id: int, priority: int = 0) -> bool:
    """
    Queue an analysis for processing
    
    Args:
        analysis_id: ID of the analysis to process
        user_id: ID of the user who owns the analysis
        priority: Priority level (higher = more important)
        
    Returns:
        True if successfully queued, False if already running/queued
    """
    queue = get_analysis_queue()
    return await queue.enqueue_analysis(analysis_id, user_id, priority)

def get_queue_status() -> Dict:
    """Get current queue status"""
    queue = get_analysis_queue()
    return queue.get_queue_status()