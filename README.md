# CRAG: Corrective & Self-Reflective Agentic RAG

> An enterprise-grade, stateful Retrieval-Augmented Generation (RAG) system engineered to autonomously detect retrieval failure, eliminate hallucinations, and ground responses using LangGraph, hybrid vector search, and dynamic web fallback.

CRAG is a private document assistant. You upload your documents, ask questions in plain language, and get clear answers that are checked against your sources before you see them. Every answer shows exactly where it came from.

---

## What you can do

- **Create an account** with your email and password. Your email is confirmed with a 6-digit code.
- **Upload documents** in PDF, TXT or Markdown, up to 20 MB each. Your library is private to your account.
- **Choose the documents for each chat.** Pick one or several before your first question, and change the selection at any time.
- **Ask questions** in everyday language, including tricky ones and follow-ups, and watch the answer appear as it's written.
- **Get an honest "not found".** If the selected documents don't contain the answer, CRAG says so instead of guessing.
- **Turn on web search when you want more.** Web search is off by default. Switch it on, or click **Search the web for this** on a "not found" answer, and CRAG will look online to fill the gaps, with your documents still coming first.
- **See the sources** for every answer, numbered and linked to the passage or web page they came from.
- **Ask follow-up questions.** CRAG remembers the conversation, and all your chats are saved for later.
- **Keep a profile** with your name, phone number, date of birth, gender and photo.
- **Reset a forgotten password** with a code sent to your email.

## How it works

When you ask a question, CRAG:

1. **Understands follow-ups.** A question like "did he play badminton?" is turned into a complete question using the conversation, keeping names exactly as they appear.
2. **Searches the selected documents.** It combines keyword matching with meaning-based search, so it finds the right passages even when the wording differs.
3. **Picks the best passages.** A ranking model keeps only the few passages that really matter.
4. **Checks they're relevant.** An AI reviewer reads each passage, knowing which document it comes from (for example, that a line in a resume describes its owner), and discards anything that doesn't help.
5. **Looks further only if you allow it.** When web search is on and your documents don't cover the question, it searches the web, ignoring pages about different people or organizations with similar names. When web search is off, it tells you the answer wasn't found.
6. **Writes the answer** in plain language using only those sources, with a citation for every fact.
7. **Double-checks the answer.** A second review makes sure every statement is backed by the sources and that the question is actually answered. If not, CRAG tries again, and if it still can't confirm an answer, it tells you so instead of guessing.

All of this happens in the background. You only see the answer, its sources, and whether it was confirmed.

---

## Requirements

- **Windows, macOS or Linux**
- **Python 3.11 or newer:** https://www.python.org/downloads/
- **Node.js 20 or newer:** https://nodejs.org
- **An OpenAI API key** (required): https://platform.openai.com/api-keys
- **A Tavily API key** (recommended, for web search): https://app.tavily.com
- **A Gmail account** (recommended, for sending verification emails)

## Installation

Open a terminal in the project folder and run the commands below. They're shown for Windows; on macOS and Linux, use `.venv/bin/python` and `cp` instead.

**1. Install the Python packages**

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

**2. Build the web interface**

```powershell
cd frontend
npm install
npm run build
cd ..
```

**3. Create your settings file**

```powershell
copy .env.example .env
```

Then open `.env` and fill in your keys, as described below.

## Configuration

All settings live in the `.env` file in the project folder. It contains your private keys, so never share it or upload it anywhere. The repository only includes `.env.example`, which shows the format.

### API keys

```env
OPENAI_API_KEY=sk-...        # required
TAVILY_API_KEY=tvly-...      # recommended: lets CRAG search the web when your documents don't have the answer
```

### Email (verification codes and password resets)

CRAG sends emails through Gmail:

1. Go to https://myaccount.google.com/security and turn on **2-Step Verification**.
2. Go to https://myaccount.google.com/apppasswords, create an app password named `CRAG`, and copy the 16-character password.
3. Add these lines to `.env`:
   ```env
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=you@gmail.com
   SMTP_PASSWORD=abcd efgh ijkl mnop
   SMTP_FROM=CRAG <you@gmail.com>
   ```
4. Check that it works:
   ```powershell
   .venv\Scripts\python -m server.mailer you@example.com
   ```

If email isn't set up, CRAG still works: the codes are printed in the server window instead of being emailed. That's handy when you're trying CRAG on your own computer.

A personal Gmail account can send a few hundred emails a day. For a larger audience, use an email service such as Brevo, Resend or SendGrid; they work the same way, by changing the `SMTP_` lines.

## Start the app

```powershell
.venv\Scripts\python -m server
```

Your browser opens **http://localhost:8000**. The first start takes a little longer while CRAG prepares its search models, and a loading screen shows while that happens. To stop the app, press **Ctrl + C** in the terminal.

## Using CRAG

1. **Create an account.** Enter your email and a password on the sign-in page. If the email is new, CRAG takes you to sign-up to add your name and phone number.
2. **Confirm your email.** Enter the 6-digit code from the email. Check your spam folder if you don't see it within a minute.
3. **Add documents.** Open **My documents** and drag files in, or click to choose them.
4. **Start a chat.** Click **New chat** and tick the documents you want to ask about. You can change them later from the **Documents** button at the top of the chat.
5. **Ask a question.** Type it and press Enter. Click a number in the answer to see its source.
6. **Need more than your documents?** Turn on **Web search** at the top of the chat, or click **Search the web for this** when CRAG says the answer wasn't found.
7. **Update your profile.** Open **Profile** to add a photo, your date of birth and gender, or to change your password.

An answer marked **"Checked against the sources"** has been verified. **"Not fully confirmed"** means you should review the listed sources yourself.

## Privacy and security

- Your documents, conversations and profile are visible only to your account.
- Passwords are stored securely hashed and are never kept in readable form.
- Email codes expire after 10 minutes and stop working after 5 wrong attempts.
- Repeated failed sign-in attempts are temporarily blocked.
- Everything is stored on the computer running CRAG, in the `data/` and `.chroma/` folders. Only your questions and the relevant passages are sent to OpenAI (and Tavily, for web searches) to produce answers.

## Troubleshooting

| Problem | What to do |
|---|---|
| "The assistant isn't set up yet" | Add your `OPENAI_API_KEY` to `.env` and restart the app. |
| No verification email | Check the spam folder, then use "send a new code". Run `python -m server.mailer you@example.com` to test your email settings. |
| "Email sending isn't set up" message | Fill in the `SMTP_` lines in `.env` (see Configuration) and restart. |
| A PDF can't be read | Scanned PDFs are images with no text. Convert them with a text-recognition (OCR) tool first. |
| The page doesn't load | Make sure the app is running in the terminal and open http://localhost:8000. |
| Port 8000 is already in use | Start with `.venv\Scripts\python -m server --port 8001`. |

---

## For developers

Run the backend and frontend separately, with live reload:

```powershell
.venv\Scripts\python -m server --reload --no-browser    # API at http://localhost:8000
cd frontend; npm run dev                                # UI at http://localhost:5173
```

Project structure:

```text
server/      Web API: accounts, email codes, profile, documents, conversations, streaming chat
frontend/    React + TypeScript interface (Vite)
src/         The CRAG agent: retrieval, ranking, grading, web search, answer writing and checking (LangGraph)
config/      Settings, all adjustable from .env
```

Built with LangGraph, LangChain, OpenAI, ChromaDB, BM25, FlashRank, FastEmbed (`BAAI/bge-small-en-v1.5`), Tavily, FastAPI, SQLAlchemy and React.
