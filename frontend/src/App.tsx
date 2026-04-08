import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const TOKEN_KEY = "mcp_chat_token";
const API_BASE_KEY = "mcp_api_base";
const SESSION_KEY = "mcp_session_id";

type Role = "user" | "assistant" | "system";

type Msg = {
  id: string;
  role: Role;
  content: string;
  pending?: boolean;
};

function getOrCreateSessionId(): string {
  try {
    let s = sessionStorage.getItem(SESSION_KEY);
    if (!s) {
      s = crypto.randomUUID();
      sessionStorage.setItem(SESSION_KEY, s);
    }
    return s;
  } catch {
    return crypto.randomUUID();
  }
}

function apiBase(): string {
  const env = import.meta.env.VITE_API_BASE;
  if (env && String(env).trim()) return String(env).replace(/\/$/, "");
  try {
    const saved = localStorage.getItem(API_BASE_KEY);
    if (saved && saved.trim()) return saved.replace(/\/$/, "");
  } catch {
    /* ignore */
  }
  return "";
}

function chatUrl(): string {
  const base = apiBase();
  return base ? `${base}/chat` : "/chat";
}

type ChatApiBody = {
  chat_id?: string;
  success?: boolean;
  type?: string;
  message?: string;
  data?: Record<string, unknown>;
  error?: string;
  response?: string;
};

function textFromResponse(data: ChatApiBody): string {
  if (typeof data.message === "string" && data.message.trim()) return data.message;
  if (typeof data.response === "string" && data.response.trim()) return data.response;
  if (typeof data.error === "string") return data.error;
  if (data.data && typeof data.data === "object") {
    const t = data.data.text;
    if (typeof t === "string" && t.trim()) return t;
  }
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return "Empty response";
  }
}

