"""
XIOPATH — Phase E Tests
=========================
Tests for Plugin Registry (E.1), Action Builder (E.2), and API integration.
"""

import pytest
import uuid
from core.plugin_registry import PluginRegistry, PluginManifest, PluginEntry
from core.action_builder import ActionBuilder, CustomAction, ActionStep, STEP_TYPES


# ═══════════════════════════════════════════════════════════════════════════
# E.1: Plugin Registry Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPluginManifest:
    def test_manifest_creation(self):
        m = PluginManifest(name="test_plugin", version="2.0.0", category="detector")
        assert m.name == "test_plugin"
        assert m.version == "2.0.0"
        assert m.category == "detector"
        assert m.entry_point == "run"

    def test_manifest_to_dict_roundtrip(self):
        m = PluginManifest(
            name="roundtrip",
            version="1.0.0",
            description="Test",
            compatible_actions=["click", "fill"],
        )
        d = m.to_dict()
        m2 = PluginManifest.from_dict(d)
        assert m2.name == m.name
        assert m2.compatible_actions == ["click", "fill"]

    def test_manifest_extra_keys_ignored(self):
        d = {"name": "safe", "unknown_field": "ignored"}
        m = PluginManifest.from_dict(d)
        assert m.name == "safe"


class TestPluginRegistry:
    def test_registry_init(self, tmp_path):
        reg = PluginRegistry(plugin_dir=str(tmp_path / "testplugins_init"))
        assert reg.count == 0

    def test_discover_bare_py(self, tmp_path):
        pdir = tmp_path / "testplugins_discover"
        pdir.mkdir()
        (pdir / "__init__.py").write_text("")
        (pdir / "my_plugin.py").write_text("async def run(page, params, vars): return True")
        reg = PluginRegistry(plugin_dir=str(pdir))
        discovered = reg.discover()
        assert "my_plugin" in discovered
        assert reg.count == 1

    def test_lifecycle_states(self, tmp_path):
        pdir = tmp_path / f"test_plugins_{id(self)}"
        pdir.mkdir()
        (pdir / "__init__.py").write_text("")
        (pdir / "lifecycle_test.py").write_text("async def run(p, a, w): return True")
        reg = PluginRegistry(plugin_dir=str(pdir))
        reg.discover()
        entry = reg._registry["lifecycle_test"]
        assert entry.state == "discovered"

        reg.load("lifecycle_test")
        assert reg._registry["lifecycle_test"].state == "loaded"

        reg.enable("lifecycle_test")
        assert reg._registry["lifecycle_test"].state == "enabled"
        assert "lifecycle_test" in reg.ALLOWED_PLUGINS

        reg.disable("lifecycle_test")
        assert reg._registry["lifecycle_test"].state == "disabled"
        assert "lifecycle_test" not in reg.ALLOWED_PLUGINS

        reg.unload("lifecycle_test")
        assert reg._registry["lifecycle_test"].state == "unloaded"

    def test_load_all(self, tmp_path):
        pdir = tmp_path / f"test_plugins_{id(self)}"
        pdir.mkdir()
        (pdir / "__init__.py").write_text("")
        (pdir / "a.py").write_text("async def run(p, a, w): return True")
        (pdir / "b.py").write_text("async def run(p, a, w): return False")
        reg = PluginRegistry(plugin_dir=str(pdir))
        results = reg.load_all()
        assert results["a"] is True
        assert results["b"] is True
        assert reg.enabled_count == 2

    def test_list_plugins_filter(self, tmp_path):
        pdir = tmp_path / f"test_plugins_{id(self)}"
        pdir.mkdir()
        (pdir / "__init__.py").write_text("")
        (pdir / "x.py").write_text("async def run(p, a, w): return True")
        reg = PluginRegistry(plugin_dir=str(pdir))
        reg.load_all()
        all_plugins = reg.list_plugins()
        assert len(all_plugins) == 1
        enabled = reg.list_plugins(state="enabled")
        assert len(enabled) == 1
        disabled = reg.list_plugins(state="disabled")
        assert len(disabled) == 0

    def test_execute_enabled_plugin(self, tmp_path):
        import asyncio
        pdir = tmp_path / f"test_plugins_{id(self)}"
        pdir.mkdir()
        (pdir / "__init__.py").write_text("")
        (pdir / "runner.py").write_text("async def run(page, params, wvars):\n    return True")
        reg = PluginRegistry(plugin_dir=str(pdir))
        reg.load_all()
        result = asyncio.run(reg.execute("runner", None, {}, {}))
        assert result is True
        info = reg.get_plugin("runner")
        assert info["execution_count"] == 1

    def test_execute_disabled_denied(self, tmp_path):
        import asyncio
        pdir = tmp_path / f"test_plugins_{id(self)}"
        pdir.mkdir()
        (pdir / "__init__.py").write_text("")
        (pdir / "blocked.py").write_text("async def run(p, a, w): return True")
        reg = PluginRegistry(plugin_dir=str(pdir))
        reg.load_all()
        reg.disable("blocked")
        result = asyncio.run(reg.execute("blocked", None, {}, {}))
        assert result is False

    def test_get_plugin_info(self, tmp_path):
        pdir = tmp_path / f"test_plugins_{id(self)}"
        pdir.mkdir()
        (pdir / "__init__.py").write_text("")
        (pdir / "info_test.py").write_text("async def run(p, a, w): return True")
        reg = PluginRegistry(plugin_dir=str(pdir))
        reg.load_all()
        info = reg.get_plugin("info_test")
        assert info is not None
        assert info["name"] == "info_test"
        assert info["state"] == "enabled"
        assert info["execution_count"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# E.2: Action Builder Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestActionStep:
    def test_valid_step(self):
        step = ActionStep("click", {"selector": "#btn"}, label="Click button")
        errors = step.validate()
        assert len(errors) == 0

    def test_unknown_step_type(self):
        step = ActionStep("explode", {})
        errors = step.validate()
        assert any("Unknown" in e for e in errors)

    def test_missing_required_param(self):
        step = ActionStep("navigate", {})
        errors = step.validate()
        assert any("url" in e for e in errors)

    def test_step_roundtrip(self):
        step = ActionStep("fill", {"selector": "#email", "value": "test"}, label="Email")
        d = step.to_dict()
        step2 = ActionStep.from_dict(d)
        assert step2.step_type == "fill"
        assert step2.params["value"] == "test"


class TestCustomAction:
    def test_valid_action(self):
        action = CustomAction(
            id="act_test",
            name="Test Action",
            steps=[ActionStep("click", {"selector": "#btn"})],
        )
        errors = action.validate()
        assert len(errors) == 0

    def test_empty_name_fails(self):
        action = CustomAction(id="x", name="", steps=[ActionStep("click", {"selector": "#a"})])
        errors = action.validate()
        assert any("name" in e.lower() for e in errors)

    def test_empty_steps_fails(self):
        action = CustomAction(id="x", name="Test", steps=[])
        errors = action.validate()
        assert any("step" in e.lower() for e in errors)

    def test_invalid_step_propagates(self):
        action = CustomAction(
            id="x",
            name="Test",
            steps=[ActionStep("navigate", {})],
        )
        errors = action.validate()
        assert len(errors) > 0
        assert any("url" in e for e in errors)


class TestActionBuilder:
    def test_templates_preloaded(self):
        builder = ActionBuilder()
        templates = builder.get_templates()
        assert len(templates) == 3
        names = [t["name"] for t in templates]
        assert "Login Flow" in names
        assert "Page Scraper" in names
        assert "Form Filler" in names

    def test_create_action(self):
        builder = ActionBuilder()
        action = CustomAction(
            id="act_custom1",
            name="My Action",
            steps=[ActionStep("click", {"selector": "#go"})],
            tags=["test"],
        )
        result = builder.create(action)
        assert result["success"] is True
        assert result["action"]["name"] == "My Action"

    def test_create_invalid_fails(self):
        builder = ActionBuilder()
        action = CustomAction(id="x", name="", steps=[])
        result = builder.create(action)
        assert result["success"] is False
        assert len(result["errors"]) > 0

    def test_get_action(self):
        builder = ActionBuilder()
        action = CustomAction(
            id="act_get_test",
            name="Get Test",
            steps=[ActionStep("delay", {"duration_ms": "1000"})],
        )
        builder.create(action)
        retrieved = builder.get("act_get_test")
        assert retrieved is not None
        assert retrieved.name == "Get Test"

    def test_update_action(self):
        builder = ActionBuilder()
        action = CustomAction(
            id="act_update",
            name="Old Name",
            steps=[ActionStep("click", {"selector": "#a"})],
        )
        builder.create(action)
        updated = builder.update("act_update", {"name": "New Name"})
        assert updated.name == "New Name"
        assert updated.updated_at != ""

    def test_delete_action(self):
        builder = ActionBuilder()
        action = CustomAction(
            id="act_delete",
            name="Deletable",
            steps=[ActionStep("click", {"selector": "#a"})],
        )
        builder.create(action)
        assert builder.delete("act_delete") is True
        assert builder.get("act_delete") is None

    def test_cannot_delete_template(self):
        builder = ActionBuilder()
        assert builder.delete("tmpl_login") is False

    def test_step_types_catalog(self):
        builder = ActionBuilder()
        types = builder.get_step_types()
        assert "navigate" in types
        assert "click" in types
        assert "fill" in types
        assert "extract" in types
        assert "condition" in types
        assert "loop" in types
        assert len(types) == len(STEP_TYPES)

    def test_list_actions_with_creator_filter(self):
        builder = ActionBuilder()
        action = CustomAction(
            id="act_user1",
            name="User Action",
            creator_id="user_123",
            steps=[ActionStep("click", {"selector": "#a"})],
        )
        builder.create(action)
        # User actions + templates
        user_list = builder.list_actions(creator_id="user_123")
        assert any(a["id"] == "act_user1" for a in user_list)
        # Templates always visible
        assert any(a["is_template"] for a in user_list)
