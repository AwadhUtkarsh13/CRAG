"""Prompt templates used by the graph nodes."""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

DOCUMENT_CONVENTIONS = (
    "How to read the documents: a resume, CV, biography or profile describes its owner, so "
    "entries listed without a subject (for example 'Was the Quarter Finalist in Badminton "
    "Men's Singles' or 'Led a team of five') are that person's own achievements and "
    "activities. Likewise, a company policy or report speaks for that company."
)

GRADE_DOCUMENT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a relevance grader for a retrieval system. Decide whether the retrieved "
            "chunk contains information that helps answer the user's question. Keyword overlap "
            "alone is not enough: the chunk must contain facts that are useful for an answer.\n"
            f"{DOCUMENT_CONVENTIONS}\n"
            "A chunk that contradicts or disproves an assumption in the question (a false "
            "premise) IS relevant, because it is needed to correct the user. Example: question "
            "'Why did the company cancel its gym benefit?' with a chunk stating 'employees "
            "receive a USD 50 monthly gym benefit' -> 'yes'.\n"
            "If the question challenges an earlier answer (for example 'how can you say he "
            "didn't...?'), judge the chunk against the underlying factual question.\n"
            "A chunk is relevant if it lets you answer the question in any direction: yes, no, "
            "partly, or by correcting it (e.g. 'got a special mention in the quiz' answers 'did "
            "he win the quiz?' with 'no, a special mention').\n"
            "Use the line 'This document begins: ...' to know whose document the chunk is from.\n"
            "Explain briefly, then give binary_score 'yes' or 'no'.",
        ),
        ("human", "Question:\n{question}\n\nRetrieved chunk:\n{document}"),
    ]
)

REWRITE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You rewrite a user question into one self-contained web search query. Keep every "
            "person, organization and product name exactly as written (full names, no "
            "shortening). Expand acronyms, add the key constraints, and remove conversational "
            "filler. Today's date is {today}: replace relative time references such as 'this "
            "year', 'current' or 'latest' with the explicit year. Only add a year when the "
            "question is about something time-dependent. Return ONLY the query text.",
        ),
        ("human", "Question: {question}{notes}"),
    ]
)

GENERATE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a helpful assistant that answers questions about the user's documents "
            "using ONLY the numbered context below.\n"
            "Rules:\n"
            "1. Answer directly in clear, natural language, in your own words rather than "
            "copying lines. Start with the answer itself (for example 'Yes, ...').\n"
            "2. End every factual sentence with citation markers like [1] or [2][3].\n"
            f"3. {DOCUMENT_CONVENTIONS} State such direct conclusions confidently and cite them.\n"
            "4. Never use outside knowledge and never invent names, numbers or dates. Use each "
            "person's or organization's name exactly as it appears in the context.\n"
            "5. Context items marked 'Source (web)' may be about a different person or "
            "organization with a similar name. Use a web item only if it clearly refers to the "
            "same subject as the question and the user's documents; never combine facts about "
            "different people or organizations. When documents and web disagree, prefer the "
            "documents.\n"
            "6. If the context does not contain the answer, say so plainly (for example 'The "
            "selected documents don't mention ...') instead of guessing.\n"
            "7. If the question contains a false premise, correct it using the context.\n"
            "8. Today's date is {today}. For time-sensitive figures, state the year they apply "
            "to and prefer the most recent.\n"
            "9. Be concise: a short paragraph or a few bullets.{feedback}\n\n"
            "Context:\n{context}",
        ),
        ("human", "{question}"),
    ]
)

GROUNDEDNESS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You verify whether an AI answer is grounded in the supplied context. Answer 'yes' "
            "only if every factual claim in the answer is supported by the context.\n"
            f"{DOCUMENT_CONVENTIONS} Conclusions that follow directly from these conventions "
            "count as supported.\n"
            "Answer 'no' if the answer: states facts the context doesn't contain (even if true "
            "in general); uses a name that appears nowhere in the context (the 'This document "
            "begins' lines are part of the context and show whose document it is); or attributes facts "
            "from a source about one person or organization to a different one (for example a "
            "web page about someone with a similar name). Saying the context lacks information "
            "counts as grounded. Explain briefly, then give binary_score 'yes' or 'no'.",
        ),
        ("human", "Context:\n{context}\n\nAnswer:\n{generation}"),
    ]
)

ANSWER_RELEVANCE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You judge whether an answer resolves the user's question. Answer 'yes' if it "
            "directly addresses what was asked (correctly rejecting a false premise counts). "
            "Answer 'no' if it is off-topic or only says the information is unavailable. "
            "Explain briefly, then give binary_score 'yes' or 'no'.",
        ),
        ("human", "Question:\n{question}\n\nAnswer:\n{generation}"),
    ]
)

CONDENSE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Rewrite the user's latest message as one standalone question that can be "
            "understood without the conversation.\n"
            "- Resolve pronouns and references ('he', 'it', 'that', 'what about Tokyo?') using "
            "the conversation.\n"
            "- Keep names exactly and completely as they appear in the conversation or the "
            "document list (full name, never shortened or changed). Never add a surname or any "
            "detail that doesn't appear there; if only a first name is known, use only that.\n"
            "- If the user disputes or questions an earlier answer (for example 'then how can "
            "you say he didn't play?'), rewrite it as the underlying factual question and "
            "include the detail they point to, e.g. 'Did Asha Rao play badminton, given that "
            "the resume lists her as a quarter-finalist in badminton?'.\n"
            "- If the message is already standalone, return it unchanged.\n"
            "Return ONLY the question.",
        ),
        (
            "human",
            "Documents in this chat:\n{documents}\n\nConversation so far:\n{history}\n\nLatest message: {question}",
        ),
    ]
)
