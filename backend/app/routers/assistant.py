from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import assistant, models, ollama, schemas
from ..database import get_db
from ..security import get_current_user

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.get("/status", response_model=schemas.AssistantStatus)
def status(user: models.User = Depends(get_current_user)):
    """Is Ollama running, and is the model downloaded? The chat screen shows setup help when not."""
    return ollama.status()


@router.post("/chat")
def chat(data: schemas.ChatRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Answers the last message. Streams newline-delimited JSON events (see assistant.chat)."""
    if data.messages[-1].role != "user":
        raise HTTPException(400, "The last message must be from the user")
    history = [m.model_dump() for m in data.messages]
    return StreamingResponse(assistant.chat(db, user, history), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
