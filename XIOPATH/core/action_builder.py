"""
XIOPATH — Custom Action Builder (Phase E.2)
==============================================
Allows users to define custom workflow actions from composable steps.
Actions are stored as JSON recipes and can be executed as plugins.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Action Step Types
# ═══════════════════════════════════════════════════════════════════════════

STEP_TYPES = {
    "navigate":     {"label": "Navigate to URL",      "params": ["url"]},
    "click":        {"label": "Click Element",         "params": ["selector"]},
    "fill":         {"label": "Fill Input",            "params": ["selector", "value"]},
    "wait":         {"label": "Wait for Element",      "params": ["selector", "timeout_ms"]},
    "screenshot":   {"label": "Take Screenshot",       "params": ["filename"]},
    "extract":      {"label": "Extract Text",          "params": ["selector", "output_var"]},
    "condition":    {"label": "If/Else Condition",     "params": ["selector", "exists_action", "missing_action"]},
    "loop":         {"label": "Repeat N Times",        "params": ["count", "steps"]},
    "delay":        {"label": "Wait (ms)",             "params": ["duration_ms"]},
    "vault_resolve":{"label": "Resolve Vault Secret",  "params": ["vault_key", "output_var"]},
    "sub_workflow":  {"label": "Run Sub-Workflow",     "params": ["intent"]},
    "assert":       {"label": "Assert Element",        "params": ["selector", "expected_text"]},
}


@dataclass
class ActionStep:
    """A single step within a custom action."""
    step_type: str        # One of STEP_TYPES keys
    params: Dict = field(default_factory=dict)
    label: str = ""
    on_error: str = "fail"  # "fail" | "skip" | "retry"

    def validate(self) -> List[str]:
        errors = []
        if self.step_type not in STEP_TYPES:
            errors.append(f"Unknown step type: {self.step_type}")
        else:
            required = STEP_TYPES[self.step_type]["params"]
            for p in required:
                if p not in self.params and p not in ("output_var", "timeout_ms", "filename",
                                                       "exists_action", "missing_action", "steps"):
                    errors.append(f"Step '{self.step_type}' missing required param: {p}")
        return errors

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> 'ActionStep':
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class CustomAction:
    """A user-defined composite action (recipe)."""
    id: str
    name: str
    description: str = ""
    creator_id: str = ""
    steps: List[ActionStep] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = ""
    version: str = "1.0.0"
    is_template: bool = False  # If true, appears in template gallery

    def validate(self) -> List[str]:
        errors = []
        if not self.name:
            errors.append("Action name is required")
        if not self.steps:
            errors.append("At least one step is required")
        for i, step in enumerate(self.steps):
            step_errors = step.validate()
            for err in step_errors:
                errors.append(f"Step {i+1}: {err}")
        return errors

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "creator_id": self.creator_id,
            "steps": [s.to_dict() for s in self.steps],
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "is_template": self.is_template,
            "step_count": len(self.steps),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> 'CustomAction':
        steps = [ActionStep.from_dict(s) for s in d.get("steps", [])]
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            creator_id=d.get("creator_id", ""),
            steps=steps,
            tags=d.get("tags", []),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            version=d.get("version", "1.0.0"),
            is_template=d.get("is_template", False),
        )


class ActionBuilder:
    """
    Manages custom action CRUD and provides built-in templates.
    Actions are stored in-memory (backed by DB in production).
    """

    # Built-in templates
    TEMPLATES = [
        CustomAction(
            id="tmpl_login",
            name="Login Flow",
            description="Navigate, fill email + password, click submit",
            is_template=True,
            tags=["auth", "login"],
            steps=[
                ActionStep("navigate",  {"url": "{{login_url}}"},       label="Go to login page"),
                ActionStep("fill",      {"selector": "#email", "value": "vault://login_email"}, label="Enter email"),
                ActionStep("fill",      {"selector": "#password", "value": "vault://login_password"}, label="Enter password"),
                ActionStep("click",     {"selector": "button[type=submit]"}, label="Click login"),
                ActionStep("wait",      {"selector": ".dashboard", "timeout_ms": "5000"}, label="Wait for dashboard"),
            ],
        ),
        CustomAction(
            id="tmpl_scrape",
            name="Page Scraper",
            description="Navigate to URL and extract text from selector",
            is_template=True,
            tags=["scraping", "data"],
            steps=[
                ActionStep("navigate",  {"url": "{{target_url}}"},     label="Go to page"),
                ActionStep("wait",      {"selector": "{{selector}}", "timeout_ms": "3000"}, label="Wait for content"),
                ActionStep("extract",   {"selector": "{{selector}}", "output_var": "scraped_text"}, label="Extract text"),
            ],
        ),
        CustomAction(
            id="tmpl_form_fill",
            name="Form Filler",
            description="Fill a multi-field form and submit",
            is_template=True,
            tags=["form", "automation"],
            steps=[
                ActionStep("navigate",  {"url": "{{form_url}}"},        label="Go to form"),
                ActionStep("fill",      {"selector": "#name", "value": "{{name}}"}, label="Fill name"),
                ActionStep("fill",      {"selector": "#email", "value": "vault://email"}, label="Fill email"),
                ActionStep("fill",      {"selector": "#message", "value": "{{message}}"}, label="Fill message"),
                ActionStep("click",     {"selector": "button[type=submit]"}, label="Submit"),
                ActionStep("wait",      {"selector": ".success", "timeout_ms": "3000"}, label="Wait for confirmation"),
            ],
        ),
    ]

    def __init__(self):
        self._actions: Dict[str, CustomAction] = {}
        # Pre-load templates
        for t in self.TEMPLATES:
            self._actions[t.id] = t

    def create(self, action: CustomAction) -> Dict:
        errors = action.validate()
        if errors:
            return {"success": False, "errors": errors}
        self._actions[action.id] = action
        logger.info(f"Created custom action: {action.name} ({action.id})")
        return {"success": True, "action": action.to_dict()}

    def get(self, action_id: str) -> Optional[CustomAction]:
        return self._actions.get(action_id)

    def update(self, action_id: str, updates: Dict) -> Optional[CustomAction]:
        action = self._actions.get(action_id)
        if not action:
            return None
        if "name" in updates:
            action.name = updates["name"]
        if "description" in updates:
            action.description = updates["description"]
        if "steps" in updates:
            action.steps = [ActionStep.from_dict(s) for s in updates["steps"]]
        if "tags" in updates:
            action.tags = updates["tags"]
        action.updated_at = datetime.now(timezone.utc).isoformat()
        return action

    def delete(self, action_id: str) -> bool:
        if action_id in self._actions and not self._actions[action_id].is_template:
            del self._actions[action_id]
            return True
        return False

    def list_actions(self, templates_only: bool = False, creator_id: str = None) -> List[Dict]:
        results = []
        for a in self._actions.values():
            if templates_only and not a.is_template:
                continue
            if creator_id and a.creator_id != creator_id and not a.is_template:
                continue
            results.append(a.to_dict())
        return results

    def get_templates(self) -> List[Dict]:
        return self.list_actions(templates_only=True)

    def get_step_types(self) -> Dict:
        return STEP_TYPES
