"""
XIOPATH — Workflow Orchestrator (Phase W.4)
=============================================
Coordinates multiple workflow executions with lifecycle management:
start, pause, resume, cancel, status tracking.

Each workflow gets a unique execution ID and tracked state.
"""

import uuid
import time
import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowExecution:
    """Tracks a single workflow's execution state."""
    id: str
    workflow_intent: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_node: Optional[str] = None
    visited_nodes: List[str] = field(default_factory=list)
    start_time: float = 0.0
    end_time: Optional[float] = None
    execution_context: Dict = field(default_factory=dict)
    result: Optional[Any] = None
    error: Optional[str] = None
    
    @property
    def duration_seconds(self) -> float:
        end = self.end_time or time.time()
        return round(end - self.start_time, 2) if self.start_time else 0.0
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "workflow_intent": self.workflow_intent,
            "status": self.status.value,
            "current_node": self.current_node,
            "visited_nodes": self.visited_nodes,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "has_result": self.result is not None,
            "error": self.error,
        }


class WorkflowOrchestrator:
    """
    Coordinates multiple workflow executions with lifecycle management.
    
    Provides:
    - Start/cancel/pause/resume operations
    - Execution state tracking
    - Concurrent workflow limits
    - Event callbacks for status changes
    
    Usage:
        orchestrator = WorkflowOrchestrator(agent_loop, max_concurrent=3)
        exec_id = await orchestrator.start_workflow("login", {"username": "test"})
        status = orchestrator.get_status(exec_id)
        await orchestrator.cancel_workflow(exec_id)
    """
    
    def __init__(self, agent_loop, max_concurrent: int = 5):
        self.agent_loop = agent_loop
        self.max_concurrent = max_concurrent
        self.executions: Dict[str, WorkflowExecution] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._pause_events: Dict[str, asyncio.Event] = {}
    
    async def start_workflow(self, intent: str, context: Dict = None) -> str:
        """
        Start a new workflow execution.
        
        Args:
            intent: The workflow intent to execute
            context: Execution context (variables, parameters)
            
        Returns:
            Unique execution ID
            
        Raises:
            RuntimeError: If max concurrent workflows reached
        """
        active = self.list_active()
        if len(active) >= self.max_concurrent:
            raise RuntimeError(
                f"Max concurrent workflows ({self.max_concurrent}) reached. "
                f"Cancel or wait for existing workflows to complete."
            )
        
        exec_id = str(uuid.uuid4())
        execution = WorkflowExecution(
            id=exec_id,
            workflow_intent=intent,
            status=WorkflowStatus.PENDING,
            execution_context=context or {},
        )
        self.executions[exec_id] = execution
        self._pause_events[exec_id] = asyncio.Event()
        self._pause_events[exec_id].set()  # Not paused initially
        
        # Launch as background task
        task = asyncio.create_task(self._run_workflow(exec_id))
        self._tasks[exec_id] = task
        
        logger.info(f"[Orchestrator] Started workflow '{intent}' as execution {exec_id}")
        return exec_id
    
    async def _run_workflow(self, exec_id: str):
        """Internal: execute the workflow and track state."""
        execution = self.executions.get(exec_id)
        if not execution:
            return
        
        execution.status = WorkflowStatus.RUNNING
        execution.start_time = time.time()
        
        try:
            # Resolve the workflow graph
            url = self.agent_loop.browser.page.url
            intent = execution.workflow_intent
            
            graph = self.agent_loop.memory.get_workflow_graph(
                url, intent,
                self.agent_loop.context_dict,
                self.agent_loop.max_fallback_tier
            )
            
            if not graph:
                execution.status = WorkflowStatus.FAILED
                execution.error = f"Workflow graph not found for intent: {intent}"
                execution.end_time = time.time()
                return
            
            # W.4: Pause checkpoint — blocks here if workflow is paused
            pause_event = self._pause_events.get(exec_id)
            if pause_event:
                await pause_event.wait()  # Blocks if event is cleared (paused)
            
            # Execute the graph (pass pause_event for per-node checkpoints)
            success = await self.agent_loop._execute_workflow_graph(
                graph, execution.execution_context, pause_event=pause_event
            )
            
            execution.result = success
            execution.status = WorkflowStatus.COMPLETED if success else WorkflowStatus.FAILED
            if not success:
                execution.error = "Workflow execution returned failure"
                
        except asyncio.CancelledError:
            execution.status = WorkflowStatus.CANCELLED
            logger.info(f"[Orchestrator] Workflow {exec_id} cancelled")
        except Exception as e:
            execution.status = WorkflowStatus.FAILED
            execution.error = str(e)
            logger.error(f"[Orchestrator] Workflow {exec_id} failed: {e}")
        finally:
            execution.end_time = time.time()
            self._tasks.pop(exec_id, None)
            self._pause_events.pop(exec_id, None)
    
    async def cancel_workflow(self, exec_id: str) -> bool:
        """Cancel a running workflow."""
        task = self._tasks.get(exec_id)
        if task and not task.done():
            task.cancel()
            execution = self.executions.get(exec_id)
            if execution:
                execution.status = WorkflowStatus.CANCELLED
                execution.end_time = time.time()
            logger.info(f"[Orchestrator] Cancelled workflow {exec_id}")
            return True
        return False
    
    async def pause_workflow(self, exec_id: str) -> bool:
        """Pause a running workflow (best-effort — pauses between nodes)."""
        event = self._pause_events.get(exec_id)
        execution = self.executions.get(exec_id)
        if event and execution and execution.status == WorkflowStatus.RUNNING:
            event.clear()  # Block the workflow at next check point
            execution.status = WorkflowStatus.PAUSED
            logger.info(f"[Orchestrator] Paused workflow {exec_id}")
            return True
        return False
    
    async def resume_workflow(self, exec_id: str) -> bool:
        """Resume a paused workflow."""
        event = self._pause_events.get(exec_id)
        execution = self.executions.get(exec_id)
        if event and execution and execution.status == WorkflowStatus.PAUSED:
            execution.status = WorkflowStatus.RUNNING
            event.set()  # Unblock the workflow
            logger.info(f"[Orchestrator] Resumed workflow {exec_id}")
            return True
        return False
    
    def get_status(self, exec_id: str) -> Optional[Dict]:
        """Get current execution status as dict."""
        execution = self.executions.get(exec_id)
        return execution.to_dict() if execution else None
    
    def list_active(self) -> List[Dict]:
        """List all active (running/paused/pending) workflow executions."""
        active_statuses = {WorkflowStatus.RUNNING, WorkflowStatus.PAUSED, WorkflowStatus.PENDING}
        return [
            e.to_dict() for e in self.executions.values()
            if e.status in active_statuses
        ]
    
    def list_all(self, limit: int = 50) -> List[Dict]:
        """List all workflow executions (most recent first)."""
        sorted_execs = sorted(
            self.executions.values(),
            key=lambda e: e.start_time,
            reverse=True
        )
        return [e.to_dict() for e in sorted_execs[:limit]]
    
    def cleanup_completed(self, max_age_seconds: int = 3600) -> int:
        """Remove completed/failed/cancelled executions older than max_age."""
        now = time.time()
        terminal_statuses = {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED}
        to_remove = [
            eid for eid, e in self.executions.items()
            if e.status in terminal_statuses and e.end_time and (now - e.end_time) > max_age_seconds
        ]
        for eid in to_remove:
            del self.executions[eid]
        return len(to_remove)
