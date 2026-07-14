import asyncio
import copy
from typing import Any, List, Optional
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_google_genai import ChatGoogleGenerativeAI
from .api_manager import ApiManager

# Global API manager instance
_api_manager = ApiManager()

def _handle_error(e: Exception, current_key: str):
    err_msg = str(e).lower()
    if "429" in err_msg or "quota" in err_msg or "too many requests" in err_msg or "exhausted" in err_msg:
        print(f"\n[API Manager] Rate limit hit for key ending in {current_key[-4:]}. Rotating...")
        _api_manager.mark_cooling(current_key, err_msg)
    elif "403" in err_msg or "401" in err_msg or "invalid" in err_msg or "permission" in err_msg:
        print(f"\n[API Manager] Key ending in {current_key[-4:]} expired or invalid. Removing...")
        _api_manager.mark_expired(current_key)
    else:
        raise e

def _update_tokens(result: ChatResult, current_key: str):
    if result.llm_output and "token_usage" in result.llm_output:
        tokens = result.llm_output["token_usage"].get("total_tokens", 0)
        if tokens == 0 and hasattr(result.llm_output.get("token_usage"), "total_tokens"):
             tokens = result.llm_output["token_usage"].total_tokens
        if type(tokens) == int:
            _api_manager.update_tokens(current_key, tokens)

# Save original methods
_orig_generate = ChatGoogleGenerativeAI._generate
_orig_agenerate = ChatGoogleGenerativeAI._agenerate

def _clean_tool_calls(result: ChatResult):
    """
    browser-use and Gemini have a known bug where list fields in Pydantic models 
    are generated as {"items": [...]} instead of just a list.
    We intercept the ChatResult and unwrap any 'items' dicts.
    """
    if result.generations:
        for gen in result.generations:
            msg = gen.message
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    if "args" in tc and isinstance(tc["args"], dict):
                        for k, v in tc["args"].items():
                            if isinstance(v, dict) and "items" in v:
                                tc["args"][k] = v["items"]
                            elif isinstance(v, list):
                                # Also fix nested arrays in action list
                                for i, item in enumerate(v):
                                    if isinstance(item, dict) and "items" in item:
                                        v[i] = item["items"]

def smart_generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, run_manager=None, **kwargs) -> ChatResult:
    max_retries = len(_api_manager.keys) + 2
    for attempt in range(max_retries):
        current_key = _api_manager.get_next_key()
        self.google_api_key = current_key
        try:
            result = _orig_generate(self, messages, stop, run_manager, **kwargs)
            _clean_tool_calls(result)
            _update_tokens(result, current_key)
            return result
        except Exception as e:
            _handle_error(e, current_key)
    raise Exception("Smart API Picker: Exhausted all retries and keys.")

async def smart_agenerate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, run_manager=None, **kwargs) -> ChatResult:
    max_retries = len(_api_manager.keys) + 2
    for attempt in range(max_retries):
        current_key = _api_manager.get_next_key()
        self.google_api_key = current_key
        try:
            result = await _orig_agenerate(self, messages, stop, run_manager, **kwargs)
            _clean_tool_calls(result)
            _update_tokens(result, current_key)
            return result
        except Exception as e:
            _handle_error(e, current_key)
    raise Exception("Smart API Picker: Exhausted all retries and keys.")

# Monkey patch the class
ChatGoogleGenerativeAI._generate = smart_generate
ChatGoogleGenerativeAI._agenerate = smart_agenerate

# Fix for browser_use checks
ChatGoogleGenerativeAI.provider = property(lambda self: "google")
ChatGoogleGenerativeAI.model_name = property(lambda self: self.model)

def SmartGeminiLLM() -> ChatGoogleGenerativeAI:
    """Returns a patched ChatGoogleGenerativeAI instance."""
    # We must instantiate it with a dummy key initially, but it will be swapped dynamically on generate
    return ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=_api_manager.get_next_key()
    )

