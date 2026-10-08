import { FormEvent, useState } from "react";
import type { Strings } from "../lib/i18n";

interface Msg {
  role: "user" | "bot";
  text: string;
}

export function AskPanel({ lang, t }: { lang: string; t: Strings }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function send(q: string) {
    const question = q.trim();
    if (!question || loading) return;
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setInput("");
    setLoading(true);
    try {
      const resp = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, lang }),
      });
      if (!resp.ok) throw new Error(String(resp.status));
      const data = await resp.json();
      setMsgs((m) => [...m, { role: "bot", text: data.answer || t.askError }]);
    } catch {
      setMsgs((m) => [...m, { role: "bot", text: t.askError }]);
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    send(input);
  }

  return (
    <div className="panel ask-panel" data-testid="ask-panel">
      <h3>{t.askTitle}</h3>

      {msgs.length > 0 && (
        <div className="ask-log" data-testid="ask-log">
          {msgs.map((m, i) => (
            <div key={i} className={`ask-msg ${m.role}`}>
              {m.text}
            </div>
          ))}
          {loading && <div className="ask-msg bot muted-line">{t.askThinking}</div>}
        </div>
      )}

      {msgs.length === 0 && (
        <div className="ask-suggest">
          {t.askSuggestions.map((q, i) => (
            <button key={i} type="button" onClick={() => send(q)}>
              {q}
            </button>
          ))}
        </div>
      )}

      <form className="steer-form" onSubmit={onSubmit}>
        <input
          data-testid="ask-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t.askPlaceholder}
          aria-label="Ask Platon"
          maxLength={500}
        />
        <button type="submit" data-testid="ask-send" disabled={loading}>
          {t.askSend}
        </button>
      </form>
    </div>
  );
}
