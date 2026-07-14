import asyncio
from typing import Dict, Any, Optional
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from mcp.server.fastmcp import FastMCP
from memory_manager import MemoryManager

# Create FastMCP server
mcp = FastMCP("memory-mcp")
memory_mgr = MemoryManager("mcp-agent-session")

@mcp.tool()
def lookup_action(url: str, intent: str, context_hash: str = "default") -> Optional[Dict[str, Any]]:
    """
    Look up a previously learned action from Long-Term Memory.
    Returns the FACE (semantic) and PLACE (DOM) values if found.
    Supports explicitly named workflows via '#' (e.g. '#amazon_checkout').
    """
    return memory_mgr.lookup_action(url, intent, {"context_hash": context_hash})

@mcp.tool()
def get_available_intents(url: str) -> str:
    """
    Get a list of all known semantic intents for the given domain.
    Useful for LLM preprocessing to map natural language to exact canonical intents.
    """
    import json
    intents = memory_mgr.get_available_intents(url)
    return json.dumps(intents)

@mcp.tool()
def save_new_action(url: str, intent: str, face_value: str, place_value: str, action_type: str, action_params: str, previous_intent: str = "", context_hash: str = "default", visibility: str = "public", volatility_type: str = "static", fallback_plugin: str = "", output_var: str = "") -> str:
    """
    Save a successful browser interaction to Client Secondary Memory.
    face_value should be a JSON string of semantic details.
    place_value should be a JSON string of DOM properties.
    visibility should be 'public' or 'private'.
    """
    import json
    face_val_dict = json.loads(face_value) if isinstance(face_value, str) else face_value
    place_val_dict = json.loads(place_value) if isinstance(place_value, str) else place_value
    action_params_dict = json.loads(action_params) if isinstance(action_params, str) else action_params
    
    memory_mgr.save_new_action(
        url, intent, face_val_dict, place_val_dict, action_type, action_params_dict, 
        previous_intent if previous_intent else None, context_hash, visibility,
        volatility_type, fallback_plugin if fallback_plugin else None, output_var if output_var else None
    )
    return f"Saved action for intent '{intent}' to [LS] Local Secondary!"

@mcp.tool()
def update_healed_step(url: str, intent: str, new_place_value: str, context_hash: str = "default") -> str:
    """
    Update a healed PLACE value in memory so future runs won't break.
    """
    import json
    action = memory_mgr.lookup_action(url, intent, {"context_hash": context_hash})
    if not action:
        return f"Error: No memory found for intent '{intent}' at '{url}'"
    
    new_place_dict = json.loads(new_place_value) if isinstance(new_place_value, str) else new_place_value
    
    # Save it back (this effectively updates the secondary memory)
    memory_mgr.save_new_action(url, intent, action.get("face_value", {}), new_place_dict, action.get("action_type", ""), action.get("action_params", {}), None, context_hash, action.get("visibility", "public"))
    return f"Successfully updated healed PLACE value for '{intent}'!"

@mcp.tool()
def promote_action(url: str, intent: str, context_hash: str = "default") -> str:
    """
    Promote an action in Local Secondary Memory. If it reaches the threshold, it elevates to Local Primary.
    """
    action = memory_mgr.lookup_action(url, intent, {"context_hash": context_hash})
    if not action:
        return f"Error: No memory found for intent '{intent}' at '{url}'"
    memory_mgr.promote_client_secondary(action["id"])
    return f"Promoted action '{intent}' in client hierarchy!"

@mcp.tool()
def semantic_search(url: str, query: str, context_hash: str = "default", top_k: int = 3) -> str:
    """
    Semantic vector search using a natural language query.
    Returns matching structural memory elements across all tiers (LP -> GP -> LS -> GS).
    """
    import json
    results = memory_mgr.semantic_lookup(url, query, context_hash, top_k)
    return json.dumps(results, indent=2)

@mcp.tool()
def get_workflow_graph(url: str, start_intent: str, context_hash: str = "default", max_depth: int = 10) -> str:
    """
    Fetch a complete workflow sequence starting from the given intent.
    Supports explicitly named workflows via '#' (e.g. '#amazon_checkout').
    """
    import json
    results = memory_mgr.get_workflow_graph(url, start_intent, context_hash, max_depth)
    if not results:
        return f"Error: No memory found for intent '{start_intent}' at '{url}'"
    return json.dumps(results, indent=2)

if __name__ == "__main__":
    mcp.run(transport='stdio')
