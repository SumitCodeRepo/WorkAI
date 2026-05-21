"""
chat/schemas.py
---------------
PURPOSE:
    Pydantic models for the chat API request and response shapes.

CONCEPT — Why streaming needs a different response model
    For regular endpoints, FastAPI serialises the return value to JSON.
    For streaming endpoints, we return a FastAPI StreamingResponse instead,
    which bypasses Pydantic serialisation. So we only need a Pydantic schema
    for the REQUEST body, not the response.

    The response is a stream of plain text tokens (or SSE-formatted lines).

SCHEMAS:
    QueryRequest     — body for POST /chat/query (direct department chat)
    MessageRequest   — body for POST /chat/message (primary; router picks dept)
    SessionResponse  — returned when a new session is created
    MessageResponse  — returned when listing chat history
"""

from pydantic import BaseModel
from typing import Optional
from db.models import Department


class QueryRequest(BaseModel):
    """
    Body for POST /chat/query.

    Fields:
        department  — which agent to route to (hr, it, finance, legal, admin)
        message     — the user's question or message
        session_id  — optional existing session ID for conversation continuity;
                      if omitted, a new session is created automatically
    """
    department: Department
    message: str
    session_id: Optional[int] = None


class MessageRequest(BaseModel):
    """
    Body for POST /chat/message — the primary endpoint used by the mobile app.

    Unlike QueryRequest, no department is required. The RouterAgent classifies
    the message and picks the department automatically.

    Fields:
        message     — the user's question or message
        session_id  — optional session ID for conversation continuity;
                      the router uses history to understand follow-up questions
    """
    message: str
    session_id: Optional[int] = None


class SessionResponse(BaseModel):
    """Returned with each streaming response to tell the client its session ID."""
    session_id: int
    department: str

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    """One message in chat history."""
    id: int
    role: str
    content: str
    created_at: str

    model_config = {"from_attributes": True}
