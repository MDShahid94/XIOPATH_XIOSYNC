"""
XIOPATH — Master Workflow Agent (Phase W.6)
=============================================
Meta-agent that decomposes a high-level goal into a plan of
sub-workflows, coordinates their execution order, handles
data passing between workflows, and retries failed sub-plans.

Example:
    User: "Scrape product prices from amazon, compare with ebay, save to spreadsheet"
    MWA decomposes into:
      1. workflow: "scrape amazon prices" → output: prices_amazon
      2. workflow: "scrape ebay prices"   → output: prices_ebay   (parallel with 1)
      3. workflow: "compare prices"       → inputs: prices_amazon, prices_ebay
      4. workflow: "save to sheets"       → inputs: comparison_result
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SubWorkflowPlan:
    """A single sub-workflow in the decomposition plan."""
    id: str
    intent: str
    input_vars: List[str] = field(default_factory=list)
    output_var: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)  # IDs of sub-workflows this depends on
    status: str = "pending"  # pending, running, completed, failed, skipped
    result: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class GoalExecution:
    """Tracks a full goal decomposition and execution."""
    id: str
    goal: str
    sub_workflows: List[SubWorkflowPlan] = field(default_factory=list)
    status: str = "pending"
    start_time: float = 0.0
    end_time: Optional[float] = None
    collected_vars: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status,
            "sub_workflows": [
                {
                    "id": sw.id, "intent": sw.intent,
                    "depends_on": sw.depends_on, "output_var": sw.output_var,
                    "status": sw.status, "error": sw.error,
                }
                for sw in self.sub_workflows
            ],
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": round((self.end_time or time.time()) - self.start_time, 2) if self.start_time else 0,
        }


class MasterWorkflowAgent:
    """
    Meta-agent that decomposes a high-level goal into sub-workflows,
    builds a dependency DAG, and executes them (parallel where possible).
    
    Follows the "Everything is an Agent" principle — the MWA itself
    is an agent that coordinates other workflow agents.
    """
    
    DECOMPOSE_PROMPT = """You are a Workflow Decomposition Agent. Given a complex user goal, 
break it down into atomic sub-workflows that can be executed sequentially or in parallel.

For each sub-workflow, specify:
- "intent": A clear, canonical intent string (e.g., "scrape_amazon_prices")
- "input_vars": List of variable names this workflow needs as input (empty if none)
- "output_var": Name of the variable this workflow produces (null if none)
- "depends_on": List of intent strings this workflow depends on (for data flow)

Respond ONLY with a JSON array of sub-workflow objects. Order them logically.
Workflows with no dependencies on each other should be marked for parallel execution.

