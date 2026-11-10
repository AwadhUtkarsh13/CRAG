"""Ask a question and stream the answer back."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from server.chat_service import answer_events
from server.db import Conversation, Message, User, get_db, session_factory, utcnow
from server.routes.conversations import owned_conversation
from server.schemas import ChatIn
from server.security import verified_user
from src.llm import MissingAPIKeyError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


def _title(question: str) -> str:
    title = " ".join(question.split())
    return title if len(title) <= 60 else title[:57].rstrip() + "..."


@router.post("/chat")
def chat(body: ChatIn, user: User = Depends(verified_user), db: Session = Depends(get_db)) -> StreamingResponse:
    if body.conversation_id:
        conv = owned_conversation(db, user, body.conversation_id)
    else:
        conv = Conversation(user_id=user.id, title=_title(body.question))
        db.add(conv)
        db.flush()
    history = [(m.role, m.content) for m in conv.messages]
    db.add(Message(conversation_id=conv.id, role="user", content=body.question))
    conv.updated_at = utcnow()
    db.commit()
    conversation = {"type": "conversation", "id": conv.id, "title": conv.title}
    owner = user.id

    def stream() -> Iterator[str]:
        yield json.dumps(conversation) + "\n"
        try:
            for event in answer_events(body.question, owner, history):
                if event["type"] == "done":
                    with session_factory()() as s:
                        msg = Message(
                            conversation_id=conversation["id"],
                            role="assistant",
                            content=event["answer"],
                            sources_json=json.dumps(event["sources"]),
                            verified=event["verified"],
                        )
                        s.add(msg)
                        stored = s.get(Conversation, conversation["id"])
                        if stored:
                            stored.updated_at = utcnow()
                        s.commit()
                        event["message_id"] = msg.id
                yield json.dumps(event) + "\n"
        except MissingAPIKeyError:
            logger.error("Chat requested but no OpenAI key is configured")
            yield (
                json.dumps(
                    {"type": "error", "message": "The assistant isn't set up yet: an OpenAI API key is missing."}
                )
                + "\n"
            )
        except Exception:
            logger.exception("Answering failed")
            yield (
                json.dumps({"type": "error", "message": "Something went wrong while answering. Please try again."})
                + "\n"
            )

    return StreamingResponse(
        stream(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
    )