export default function App() {
  const [token, setToken] = useState(() => {
    try {
      return localStorage.getItem(TOKEN_KEY) ?? "";
    } catch {
      return "";
    }
  });
  const [baseOverride, setBaseOverride] = useState(() => {
    try {
      return localStorage.getItem(API_BASE_KEY) ?? "";
    } catch {
      return "";
    }
  });
  const [showSettings, setShowSettings] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [sending, setSending] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      if (token) localStorage.setItem(TOKEN_KEY, token);
      else localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ignore */
    }
  }, [token]);

  useEffect(() => {
    try {
      if (baseOverride.trim()) localStorage.setItem(API_BASE_KEY, baseOverride.trim());
      else localStorage.removeItem(API_BASE_KEY);
    } catch {
      /* ignore */
    }
  }, [baseOverride]);

  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, sending]);

  const send = useCallback(async () => {
    const q = input.trim();
    if (!q || sending) return;
    if (!token.trim()) {
      setShowSettings(true);
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: "system",
          content: "Add your Bearer token in settings (same credential your /chat API expects).",
        },
      ]);
      return;
    }

    const userId = crypto.randomUUID();
    setMessages((m) => [
      ...m,
      { id: userId, role: "user", content: q },
      { id: crypto.randomUUID(), role: "assistant", content: "", pending: true },
    ]);
    setInput("");
    setSending(true);

    try {
      const res = await fetch(chatUrl(), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token.trim()}`,
        },
        body: JSON.stringify({
          query: q,
          session_id: getOrCreateSessionId(),
        }),
      });

      let body: ChatApiBody;
      try {
        body = (await res.json()) as ChatApiBody;
      } catch {
        body = { message: await res.text().catch(() => "Invalid response") };
      }

      const text = res.ok ? textFromResponse(body) : textFromResponse(body) || `HTTP ${res.status}`;

      setMessages((m) => {
        const next = [...m];
        const pendingIdx = next.findIndex((x) => x.pending);
        if (pendingIdx >= 0) {
          next[pendingIdx] = {
            ...next[pendingIdx],
            content: text,
            pending: false,
          };
        }
        return next;
      });
    } catch (e) {
      const err = e instanceof Error ? e.message : "Request failed";
      setMessages((m) => {
        const next = [...m];
        const pendingIdx = next.findIndex((x) => x.pending);
        if (pendingIdx >= 0) {
          next[pendingIdx] = {
            ...next[pendingIdx],
            content: `Could not reach the server. ${err}\n\nIs the Flask app on port 8000? For dev, leave API base empty so Vite proxies /chat.`,
            pending: false,
          };
        }
        return next;
      });
    } finally {
      setSending(false);
    }
  }, [input, sending, token]);

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  const usingProxy = !import.meta.env.VITE_API_BASE?.trim() && !baseOverride.trim();

  return (
    <div
      style={{
        height: "100%",
        minHeight: "100dvh",
        display: "flex",
        flexDirection: "column",
        maxWidth: 900,
        margin: "0 auto",
        padding: "clamp(12px, 3vw, 24px)",
        paddingBottom: 16,
      }}
    >
      <header
        style={{
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 16,
          padding: "14px 18px",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 16,
          backdropFilter: "blur(12px)",
          boxShadow: "0 8px 32px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.06)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            aria-hidden
            style={{
              width: 40,
              height: 40,
              borderRadius: 12,
              background: "linear-gradient(135deg, #2d7fd4, #5eb0ff)",
              boxShadow: "0 0 24px var(--accent-glow)",
            }}
          />
          <div>
            <div style={{ fontWeight: 700, fontSize: "1.05rem", letterSpacing: "-0.02em" }}>
              Workspace assistant
            </div>
            <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
              {usingProxy ? "Dev proxy → localhost:8000/chat" : `${chatUrl()}`}
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setShowSettings((s) => !s)}
          style={btnGhost()}
        >
          {token.trim() ? "Settings" : "Connect"}
        </button>
      </header>

      {showSettings && (
        <div
          style={{
            flexShrink: 0,
            marginBottom: 14,
            padding: 16,
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 16,
            display: "grid",
            gap: 12,
          }}
        >
          <label style={labelStyle}>
            API base URL (optional)
            <input
              value={baseOverride}
              onChange={(e) => setBaseOverride(e.target.value)}
              placeholder="Empty = use Vite proxy (/chat) in dev"
              style={inputStyle}
              autoComplete="off"
            />
          </label>
          <label style={labelStyle}>
            Bearer token
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Authorization token for POST /chat"
              style={inputStyle}
              autoComplete="off"
            />
          </label>
          <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-muted)" }}>
            Matches your Flask handler: JSON body <code style={inlineCode}>`{"{"} query, session_id {"}"}`</code> and{" "}
            <code style={inlineCode}>Authorization: Bearer …</code>
          </p>
        </div>
      )}

      <div
        ref={listRef}
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: "auto",
          paddingRight: 4,
          display: "flex",
          flexDirection: "column",
          gap: 14,
        }}
      >
        {messages.length === 0 && (
          <div
            style={{
              margin: "auto",
              textAlign: "center",
              maxWidth: 340,
              color: "var(--text-muted)",
              fontSize: "0.92rem",
              lineHeight: 1.6,
            }}
          >
            <p style={{ margin: "0 0 8px", color: "var(--text)", fontWeight: 600 }}>
              Start a conversation
            </p>
            Messages are sent to <strong style={{ color: "var(--accent)" }}>/chat</strong> on your running Flask app.
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}
      </div>

      <div
        style={{
          flexShrink: 0,
          marginTop: 14,
          padding: "12px 14px",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 16,
          backdropFilter: "blur(12px)",
          boxShadow: "0 -4px 24px rgba(0,0,0,0.15)",
        }}
      >
        <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Message…"
            rows={1}
            style={{
              ...inputStyle,
              flex: 1,
              resize: "none",
              minHeight: 48,
              maxHeight: 160,
              paddingTop: 13,
              paddingBottom: 13,
            }}
          />
          <button
            type="button"
            disabled={sending || !input.trim()}
            onClick={() => void send()}
            style={btnPrimary(sending || !input.trim())}
          >
            {sending ? "…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ msg }: { msg: Msg }) {
  const isUser = msg.role === "user";
  const isSystem = msg.role === "system";

  if (isSystem) {
    return (
      <div style={{ textAlign: "center" }}>
        <span
          style={{
            display: "inline-block",
            padding: "8px 14px",
            fontSize: "0.82rem",
            color: "var(--text-muted)",
            background: "rgba(255,180,100,0.12)",
            border: "1px solid rgba(255,180,100,0.25)",
            borderRadius: 999,
          }}
        >
          {msg.content}
        </span>
      </div>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        animation: "chat-fade-in 0.35s ease-out",
      }}
    >
      <div
        style={{
          maxWidth: "min(92%, 640px)",
          padding: "14px 18px",
          borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
          background: isUser ? "var(--user-bubble)" : "var(--assistant-bubble)",
          border: isUser ? "none" : "1px solid var(--border)",
          boxShadow: isUser ? "0 4px 24px rgba(45,127,212,0.25)" : "0 4px 20px rgba(0,0,0,0.2)",
          color: isUser ? "#fff" : "var(--text)",
        }}
      >
        {msg.pending ? (
          <TypingDots />
        ) : isUser ? (
          <span style={{ whiteSpace: "pre-wrap", fontSize: "0.95rem" }}>{msg.content}</span>
        ) : (
          <div className="md-content">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}

function TypingDots() {
  return (
    <span style={{ display: "flex", gap: 6, alignItems: "center", height: 22 }}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: 7,
            height: 7,
            borderRadius: "50%",
            background: "var(--accent)",
            opacity: 0.35,
            animation: `chat-pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
          }}
        />
      ))}
    </span>
  );
}

const inlineCode: CSSProperties = {
  fontSize: "0.85em",
  background: "rgba(0,0,0,0.35)",
  padding: "0.1em 0.35em",
  borderRadius: 4,
};

const labelStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 6,
  fontSize: "0.8rem",
  fontWeight: 600,
  color: "var(--text-muted)",
};

const inputStyle: CSSProperties = {
  width: "100%",
  border: "1px solid var(--border)",
  borderRadius: 10,
  padding: "12px 14px",
  fontSize: "0.9rem",
  fontFamily: "inherit",
  background: "rgba(0,0,0,0.25)",
  color: "var(--text)",
  outline: "none",
};

function btnGhost(): CSSProperties {
  return {
    border: "1px solid var(--border)",
    background: "rgba(255,255,255,0.05)",
    color: "var(--text)",
    padding: "10px 16px",
    borderRadius: 10,
    fontWeight: 600,
    fontSize: "0.85rem",
    cursor: "pointer",
    fontFamily: "inherit",
  };
}

function btnPrimary(disabled: boolean): CSSProperties {
  return {
    border: "none",
    background: disabled ? "rgba(59,158,255,0.35)" : "linear-gradient(135deg, #2d7fd4, #4a9ef0)",
    color: "#fff",
    padding: "12px 22px",
    borderRadius: 12,
    fontWeight: 700,
    fontSize: "0.9rem",
    cursor: disabled ? "not-allowed" : "pointer",
    fontFamily: "inherit",
    boxShadow: disabled ? "none" : "0 4px 20px var(--accent-glow)",
    flexShrink: 0,
  };
}
