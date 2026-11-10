import type { ReactNode } from "react";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="auth">
      <aside className="auth-brand">
        <div className="brand-name">CRAG</div>
        <div>
          <h1>Clear answers from your own documents.</h1>
          <ul>
            <li>
              <strong>Upload once</strong>
              Policies, reports, manuals and notes in PDF, TXT or Markdown.
            </li>
            <li>
              <strong>Ask in plain language</strong>
              Get a direct answer in seconds, with the exact sources it came from.
            </li>
            <li>
              <strong>Checked before you see it</strong>
              Every answer is verified against your documents to avoid guesswork.
            </li>
          </ul>
        </div>
        <footer>Your documents stay private to your account.</footer>
      </aside>
      <main className="auth-main">
        <div className="auth-card">
          <div className="mobile-brand">CRAG</div>
          {children}
        </div>
      </main>
    </div>
  );
}

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
