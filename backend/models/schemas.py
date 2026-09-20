from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
    tool = "tool"


class ChatMessage(BaseModel):
    role: MessageRole
    content: Optional[str] = ""
    tool_calls: Optional[list[dict]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = Field(default_factory=list)
    stream: bool = True


class SSEEventType(str, Enum):
    thinking = "thinking"
    token = "token"
    tool_call_start = "tool_call_start"
    tool_call_result = "tool_call_result"
    done = "done"
    error = "error"


class SSEEvent(BaseModel):
    type: SSEEventType
    data: dict | str