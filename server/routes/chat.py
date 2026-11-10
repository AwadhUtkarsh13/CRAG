"""Ask a question about the selected documents and stream the answer back."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from server.chat_service import answer_events
from server.db import Conversation, DocumentRecord, Message, User, get_db, session_factory, utcnow
from server.routes.conversations import owned_conversation
from server.schemas import ChatIn
from server.security import verified_user
from src.llm import MissingAPIKeyError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


def _title(question: str) -> str:
    title = " ".join(question.split())
    return title if len(title) <= 60 else title[:57].rstrip() + "..."


def _owned_document_ids(db: Session, user: User, requested: list[str]) -> list[str]:
    """Keep only the requested documents that still exist in the user's library."""
    if not requested:
        return []
    found = {
        d.id
        for d in db.query(DocumentRecord.id).filter(
            DocumentRecord.user_id == user.id, DocumentRecord.id.in_(set(requested))
        )
    }
    return [d for d in dict.fromkeys(requested) if d in found]


def _line(event: dict) -> str:
    return json.dumps(event) + "\n"


@router.post("/chat")
def chat(body: ChatIn, user: User = Depends(verified_user), db: Session = Depends(get_db)) -> StreamingResponse:
    document_ids = _owned_document_ids(db, user, body.document_ids)
    if not document_ids:
        raise HTTPException(400, {"code": "no_documents", "message": "Select at least one document to ask about."})
    if body.conversation_id:
        conv = owned_conversation(db, user, body.conversation_id)
    else:
        conv = Conversation(user_id=user.id, title=_title(body.question))
        db.add(conv)
        db.flush()
    history = [(m.role, m.content) for m in conv.messages]
    conv.document_ids_json = json.dumps(document_ids)
    conv.web_search = body.web_search
    conv.updated_at = utcnow()
    db.add(Message(conversation_id=conv.id, role="user", content=body.question))
    db.commit()
    conversation = {
        "type": "conversation",
        "id": conv.id,
        "title": conv.title,
        "document_ids": document_ids,
        "web_search": body.web_search,
    }
    owner = user.id

    def stream() -> Iterator[str]:
        yield _line(conversation)
        try:
            for event in answer_events(body.question, owner, history, document_ids, body.web_search):
                if event["type"] == "done":
                    with session_factory()() as s:
                        msg = Message(
                            conversation_id=conversation["id"],
                            role="assistant",
                            content=event["answer"],
                            sources_json=json.dumps(event["sources"]),
                            verified=event["verified"],
                            outcome=event["outcome"],
                        )
                        s.add(msg)
                        stored = s.get(Conversation, conversation["id"])
                        if stored:
                            stored.updated_at = utcnow()
                        s.commit()
                        event["message_id"] = msg.id
                yield _line(event)
        except MissingAPIKeyError:
            logger.error("Chat requested but no OpenAI key is configured")
            yield _line({"type": "error", "message": "The assistant isn't set up yet: an OpenAI API key is missing."})
        except Exception:
            logger.exception("Answering failed")
            yield _line({"type": "error", "message": "Something went wrong while answering. Please try again."})

    return StreamingResponse(
        stream(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
    )
