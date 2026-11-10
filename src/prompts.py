"""Prompt templates used by the graph nodes."""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

GRADE_DOCUMENT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a strict relevance grader for a retrieval system. Decide whether the "
            "retrieved chunk contains information that helps answer the user's question. "
            "Keyword overlap alone is not enough: the chunk must contain facts that are "
            "actually useful for an answer.\n"
            "Important: a chunk that contradicts or disproves an assumption in the question "
            "(a false premise) IS relevant, because it is needed to correct the user.\n"
            "Example: question 'Why did the company cancel its gym benefit?' with a chunk "
            "stating 'employees receive a USD 50 monthly gym benefit' -> 'yes' (it shows the "
            "benefit still exists).\n"
            "Explain briefly, then give binary_score 'yes' or 'no'.",
        ),
        ("human", "Question:\n{question}\n\nRetrieved chunk:\n{document}"),
    ]
)

REWRITE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You rewrite user questions into a single, self-contained search query optimised "
            "for a web search engine. Expand acronyms, add the key entities and constraints, "
            "and remove conversational filler. Today's date is {today}: replace relative "
            "time references such as 'this year', 'current' or 'latest' with the explicit "
            "year. Return ONLY the query text, no quotes.",
        ),
        (
            "human",
            "Original question: {question}\n"
            "Previous query (may be empty): {previous}\n"
            "Why the last attempt failed (may be empty): {feedback}",
        ),
    ]
)

GENERATE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a precise enterprise assistant. Answer the question using ONLY the "
            "numbered context below.\n"
            "Rules:\n"
            "1. Every factual sentence must end with citation markers like [1] or [2][3] "
            "referring to the context numbers.\n"
            "2. Never use outside knowledge and never invent numbers, names or dates.\n"
            "3. If the context does not contain the answer, say exactly what is missing "
            '(e.g. "The provided documents do not specify ...") instead of guessing.\n'
            "4. If the question contains a false premise, point it out using the context.\n"
            "5. Today's date is {today}. When the context gives figures for specific years, "
            "state the year and prefer the most recent; if only older figures are available, "
            "say so instead of presenting them as current.\n"
            "6. Be concise: a short paragraph or a few bullets.\n\n"
            "Context:\n{context}",
        ),
        ("human", "{question}"),
    ]
)

GROUNDEDNESS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You verify whether an AI answer is grounded in the supplied context. Answer "
            "'yes' only if every factual claim in the answer is stated in the context. "
            "Claims drawn from general or background knowledge that the context does not "
            "state are NOT grounded, even if they are true. Statements that the context "
            "lacks information count as grounded. Explain briefly, then give binary_score "
            "'yes' or 'no'.",
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
            "Rewrite the user's latest message as a single standalone question that can be "
            "understood without the conversation. Resolve pronouns and references such as "
            "'it', 'that' or 'what about Tokyo?' using the conversation. If the message is "
            "already standalone, return it unchanged. Return ONLY the question.",
        ),
        ("human", "Conversation so far:\n{history}\n\nLatest message: {question}"),
    ]
)
