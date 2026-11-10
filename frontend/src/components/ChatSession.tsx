import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
  selectedDocs: string[];
  webSearch: boolean;
  setSelectedDocs: (ids: string[]) => void;
  setWebSearch: (on: boolean) => void;
  open: (id: string | null) => void;
  send: (question: string, options?: { webSearch?: boolean; onCreated?: (id: string) => void }) => void;
  stop: () => void;
}

const ChatContext = createContext<ChatSessionState | null>(null);
let tempCounter = 0;
const tempId = () => `tmp-${++tempCounter}`;

export function ChatProvider({ children }: { children: ReactNode }) {
  const { conversations, documents, touchConversation } = useLibrary();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [webSearch, setWebSearch] = useState(false);
  const activeRef = useRef<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const loadSeq = useRef(0);
  const settingsFor = useRef<string | null>(null);

  // Restore a saved chat's document selection and web search setting once its details are known.
  useEffect(() => {
    if (!activeId || settingsFor.current === activeId || !conversations) return;
    const conv = conversations.find((c) => c.id === activeId);
    if (!conv) return;
    settingsFor.current = activeId;
    setSelectedDocs(conv.document_ids);
    setWebSearch(conv.web_search);
  }, [activeId, conversations]);

  // Drop documents that were removed from the library.
  useEffect(() => {
    if (!documents) return;
    const existing = new Set(documents.map((d) => d.id));
    setSelectedDocs((ids) => (ids.every((id) => existing.has(id)) ? ids : ids.filter((id) => existing.has(id))));
  }, [documents]);

  const open = useCallback((id: string | null) => {
    if (id === activeRef.current && (id !== null || loadSeq.current > 0)) return;
    activeRef.current = id;
    setActiveId(id);
    setLoadError(null);
    const seq = ++loadSeq.current;
    if (id === null) {
      settingsFor.current = null;
      setSelectedDocs([]);
      setWebSearch(false);
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

  const selectedRef = useRef(selectedDocs);
  selectedRef.current = selectedDocs;
  const webRef = useRef(webSearch);
  webRef.current = webSearch;

  const send = useCallback(
    (question: string, options: { webSearch?: boolean; onCreated?: (id: string) => void } = {}) => {
      if (controllerRef.current) return;
      const documentIds = selectedRef.current;
      const web = options.webSearch ?? webRef.current;
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
          status: web ? "Reading your documents" : "Reading the selected documents",
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
              settingsFor.current = event.id;
              setActiveId(event.id);
              options.onCreated?.(event.id);
            }
            touchConversation({
              id: event.id,
              title: event.title,
              document_ids: event.document_ids,
              web_search: event.web_search,
              updated_at: new Date().toISOString(),
            });
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
                  outcome: event.outcome,
                  created_at: new Date().toISOString(),
                  question,
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

      streamChat(
        { question, conversation_id: convId, document_ids: documentIds, web_search: web },
        onEvent,
        controller.signal,
      )
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
    () => ({
      activeId,
      messages,
      loading,
      loadError,
      streaming,
      selectedDocs,
      webSearch,
      setSelectedDocs,
      setWebSearch,
      open,
      send,
      stop,
    }),
    [activeId, messages, loading, loadError, streaming, selectedDocs, webSearch, open, send, stop],
  );
  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChatSession(): ChatSessionState {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChatSession must be used inside ChatProvider");
  return ctx;
}
