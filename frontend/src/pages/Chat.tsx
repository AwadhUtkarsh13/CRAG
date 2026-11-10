import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate, useParams } from "react-router";
import { firstName, useAuth } from "../auth";
import AnswerText, { stripCitations } from "../components/AnswerText";
import { useChatSession, type UiMessage } from "../components/ChatSession";
import { useLibrary } from "../components/Library";
import { Button, Dots, Skeleton, Spinner, useToast } from "../components/ui";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function Message({ message, onRetry }: { message: UiMessage; onRetry: (q: string) => void }) {
  const notify = useToast();
  const [flash, setFlash] = useState<number | null>(null);
  const sourcesRef = useRef<HTMLDivElement>(null);

  if (message.role === "user") {
    return (
      <div className="msg msg-user">
        <div className="bubble-user">{message.content}</div>
      </div>
    );
  }

  const showSource = (n: number) => {
    const el = sourcesRef.current?.querySelector<HTMLElement>(`[data-source="${n}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    setFlash(n);
    window.setTimeout(() => setFlash(null), 1400);
  };

  const thinking = message.pending && !message.content;
  return (
    <div className="msg msg-assistant">
      <div className="who-label">CRAG</div>
      {thinking ? (
        <div className="thinking">
          <Dots />
          <span className="status" key={message.status}>
            {message.status}
          </span>
        </div>
      ) : (
        <>
          {message.content && <AnswerText text={message.content} streaming={message.pending} onCite={showSource} />}
          {message.pending && message.status && (
            <div className="thinking" style={{ marginTop: 10 }}>
              <Dots />
              <span className="status muted" key={message.status}>
                {message.status}
              </span>
            </div>
          )}
        </>
      )}

      {message.error && (
        <div className="msg-error" style={{ marginTop: message.content ? 12 : 0 }}>
          <span>{message.error}</span>
          {message.question && (
            <Button size="sm" variant="secondary" onClick={() => onRetry(message.question!)}>
              Try again
            </Button>
          )}
        </div>
      )}
      {message.stopped && <p className="muted" style={{ marginTop: 8, fontSize: 14 }}>Stopped.</p>}

      {!message.pending && !message.error && message.content && (
        <>
          {message.sources.length > 0 && (
            <div className="sources" ref={sourcesRef}>
              <div className="sources-title">Sources</div>
              {message.sources.map((s) => (
                <div key={s.number} data-source={s.number} className={`source${flash === s.number ? " flash" : ""}`}>
                  <span className="num">{s.number}</span>
                  <div className="body">
                    <div>
                      {s.url ? (
                        <a className="title" href={s.url} target="_blank" rel="noopener noreferrer">
                          {s.title}
                        </a>
                      ) : (
                        <span className="title">{s.title}</span>
                      )}
                      <span className="kind">{s.kind === "web" ? "Web" : "Your document"}</span>
                    </div>
                    {s.excerpt && <div className="excerpt">{s.excerpt}</div>}
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="meta-row">
            {message.verified === true && <span className="check ok">Checked against the sources</span>}
            {message.verified === false && (
              <span className="check warn">Not fully confirmed. Please review the sources.</span>
            )}
            <button
              className="link-btn"
              onClick={() =>
                navigator.clipboard
                  .writeText(stripCitations(message.content))
                  .then(() => notify("Answer copied", "success"))
                  .catch(() => notify("Couldn't copy the answer", "error"))
              }
            >
              Copy answer
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function Welcome({ onAsk }: { onAsk: (q: string) => void }) {
  const { user } = useAuth();
  const { documents } = useLibrary();
  const navigate = useNavigate();

  const suggestions = (documents ?? []).slice(0, 2).flatMap((d) => [
    { topic: d.filename, q: `Summarize the key points of ${d.filename}` },
    { topic: d.filename, q: `What are the most important dates or deadlines in ${d.filename}?` },
  ]);

  return (
    <div className="welcome">
      <h1>
        {greeting()}, {user ? firstName(user) : ""}
      </h1>
      <p className="lead">
        Ask anything about your documents. You'll get a direct answer, with the sources it came from.
      </p>
      {documents === null ? (
        <div className="suggestions">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} height={72} style={{ borderRadius: 14 }} />
          ))}
        </div>
      ) : documents.length === 0 ? (
        <div className="card empty-library">
          <h2>Start by adding your documents</h2>
          <p className="muted">Upload PDF, TXT or Markdown files, then ask anything about them.</p>
          <div className="welcome-actions">
            <Button onClick={() => navigate("/documents")}>Upload documents</Button>
          </div>
        </div>
      ) : (
        <div className="suggestions">
          {suggestions.map((s) => (
            <button key={s.q} className="suggestion" onClick={() => onAsk(s.q)}>
              <small>{s.topic}</small>
              {s.q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ChatPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { messages, loading, loadError, streaming, open, send, stop, activeId } = useChatSession();
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const stickToBottom = useRef(true);

  useEffect(() => {
    open(id ?? null);
  }, [id, open]);

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  useLayoutEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [draft]);

  function ask(question: string) {
    const q = question.trim();
    if (!q || streaming) return;
    stickToBottom.current = true;
    setDraft("");
    send(q, (newId) => navigate(`/c/${newId}`, { replace: !id }));
    inputRef.current?.focus();
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      ask(draft);
    }
  }

  const showWelcome = !id && !activeId && messages.length === 0;
  return (
    <div className="chat">
      <div
        className="chat-scroll"
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
      >
        <div className="chat-inner">
          {showWelcome ? (
            <Welcome onAsk={ask} />
          ) : loading ? (
            <div style={{ display: "grid", gap: 18, paddingTop: 12 }}>
              <Skeleton width="45%" height={40} style={{ marginLeft: "auto", borderRadius: 18 }} />
              <Skeleton width="90%" height={18} />
              <Skeleton width="75%" height={18} />
              <Skeleton width="60%" height={18} />
            </div>
          ) : loadError ? (
            <div className="banner banner-error">{loadError}</div>
          ) : (
            messages.map((m) => <Message key={m.id} message={m} onRetry={ask} />)
          )}
        </div>
      </div>
      <div className="composer-wrap">
        <div className="composer">
          <label htmlFor="question" className="sr-only">
            Your question
          </label>
          <textarea
            id="question"
            ref={inputRef}
            rows={1}
            value={draft}
            autoFocus
            placeholder="Ask a question about your documents"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            maxLength={2000}
          />
          {streaming ? (
            <Button variant="secondary" onClick={stop}>
              <Spinner /> Stop
            </Button>
          ) : (
            <Button onClick={() => ask(draft)} disabled={!draft.trim()}>
              Ask
            </Button>
          )}
        </div>
        <p className="composer-note">Answers are checked against your sources. Press Enter to send, Shift + Enter for a new line.</p>
      </div>
    </div>
  );
}
