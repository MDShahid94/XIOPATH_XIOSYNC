from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

class PromotionRequest(BaseModel):
    domain: str
    node_id: str
    client_id: str
    action_data: Dict[str, Any]

class ExecutionRequest(BaseModel):
    session_id: str
    url: str
    start_intent: str
    context_dict: Dict[str, Any] = Field(default_factory=dict)

class RecordActionRequest(BaseModel):
    url: str
    intent: str
    face_value: Dict[str, Any]
    place_value: Dict[str, Any]
    action_type: str
    action_params: Dict[str, Any]
    context: Dict[str, Any] = Field(default_factory=dict)
    context_hash: Optional[str] = None
    previous_node_id: Optional[str] = None
    execution_mode: str = "sequential"
    condition: str = "default"

class InferenceRequest(BaseModel):
    intent: str
    dom: str
    worker_type: Optional[str] = None


class DeployRequest(BaseModel):
    graph_name: str
    profile_mail_id: Optional[str] = None


class WorkerTokenRequest(BaseModel):
    worker_secret: str
