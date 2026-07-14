"""
XIOPATH — Plugin Registry (Phase E.1)
========================================
Central registry for all plugins with manifest-based discovery,
lifecycle management (load → enable → execute → disable → unload),
and versioned metadata.

Replaces the basic PluginManager with a full registry while
maintaining backwards compatibility with the existing `run()` interface.
"""

import importlib
import json
import logging
import sys
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Set, List, Optional, Callable
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Plugin Manifest
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class PluginManifest:
    """Declarative metadata for a plugin."""
    name: str                                    # Unique identifier (e.g. "captcha_solver")
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    category: str = "action"                     # "action" | "detector" | "transformer" | "integration"
    entry_point: str = "run"                     # Async function name to invoke
    required_permissions: List[str] = field(default_factory=list)  # e.g. ["page.fill", "page.click"]
    compatible_actions: List[str] = field(default_factory=list)    # Action types this plugin handles
    config_schema: Dict = field(default_factory=dict)              # JSON schema for plugin config
    enabled: bool = True
    marketplace_id: Optional[str] = None         # If published to marketplace

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> 'PluginManifest':
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_file(cls, path: Path) -> 'PluginManifest':
        with open(path, 'r') as f:
            return cls.from_dict(json.load(f))


# ═══════════════════════════════════════════════════════════════════════════
# Plugin Lifecycle States
# ═══════════════════════════════════════════════════════════════════════════

PLUGIN_STATES = {
    "discovered": "Plugin file found but not loaded",
    "loaded": "Module imported successfully",
    "enabled": "Ready for execution",
    "disabled": "Loaded but not available for execution",
    "error": "Failed to load or execute",
    "unloaded": "Module removed from registry",
}


@dataclass
class PluginEntry:
    """Runtime state for a registered plugin."""
    manifest: PluginManifest
    state: str = "discovered"
    module: Any = None
    load_time: Optional[str] = None
    last_executed: Optional[str] = None
    execution_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None

    def to_dict(self) -> Dict:
        d = self.manifest.to_dict()
        d.update({
            "state": self.state,
            "load_time": self.load_time,
            "last_executed": self.last_executed,
            "execution_count": self.execution_count,
            "error_count": self.error_count,
            "last_error": self.last_error,
        })
        return d


# ═══════════════════════════════════════════════════════════════════════════
# Plugin Registry
# ═══════════════════════════════════════════════════════════════════════════

