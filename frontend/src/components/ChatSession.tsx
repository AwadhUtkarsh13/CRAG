import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { api, ApiError, streamChat, type ChatEvent, type ChatMessage } from "../api";
import { useLibrary } from "./Library";

export interface UiMessage extends ChatMessage {
  pending?: boolean;
  status?: string;
  error?: string;
  stopped?: boolean;
  question?: string;
}

interface ChatSessionState {
  activeId: string | null;
  messages: UiMessage[];
  loading: boolean;
  loadError: string | null;
  streaming: boolean;
  open: (id: string | null) => void;
  send: (question: string, onCreated?: (id: string) => void) => void;
  stop: () => void;
}

const ChatContext = createContext<ChatSessionState | null>(null);
let tempCounter = 0;
const tempId = () => `tmp-${++tempCounter}`;

export function ChatProvider({ children }: { children: ReactNode }) {
  const { touchConversation } = useLibrary();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const activeRef = useRef<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const loadSeq = useRef(0);

  const open = useCallback((id: string | null) => {
    if (id === activeRef.current && (id !== null || loadSeq.current > 0)) return;
    activeRef.current = id;
    setActiveId(id);
    setLoadError(null);
    const seq = ++loadSeq.current;
    if (id === null) {
      setMessages([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setMessages([]);
    api
      .messages(id)
      .then((list) => seq === loadSeq.current && setMessages(list))
      .catch((err: ApiError) => seq === loadSeq.current && setLoadError(err.message))
      .finally(() => seq === loadSeq.current && setLoading(false));
  }, []);

  const send = useCallback(
    (question: string, onCreated?: (id: string) => void) => {
      if (controllerRef.current) return;
      const placeholderId = tempId();
      let convId = activeRef.current;
      const now = new Date().toISOString();
      setMessages((list) => [
        ...list,
        { id: tempId(), role: "user", content: question, sources: [], verified: null, created_at: now },
        {
          id: placeholderId,
          role: "assistant",
          content: "",
          sources: [],
          verified: null,
          created_at: now,
          pending: true,
          status: "Reading your documents",
          question,
        },
      ]);
      const controller = new AbortController();
      controllerRef.current = controller;
      setStreaming(true);

      const patch = (fn: (m: UiMessage) => UiMessage) => {
        if (activeRef.current !== convId) return;
        setMessages((list) => list.map((m) => (m.id === placeholderId ? fn(m) : m)));
      };

      const onEvent = (event: ChatEvent) => {
        switch (event.type) {
          case "conversation":
            if (!convId) {
              convId = event.id;
              activeRef.current = event.id;
              setActiveId(event.id);
              onCreated?.(event.id);
            }
            touchConversation({ id: event.id, title: event.title, updated_at: new Date().toISOString() });
            break;
          case "status":
            patch((m) => ({ ...m, status: event.text }));
            break;
          case "token":
            patch((m) => ({ ...m, content: m.content + event.text }));
            break;
          case "reset":
            patch((m) => ({ ...m, content: "" }));
            break;
          case "done":
            if (activeRef.current === convId) {
              setMessages((list) => {
                const final: UiMessage = {
                  id: event.message_id,
                  role: "assistant",
                  content: event.answer,
                  sources: event.sources,
                  verified: event.verified,
                  created_at: new Date().toISOString(),
                };
                return list.some((m) => m.id === placeholderId)
                  ? list.map((m) => (m.id === placeholderId ? final : m))
                  : [...list, final];
              });
            }
            break;
          case "error":
            patch((m) => ({ ...m, pending: false, error: event.message }));
            break;
        }
      };

      streamChat({ question, conversation_id: convId }, onEvent, controller.signal)
        .catch((err: Error) => {
          if (err.name === "AbortError") patch((m) => ({ ...m, pending: false, stopped: true }));
          else patch((m) => ({ ...m, pending: false, error: err.message }));
        })
        .finally(() => {
          controllerRef.current = null;
          setStreaming(false);
          patch((m) => (m.pending ? { ...m, pending: false } : m));
        });
    },
    [touchConversation],
  );

  const stop = useCallback(() => controllerRef.current?.abort(), []);

  const value = useMemo(
    () => ({ activeId, messages, loading, loadError, streaming, open, send, stop }),
    [activeId, messages, loading, loadError, streaming, open, send, stop],
  );
  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChatSession(): ChatSessionState {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChatSession must be used inside ChatProvider");
  return ctx;
}