Example:
[
    {"intent": "scrape_amazon_prices", "input_vars": [], "output_var": "prices_amazon", "depends_on": []},
    {"intent": "scrape_ebay_prices", "input_vars": [], "output_var": "prices_ebay", "depends_on": []},
    {"intent": "compare_prices", "input_vars": ["prices_amazon", "prices_ebay"], "output_var": "comparison", "depends_on": ["scrape_amazon_prices", "scrape_ebay_prices"]},
    {"intent": "save_to_sheets", "input_vars": ["comparison"], "output_var": null, "depends_on": ["compare_prices"]}
]
"""
    
    def __init__(self, agent_loop, llm):
        self.agent_loop = agent_loop
        self.llm = llm
        self.goal_executions: Dict[str, GoalExecution] = {}
    
    async def execute_goal(self, goal: str, context: Dict = None) -> Dict:
        """
        Decompose a complex goal into sub-workflows and execute them.
        
        Args:
            goal: High-level natural language goal
            context: Optional initial context variables
            
        Returns:
            Dict with execution results
        """
        exec_id = str(uuid.uuid4())
        execution = GoalExecution(
            id=exec_id,
            goal=goal,
            start_time=time.time(),
            collected_vars=context.copy() if context else {},
        )
        self.goal_executions[exec_id] = execution
        
        try:
            # Step 1: Decompose goal into sub-workflows
            sub_plans = self._decompose_goal(goal)
            if not sub_plans:
                execution.status = "failed"
                execution.end_time = time.time()
                return {"status": "failed", "error": "Could not decompose goal into sub-workflows"}
            
            execution.sub_workflows = sub_plans
            execution.status = "running"
            
            # Step 2: Build and execute DAG
            success = await self._execute_dag(execution)
            
            execution.status = "completed" if success else "failed"
            execution.end_time = time.time()
            
            return {
                "status": execution.status,
                "execution_id": exec_id,
                "sub_workflows": len(sub_plans),
                "collected_vars": execution.collected_vars,
                "details": execution.to_dict(),
            }
            
        except Exception as e:
            logger.error(f"[MWA] Goal execution failed: {e}")
            execution.status = "failed"
            execution.end_time = time.time()
            return {"status": "failed", "error": str(e)}
    
    def _decompose_goal(self, goal: str) -> List[SubWorkflowPlan]:
        """Use LLM to break a complex goal into atomic sub-workflows."""
        try:
            response = self.llm.ask(
                self.DECOMPOSE_PROMPT,
                f"User Goal: {goal}\n\nDecompose into sub-workflows:"
            )
            
            # Response should be a list of dicts
            if isinstance(response, list):
                plans = []
                for i, item in enumerate(response):
                    plans.append(SubWorkflowPlan(
                        id=f"sw_{i}_{item.get('intent', 'unknown')}",
                        intent=item.get("intent", f"step_{i}"),
                        input_vars=item.get("input_vars", []),
                        output_var=item.get("output_var"),
                        depends_on=item.get("depends_on", []),
                    ))
                logger.info(f"[MWA] Decomposed goal into {len(plans)} sub-workflows")
                return plans
            else:
                logger.warning(f"[MWA] LLM returned non-list response: {type(response)}")
                # Fallback: treat the whole goal as a single workflow
                return [SubWorkflowPlan(
                    id="sw_0_fallback",
                    intent=goal,
                    input_vars=[],
                    output_var=None,
                    depends_on=[],
                )]
                
        except Exception as e:
            logger.error(f"[MWA] Goal decomposition failed: {e}")
            return []
    
    async def _execute_dag(self, execution: GoalExecution) -> bool:
        """
        Execute sub-workflows respecting their dependency DAG.
        Parallelizes independent sub-workflows using asyncio.gather().
        """
        # Build intent → plan mapping
        intent_map = {sw.intent: sw for sw in execution.sub_workflows}
        completed_intents = set()
        
        max_iterations = len(execution.sub_workflows) + 1  # Safety limit
        iteration = 0
        
        while len(completed_intents) < len(execution.sub_workflows):
            iteration += 1
            if iteration > max_iterations:
                logger.error("[MWA] DAG execution exceeded max iterations — possible deadlock")
                return False
            
            # Find all sub-workflows ready to run (dependencies satisfied)
            ready = [
                sw for sw in execution.sub_workflows
                if sw.status == "pending"
                and all(dep in completed_intents for dep in sw.depends_on)
            ]
            
            if not ready:
                # Check if we're stuck (remaining workflows have unsatisfied deps)
                pending = [sw for sw in execution.sub_workflows if sw.status == "pending"]
                if pending:
                    logger.error(f"[MWA] Deadlock: {len(pending)} workflows pending but none ready")
                    for sw in pending:
                        sw.status = "failed"
                        sw.error = "Deadlock: dependencies cannot be satisfied"
                    return False
                break
            
            # Execute all ready workflows in parallel
            if len(ready) > 1:
                logger.info(f"[MWA] Executing {len(ready)} sub-workflows in parallel: {[sw.intent for sw in ready]}")
                tasks = [self._run_sub_workflow(sw, execution) for sw in ready]
                await asyncio.gather(*tasks)
            else:
                await self._run_sub_workflow(ready[0], execution)
            
            # Update completed set
            for sw in execution.sub_workflows:
                if sw.status == "completed":
                    completed_intents.add(sw.intent)
        
        # Check if all succeeded
        all_success = all(sw.status == "completed" for sw in execution.sub_workflows)
        return all_success
    
    async def _run_sub_workflow(self, sw: SubWorkflowPlan, execution: GoalExecution):
        """Execute a single sub-workflow within the DAG context."""
        sw.status = "running"
        logger.info(f"[MWA] Running sub-workflow: {sw.intent}")
        
        try:
            # Build context from collected vars
            context = {}
            for var_name in sw.input_vars:
                if var_name in execution.collected_vars:
                    context[var_name] = execution.collected_vars[var_name]
                else:
                    logger.warning(f"[MWA] Missing input var '{var_name}' for sub-workflow '{sw.intent}'")
            
            # Try to find and execute the workflow graph
            url = self.agent_loop.browser.page.url
            graph = self.agent_loop.memory.get_workflow_graph(
                url, sw.intent,
                self.agent_loop.context_dict,
                self.agent_loop.max_fallback_tier
            )
            
            if graph:
                success = await self.agent_loop._execute_workflow_graph(graph, context)
            else:
                # No existing workflow — use chat_step as fallback
                logger.info(f"[MWA] No graph found for '{sw.intent}', using LLM chat_step")
                result = await self.agent_loop.chat_step(sw.intent)
                success = result is True or result is not False
            
            if success:
                sw.status = "completed"
                # Collect output variable if defined
                if sw.output_var and sw.output_var in self.agent_loop.workflow_vars:
                    execution.collected_vars[sw.output_var] = self.agent_loop.workflow_vars[sw.output_var]
                    sw.result = execution.collected_vars[sw.output_var]
            else:
                sw.status = "failed"
                sw.error = f"Sub-workflow execution returned failure"
                
        except Exception as e:
            sw.status = "failed"
            sw.error = str(e)
            logger.error(f"[MWA] Sub-workflow '{sw.intent}' failed: {e}")
    
    def get_goal_status(self, exec_id: str) -> Optional[Dict]:
        """Get the status of a goal execution."""
        execution = self.goal_executions.get(exec_id)
        return execution.to_dict() if execution else None
    
    def list_goals(self, limit: int = 20) -> List[Dict]:
        """List recent goal executions."""
        sorted_execs = sorted(
            self.goal_executions.values(),
            key=lambda e: e.start_time,
            reverse=True
        )
        return [e.to_dict() for e in sorted_execs[:limit]]
