import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate, useParams } from "react-router";
import { api } from "../api";
import { firstName, useAuth } from "../auth";
import AnswerText, { stripCitations } from "../components/AnswerText";
import { DocumentChecklist, DocumentPicker, WebToggle } from "../components/ChatControls";
import { useChatSession, type UiMessage } from "../components/ChatSession";
import { useLibrary } from "../components/Library";
import { Button, Dots, Skeleton, Spinner, useToast } from "../components/ui";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function Message({
  message,
  question,
  webOn,
  webAvailable,
  onRetry,
  onSearchWeb,
}: {
  message: UiMessage;
  question?: string;
  webOn: boolean;
  webAvailable: boolean;
  onRetry: (q: string) => void;
  onSearchWeb: (q: string) => void;
}) {
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
  const notFound = message.outcome === "not_found";
  const plainReply = message.outcome === "chat";
  const finished = !message.pending && !message.error && message.content;
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
          {(message.question ?? question) && (
            <Button size="sm" variant="secondary" onClick={() => onRetry((message.question ?? question)!)}>
              Try again
            </Button>
          )}
        </div>
      )}
      {message.stopped && <p className="muted" style={{ marginTop: 8, fontSize: 14 }}>Stopped.</p>}

      {finished && notFound && !webOn && (
        <div className="not-found">
          {webAvailable ? (
            <>
              <p>Want me to look beyond your documents?</p>
              <Button size="sm" onClick={() => (message.question ?? question) && onSearchWeb((message.question ?? question)!)}>
                Search the web for this
              </Button>
            </>
          ) : (
            <p className="muted">Try selecting another document, or rephrase the question.</p>
          )}
        </div>
      )}

      {finished && !plainReply && !notFound && (
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
            {message.verified === true && message.sources.length > 0 && (
              <span className="check ok">Checked against the sources</span>
            )}
            {message.verified !== true && (
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
  const { selectedDocs, setSelectedDocs } = useChatSession();
  const navigate = useNavigate();

  const chosen = (documents ?? []).filter((d) => selectedDocs.includes(d.id));
  const suggestions = chosen.slice(0, 2).flatMap((d) => [
    { topic: d.filename, q: `Summarize the key points of ${d.filename}` },
    { topic: d.filename, q: `What are the most important dates or details in ${d.filename}?` },
  ]);

  return (
    <div className="welcome">
      <h1>
        {greeting()}, {user ? firstName(user) : ""}
      </h1>
      <p className="lead">
        Choose the documents for this chat, then ask anything. You'll get a direct answer with the sources it came
        from.
      </p>
      {documents === null ? (
        <div className="suggestions">
          {[0, 1].map((i) => (
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
        <>
          <div className="card choose-docs">
            <h2>Documents for this chat</h2>
            <p className="muted">Answers will come only from the documents you select here.</p>
            <DocumentChecklist documents={documents} selected={selectedDocs} onChange={setSelectedDocs} />
          </div>
          {suggestions.length > 0 && (
            <div className="suggestions">
              {suggestions.map((s) => (
                <button key={s.q} className="suggestion" onClick={() => onAsk(s.q)}>
                  <small>{s.topic}</small>
                  {s.q}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function ChatPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { documents } = useLibrary();
  const notify = useToast();
  const {
    messages,
    loading,
    loadError,
    streaming,
    open,
    send,
    stop,
    activeId,
    selectedDocs,
    setSelectedDocs,
    webSearch,
    setWebSearch,
  } = useChatSession();
  const [draft, setDraft] = useState("");
  const [webAvailable, setWebAvailable] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const stickToBottom = useRef(true);

  useEffect(() => {
    open(id ?? null);
  }, [id, open]);

  useEffect(() => {
    api
      .health()
      .then((h) => setWebAvailable(h.web_search))
      .catch(() => setWebAvailable(false));
  }, []);

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

  const hasDocs = selectedDocs.length > 0;

  function ask(question: string, options: { webSearch?: boolean } = {}) {
    const q = question.trim();
    if (!q || streaming) return;
    if (!hasDocs) {
      notify("Choose at least one document first", "error");
      return;
    }
    stickToBottom.current = true;
    setDraft("");
    send(q, { ...options, onCreated: (newId) => navigate(`/c/${newId}`, { replace: !id }) });
    inputRef.current?.focus();
  }

  function searchWeb(question: string) {
    setWebSearch(true);
    ask(question, { webSearch: true });
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      ask(draft);
    }
  }

  const showWelcome = !id && !activeId && messages.length === 0;
  const library = documents ?? [];
  return (
    <div className="chat">
      {!showWelcome && (
        <div className="chat-toolbar">
          <DocumentPicker documents={library} selected={selectedDocs} onChange={setSelectedDocs} disabled={streaming} />
          <WebToggle on={webSearch} onChange={setWebSearch} available={webAvailable} disabled={streaming} />
        </div>
      )}
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
            <Welcome onAsk={(q) => ask(q)} />
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
            messages.map((m, i) => (
              <Message
                key={m.id}
                message={m}
                question={i > 0 && messages[i - 1]!.role === "user" ? messages[i - 1]!.content : undefined}
                webOn={webSearch}
                webAvailable={webAvailable}
                onRetry={(q) => ask(q)}
                onSearchWeb={searchWeb}
              />
            ))
          )}
        </div>
      </div>
      <div className="composer-wrap">
        {showWelcome && library.length > 0 && (
          <div className="composer-options">
            <WebToggle on={webSearch} onChange={setWebSearch} available={webAvailable} disabled={streaming} />
          </div>
        )}
        <div className={`composer${hasDocs ? "" : " locked"}`}>
          <label htmlFor="question" className="sr-only">
            Your question
          </label>
          <textarea
            id="question"
            ref={inputRef}
            rows={1}
            value={draft}
            autoFocus
            placeholder={hasDocs ? "Ask a question about the selected documents" : "Choose at least one document to start"}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            maxLength={2000}
          />
          {streaming ? (
            <Button variant="secondary" onClick={stop}>
              <Spinner /> Stop
            </Button>
          ) : (
            <Button onClick={() => ask(draft)} disabled={!draft.trim() || !hasDocs}>
              Ask
            </Button>
          )}
        </div>
        <p className="composer-note">
          {webSearch && webAvailable
            ? "Web search is on: your documents come first, the web fills any gaps."
            : "Answers come only from the selected documents."}{" "}
          Press Enter to send, Shift + Enter for a new line.
        </p>
      </div>
    </div>
  );
}