class PluginRegistry:
    """
    Central plugin registry with discovery, lifecycle, and execution.

    Discovery: Scans plugins/ dir for plugin.json manifests or bare .py files.
    Lifecycle: discovered → loaded → enabled ⇄ disabled → unloaded
    Execution: Delegates to the plugin's entry_point function.

    Backwards-compatible: Plugins without manifests get auto-generated ones.
    """

    # Security: Only allowlisted plugins can execute
    ALLOWED_PLUGINS: Set[str] = set()

    def __init__(self, plugin_dir: str = "plugins"):
        self.plugin_dir = Path(plugin_dir)
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self._registry: Dict[str, PluginEntry] = {}
        self._module_prefix = self.plugin_dir.name  # e.g. "plugins"

        # Ensure plugins dir is importable
        parent = str(self.plugin_dir.absolute().parent)
        if parent not in sys.path:
            sys.path.insert(0, parent)
        importlib.invalidate_caches()

    # ─── Discovery ────────────────────────────────────────────────

    def discover(self) -> List[str]:
        """
        Scan the plugins directory for plugins.
        A plugin is either:
        1. A directory with plugin.json manifest
        2. A bare .py file (gets auto-manifest)
        """
        discovered = []

        # 1. Scan for manifest-based plugins (subdirectories)
        for manifest_path in self.plugin_dir.glob("*/plugin.json"):
            try:
                manifest = PluginManifest.from_file(manifest_path)
                if manifest.name not in self._registry:
                    self._registry[manifest.name] = PluginEntry(
                        manifest=manifest,
                        state="discovered",
                    )
                    discovered.append(manifest.name)
            except Exception as e:
                logger.warning(f"Failed to parse manifest {manifest_path}: {e}")

        # 2. Scan for bare .py files (legacy plugins)
        for py_file in self.plugin_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            name = py_file.stem
            if name not in self._registry:
                manifest = PluginManifest(
                    name=name,
                    description=f"Auto-discovered plugin: {name}",
                    category="action",
                )
                self._registry[name] = PluginEntry(
                    manifest=manifest,
                    state="discovered",
                )
                discovered.append(name)

        logger.info(f"Discovered {len(discovered)} plugins: {discovered}")
        return discovered

    # ─── Lifecycle ────────────────────────────────────────────────

    def load(self, name: str) -> bool:
        """Import the plugin module."""
        entry = self._registry.get(name)
        if not entry:
            logger.error(f"Plugin '{name}' not in registry")
            return False

        try:
            module_name = f"{self._module_prefix}.{name}"
            # Check if it's a package (directory) or module (file)
            pkg_init = self.plugin_dir / name / "__init__.py"
            if pkg_init.exists():
                module_name = f"{self._module_prefix}.{name}"

            entry.module = importlib.import_module(module_name)
            entry.state = "loaded"
            entry.load_time = datetime.now(timezone.utc).isoformat()

            # Validate entry point exists
            if not hasattr(entry.module, entry.manifest.entry_point):
                logger.warning(f"Plugin '{name}' missing entry point '{entry.manifest.entry_point}'")
                entry.state = "error"
                entry.last_error = f"Missing entry point: {entry.manifest.entry_point}"
                return False

            logger.info(f"Loaded plugin: {name} v{entry.manifest.version}")
            return True
        except Exception as e:
            entry.state = "error"
            entry.last_error = str(e)
            logger.error(f"Failed to load plugin '{name}': {e}")
            return False

    def enable(self, name: str) -> bool:
        """Mark a loaded plugin as available for execution."""
        entry = self._registry.get(name)
        if not entry:
            return False
        if entry.state not in ("loaded", "disabled"):
            logger.warning(f"Cannot enable plugin '{name}' in state '{entry.state}'")
            return False
        entry.state = "enabled"
        self.ALLOWED_PLUGINS.add(name)
        logger.info(f"Enabled plugin: {name}")
        return True

    def disable(self, name: str) -> bool:
        """Disable a plugin without unloading."""
        entry = self._registry.get(name)
        if not entry:
            return False
        entry.state = "disabled"
        self.ALLOWED_PLUGINS.discard(name)
        logger.info(f"Disabled plugin: {name}")
        return True

    def unload(self, name: str) -> bool:
        """Remove a plugin from the registry."""
        entry = self._registry.get(name)
        if not entry:
            return False
        # Remove from sys.modules if loaded
        module_name = f"{self._module_prefix}.{name}"
        if module_name in sys.modules:
            del sys.modules[module_name]
        entry.module = None
        entry.state = "unloaded"
        self.ALLOWED_PLUGINS.discard(name)
        logger.info(f"Unloaded plugin: {name}")
        return True

    def load_all(self) -> Dict[str, bool]:
        """Discover and load all plugins."""
        self.discover()
        results = {}
        for name in list(self._registry.keys()):
            loaded = self.load(name)
            if loaded:
                self.enable(name)
            results[name] = loaded
        return results

    # ─── Execution ────────────────────────────────────────────────

    async def execute(
        self,
        name: str,
        page: Any = None,
        action_params: Dict = None,
        workflow_vars: Dict = None,
        config: Dict = None,
    ) -> bool:
        """
        Execute a plugin by name.
        Backwards-compatible with PluginManager.execute_plugin().
        """
        entry = self._registry.get(name)
        if not entry:
            logger.error(f"Plugin '{name}' not found in registry")
            return False

        if entry.state != "enabled":
            logger.error(f"Plugin '{name}' not enabled (state: {entry.state})")
            return False

        if name not in self.ALLOWED_PLUGINS:
            logger.error(f"Plugin '{name}' not in allowlist")
            return False

        try:
            fn = getattr(entry.module, entry.manifest.entry_point)
            result = await fn(page, action_params or {}, workflow_vars or {})
            entry.execution_count += 1
            entry.last_executed = datetime.now(timezone.utc).isoformat()
            logger.info(f"Executed plugin '{name}': result={result}")
            return bool(result)
        except Exception as e:
            entry.error_count += 1
            entry.last_error = str(e)
            logger.error(f"Plugin '{name}' execution failed: {e}")
            return False

    # ─── Backwards Compatibility ──────────────────────────────────

    async def execute_plugin(
        self,
        plugin_name: str,
        page: Any,
        action_params: Dict,
        workflow_vars: Dict,
    ) -> bool:
        """Drop-in replacement for PluginManager.execute_plugin()."""
        # Auto-discover and load if not yet in registry
        if plugin_name not in self._registry:
            self.discover()
            if plugin_name in self._registry:
                self.load(plugin_name)
                self.enable(plugin_name)

        return await self.execute(plugin_name, page, action_params, workflow_vars)

    # ─── Query ────────────────────────────────────────────────────

    def list_plugins(self, state: str = None) -> List[Dict]:
        """List all registered plugins, optionally filtered by state."""
        plugins = []
        for name, entry in self._registry.items():
            if state and entry.state != state:
                continue
            plugins.append(entry.to_dict())
        return plugins

    def get_plugin(self, name: str) -> Optional[Dict]:
        """Get a single plugin's info."""
        entry = self._registry.get(name)
        return entry.to_dict() if entry else None

    def get_by_category(self, category: str) -> List[Dict]:
        """Get plugins by category."""
        return [
            e.to_dict() for e in self._registry.values()
            if e.manifest.category == category
        ]

    def get_by_action(self, action_type: str) -> List[Dict]:
        """Find plugins that handle a specific action type."""
        return [
            e.to_dict() for e in self._registry.values()
            if action_type in e.manifest.compatible_actions and e.state == "enabled"
        ]

    @property
    def count(self) -> int:
        return len(self._registry)

    @property
    def enabled_count(self) -> int:
        return sum(1 for e in self._registry.values() if e.state == "enabled")
