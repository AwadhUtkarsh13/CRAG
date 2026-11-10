import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, type ConversationItem, type DocumentItem } from "../api";

interface LibraryState {
  conversations: ConversationItem[] | null;
  documents: DocumentItem[] | null;
  refreshConversations: () => Promise<void>;
  refreshDocuments: () => Promise<void>;
  touchConversation: (item: ConversationItem) => void;
  removeConversation: (id: string) => void;
  setDocuments: (docs: DocumentItem[]) => void;
}

const LibraryContext = createContext<LibraryState | null>(null);

export function LibraryProvider({ children }: { children: ReactNode }) {
  const [conversations, setConversations] = useState<ConversationItem[] | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[] | null>(null);

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await api.listConversations());
    } catch {
      setConversations((c) => c ?? []);
    }
  }, []);

  const refreshDocuments = useCallback(async () => {
    try {
      setDocuments(await api.listDocuments());
    } catch {
      setDocuments((d) => d ?? []);
    }
  }, []);

  useEffect(() => {
    void refreshConversations();
    void refreshDocuments();
  }, [refreshConversations, refreshDocuments]);

  const touchConversation = useCallback((item: ConversationItem) => {
    setConversations((list) => [item, ...(list ?? []).filter((c) => c.id !== item.id)]);
  }, []);

  const removeConversation = useCallback((id: string) => {
    setConversations((list) => (list ?? []).filter((c) => c.id !== id));
  }, []);

  const value = useMemo(
    () => ({
      conversations,
      documents,
      refreshConversations,
      refreshDocuments,
      touchConversation,
      removeConversation,
      setDocuments,
    }),
    [conversations, documents, refreshConversations, refreshDocuments, touchConversation, removeConversation],
  );
  return <LibraryContext.Provider value={value}>{children}</LibraryContext.Provider>;
}

export function useLibrary(): LibraryState {
  const ctx = useContext(LibraryContext);
  if (!ctx) throw new Error("useLibrary must be used inside LibraryProvider");
  return ctx;
}
