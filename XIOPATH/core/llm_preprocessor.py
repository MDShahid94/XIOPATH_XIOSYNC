import json
import hashlib
import logging
from typing import Dict, List, Any
from core.gemini_engine import GeminiEngine

logger = logging.getLogger(__name__)


class PreFlightValidator:
    """
    LLM Preprocessing Engine.
    Analyzes Workflow Graphs before execution to ensure all required 
    data is provided. Replaces `<REDACTED>` values dynamically.
    """
    # E-19: Class-level intent mapping cache
    _intent_cache: Dict[str, str] = {}
    _CACHE_MAX = 128

    def __init__(self, llm: GeminiEngine):
        self.llm = llm
        
        self.intent_mapping_instruction = """
        You are a Semantic Intent Router. The user has provided a natural language request.
        You must map their request to exactly ONE of the canonical intents available for this domain.
        If none match closely, respond with 'UNKNOWN'.
        Return ONLY the raw string of the canonical intent.
        """
        
        self.branch_evaluator_instruction = """
        You are a Workflow Graph Router. A workflow has reached a fork with multiple possible next nodes.
        You are provided with the current state variables extracted from previous steps, and the available next node intents.
        Evaluate the state variables to determine which node logically follows next.
        Return ONLY the raw string of the exact next intent you choose.
        """
        
        self.extraction_instruction = """
        You are a Data Preprocessor for an AI Agent.
        The user wants to execute a workflow that requires specific parameters.
        Your job is to extract any required parameters from the user's prompt.
        
        If ALL required parameters are present, respond with a JSON object:
        {
            "status": "READY",
            "context": { "param_name": "extracted_value" }
        }
        
        If ANY required parameters are missing, respond with a JSON object 
        asking a consolidated question for ALL missing parameters:
        {
            "status": "MISSING_DATA",
            "question": "To complete this workflow, I need the following information: 1. [param_1], 2. [param_2]..."
        }
        """

    def analyze_graph(self, graph_node: Dict) -> List[str]:
        """
        Recursively scans a Workflow Graph to find all missing or `<REDACTED>` parameters.
        """
        required_params = set()
        
        def traverse(node: Dict):
            if not node:
                return
                
            # Check action_params
            params = node.get("action_params", {})
            if params.get("text") == "<REDACTED>":
                required_params.add(f"input_for_{node['intent']}")
            elif isinstance(params.get("text"), str) and params["text"].startswith("{") and params["text"].endswith("}"):
                required_params.add(params["text"].strip("{}"))
                
            # Check place_value
            place_val = node.get("place_value", {})
            if place_val.get("input_data") == "<REDACTED>":
                required_params.add(f"input_for_{node['intent']}")
            elif isinstance(place_val.get("input_data"), str) and place_val["input_data"].startswith("{") and place_val["input_data"].endswith("}"):
                required_params.add(place_val["input_data"].strip("{}"))
                
            # Check explicitly declared face_value inputs
            face_val = node.get("face_value", {})
            if "required_inputs" in face_val and isinstance(face_val["required_inputs"], dict):
                for k in face_val["required_inputs"].keys():
                    required_params.add(k)
                    
            for next_node in node.get("next_nodes", []):
                traverse(next_node)
                
        traverse(graph_node)
        return list(required_params)

    def process_intent(self, user_prompt: str, required_params: List[str], previous_context: Dict = None) -> Dict:
        """
        Calls the LLM to map the user prompt to the required parameters.
        Returns {"status": "READY" | "MISSING_DATA", "context": {...}, "question": "..."}
        """
        if not required_params:
            return {"status": "READY", "context": {}}
            
        previous_context = previous_context or {}
        
        # Check if all required params are already in previous_context
        if all(p in previous_context for p in required_params):
            return {"status": "READY", "context": previous_context}
            
        prompt = (
            f"User Prompt: '{user_prompt}'\n"
            f"Already Provided Context: {json.dumps(previous_context)}\n"
            f"Required Parameters: {required_params}\n"
        )
        
        try:
            res = self.llm.ask(self.extraction_instruction, prompt)
            
            if res.get("status") == "READY":
                # Merge with previous context
                merged = {**previous_context, **res.get("context", {})}
                return {"status": "READY", "context": merged}
            else:
                return {
                    "status": "MISSING_DATA", 
                    "question": res.get("question", "Please provide the missing data.")
                }
        except Exception as e:
            return {"status": "MISSING_DATA", "question": f"Error extracting parameters: {str(e)}"}

    def map_intent_to_canonical(self, user_prompt: str, available_intents: List[str]) -> str:
        """Maps a natural language prompt to a known canonical intent from the database."""
        if not available_intents:
            return user_prompt  # Fallback if no intents exist yet

        # E-19: Check cache first
        cache_key = hashlib.sha256(
            f"{user_prompt}|{'|'.join(sorted(available_intents))}".encode()
        ).hexdigest()[:16]
        if cache_key in self._intent_cache:
            logger.debug(f"Intent cache hit: '{user_prompt}' → '{self._intent_cache[cache_key]}'")
            return self._intent_cache[cache_key]

        prompt = (
            f"User Prompt: '{user_prompt}'\n"
            f"Available Canonical Intents: {json.dumps(available_intents)}\n"
            "Which canonical intent best matches the user's prompt? Output ONLY the intent string."
        )
        
        result = user_prompt  # Default fallback to raw prompt
        try:
            res = self.llm.ask_raw(self.intent_mapping_instruction, prompt)
            mapped = res.strip('\'" \n')

            # E-18: Case-insensitive matching
            intent_map = {i.lower(): i for i in available_intents}
            if mapped.lower() in intent_map:
                result = intent_map[mapped.lower()]
            else:
                # Partial / substring match fallback
                for intent in available_intents:
                    if mapped.lower() in intent.lower() or intent.lower() in mapped.lower():
                        logger.info(f"Fuzzy intent match: '{mapped}' → '{intent}'")
                        result = intent
                        break
                else:
                    # No match at all — fall back to raw prompt
                    logger.info(f"No intent match for LLM output '{mapped}'. Using raw prompt.")
        except Exception as e:
            logger.warning(f"Intent mapping failed: {e}. Falling back to raw prompt.")

        # E-19: Cache the result (bounded LRU)
        if len(self._intent_cache) >= self._CACHE_MAX:
            oldest = next(iter(self._intent_cache))
            del self._intent_cache[oldest]
        self._intent_cache[cache_key] = result

        return result
        
    def evaluate_branch(self, next_nodes: List[str], workflow_vars: Dict) -> str:
        """Dynamically selects the next workflow node based on execution state."""
        if not workflow_vars:
            # If no state to evaluate, default to first node
            return next_nodes[0]
            
        prompt = (
            f"Current Workflow Variables (State): {json.dumps(workflow_vars)}\n"
            f"Available Next Nodes: {json.dumps(next_nodes)}\n"
            "Based on the variables, which node should be executed next? Output ONLY the string."
        )
        
        try:
            res = self.llm.ask_raw(self.branch_evaluator_instruction, prompt)
            selected = res.strip('\'" \n')
            if selected in next_nodes:
                logger.info(f"Branch evaluator chose: '{selected}' from {next_nodes}")
                return selected
        except Exception as e:
            logger.warning(f"Branch evaluator failed: {e}. Defaulting to first node.")
            
        return next_nodes[0]  # Fallback to first node
