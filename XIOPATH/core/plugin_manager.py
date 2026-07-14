import importlib
import logging
import sys
from pathlib import Path
from typing import Dict, Any, Set

logger = logging.getLogger(__name__)

class PluginManager:
    """
    Dynamically loads and executes Python plugins from the /plugins directory.
    This acts as the 'Action Healing' engine for volatile/non-deterministic nodes.
    
    F-20: Plugin allowlist for security. When populated, only listed plugins can execute.
    """
    # Configurable allowlist — empty means allow all (adjustable via admin panel in future)
    ALLOWED_PLUGINS: Set[str] = set()

    def __init__(self, plugin_dir: str = "plugins"):
        self.plugin_dir = Path(plugin_dir)
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        
        # Ensure plugins dir is in sys.path so importlib can find it
        if str(self.plugin_dir.absolute().parent) not in sys.path:
            sys.path.append(str(self.plugin_dir.absolute().parent))

    async def execute_plugin(self, plugin_name: str, page: Any, action_params: Dict[str, Any], workflow_vars: Dict[str, Any]) -> bool:
        """
        Dynamically loads the specified plugin module and executes its async `run()` function.
        F-20: Enforces allowlist when populated. Removed importlib.reload() to prevent side effects.
        """
        logger.info(f"[PluginManager] Attempting to load and execute plugin: {plugin_name}")

        # C7 Fix: Deny-by-default — block all plugins unless explicitly allowlisted.
        # Previously: empty set = allow all (dangerous). Now: empty set = deny all.
        if plugin_name not in self.ALLOWED_PLUGINS:
            logger.error(f"[PluginManager] Plugin '{plugin_name}' denied — not in allowlist. "
                         f"Add it to PluginManager.ALLOWED_PLUGINS to permit execution.")
            return False
        
        try:
            # Dynamically import the module (no reload — F-20)
            module_name = f"plugins.{plugin_name}"
            plugin_module = importlib.import_module(module_name)
            
            if not hasattr(plugin_module, "run"):
                logger.error(f"[PluginManager] Plugin '{plugin_name}' missing required async 'run' method.")
                return False
                
            # Execute the plugin's run method
            logger.info(f"[PluginManager] Yielding execution control to {plugin_name}.run()")
            result = await plugin_module.run(page, action_params, workflow_vars)
            
            logger.info(f"[PluginManager] Plugin '{plugin_name}' executed successfully.")
            return result
            
        except ModuleNotFoundError:
            logger.error(f"[PluginManager] Plugin module '{plugin_name}' not found in {self.plugin_dir}")
            return False
        except Exception as e:
            logger.error(f"[PluginManager] Exception during plugin execution '{plugin_name}': {e}")
            return False
