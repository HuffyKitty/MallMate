"use client";

import { FormEvent, useRef, useState } from "react";

type Source = { title: string; version: string; uri: string };
type ChatMessage = { role: "user" | "assistant"; text: string; sources?: Source[] };
type Preview = {
  eligible: boolean;
  reason: string;
  order_id: number;
  case_type: string;
  application_reason: string;
  decision_code: string;
  requires_evidence: boolean;
  requires_human: boolean;
  policy_version: string;
};

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:18080";

async function api<T>(path: string, user: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", "X-Demo-User": user, ...init?.headers },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "请求失败");
  return data as T;
}

export default function Home() {
  const [user, setUser] = useState("demo-alice");
  const [conversationId, setConversationId] = useState<string>();
  const [chatInput, setChatInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [orderId, setOrderId] = useState("1001");
  const [caseType, setCaseType] = useState<"refund" | "return" | "exchange">("return");
  const [reason, setReason] = useState("灯罩收到时有裂纹");
  const [preview, setPreview] = useState<Preview>();
  const previewKey = useRef<string | null>(null);
  const [caseResult, setCaseResult] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function resetForUser(nextUser: string) {
    setUser(nextUser);
    setConversationId(undefined);
    setMessages([]);
    setPreview(undefined);
    previewKey.current = null;
    setCaseResult("");
    setError("");
  }

  async function sendChat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = chatInput.trim();
    if (!message) return;
    setBusy(true);
    setError("");
    setChatInput("");
    setMessages((old) => [...old, { role: "user", text: message }]);
    try {
      const data = await api<{ conversation_id: string; answer: string; sources: Source[] }>(
        "/api/v1/chat", user,
        { method: "POST", body: JSON.stringify({ message, conversation_id: conversationId }) },
      );
      setConversationId(data.conversation_id);
      setMessages((old) => [...old, { role: "assistant", text: data.answer, sources: data.sources }]);
    } catch (caught) {
      setError((caught as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function makePreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setPreview(undefined);
    previewKey.current = null;
    setCaseResult("");
    try {
      const data = await api<Preview>("/api/v1/after-sales/preview", user, {
        method: "POST", body: JSON.stringify({ order_id: Number(orderId), case_type: caseType, reason }),
      });
      setPreview(data);
      previewKey.current = crypto.randomUUID();
    } catch (caught) {
      setError((caught as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function confirmCase() {
    if (!preview?.eligible) return;
    setBusy(true);
    setError("");
    try {
      const key = previewKey.current ?? crypto.randomUUID();
      previewKey.current = key;
      const data = await api<{ case_id: number; status: string }>("/api/v1/after-sales/confirm", user, {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: JSON.stringify({
          order_id: preview.order_id,
          case_type: preview.case_type,
          reason: preview.application_reason,
          confirmed: true,
        }),
      });
      setCaseResult(`申请 #${data.case_id} 已创建，状态：${data.status}`);
      setPreview(undefined);
      previewKey.current = null;
    } catch (caught) {
      setError((caught as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <header>
        <div><span className="eyebrow">MALLMATE / DEMO</span><h1>电商客服与售后 Agent</h1></div>
        <label>演示账号 <select value={user} onChange={(e) => resetForUser(e.target.value)}>
          <option value="demo-alice">Alice（订单 1001～1008）</option>
          <option value="demo-bob">Bob（订单 2001～2003）</option>
          <option value="demo-carol">Carol（订单 3001 / 3002）</option>
        </select></label>
      </header>
      <div className="grid">
        <section className="panel chat">
          <h2>客服对话</h2>
          <p className="hint">试试“退货上门取件要多久”、“查询订单 1001”或“订单 1002 的物流到哪了”。</p>
          <div className="messages" aria-live="polite">
            {messages.length === 0 && <p className="empty">发送一条消息开始演示。</p>}
            {messages.map((item, index) => <div key={index} className={`bubble ${item.role}`}>
              <strong>{item.role === "user" ? "你" : "MallMate"}</strong>
              <p>{item.text}</p>
              {item.sources?.map((source) => <small key={source.uri}>来源：{source.title} · {source.version} · {source.uri}</small>)}
            </div>)}
          </div>
          <form className="input-row" onSubmit={sendChat}>
            <input value={chatInput} onChange={(e) => setChatInput(e.target.value)} placeholder="输入问题" aria-label="输入问题" />
            <button disabled={busy || !chatInput.trim()}>发送</button>
          </form>
        </section>
        <section className="panel">
          <h2>售后申请</h2>
          <p className="hint">先查看规则结果，再确认创建模拟申请。</p>
          <form className="case-form" onSubmit={makePreview}>
            <label>订单号<input value={orderId} onChange={(e) => { setOrderId(e.target.value); setPreview(undefined); previewKey.current = null; }} inputMode="numeric" /></label>
            <label>申请类型<select value={caseType} onChange={(e) => { setCaseType(e.target.value as "refund" | "return" | "exchange"); setPreview(undefined); previewKey.current = null; }}>
              <option value="refund">退款</option><option value="return">退货</option><option value="exchange">换货</option>
            </select></label>
            <label>问题说明<textarea value={reason} onChange={(e) => { setReason(e.target.value); setPreview(undefined); previewKey.current = null; }} rows={4} /></label>
            <button disabled={busy}>查看申请预览</button>
          </form>
          {preview && <div className="preview">
            <strong>{preview.eligible ? "可以提交审核" : "暂不能提交"}</strong>
            <p>{preview.reason}</p>
            <p>订单 {preview.order_id} · {preview.case_type} · {preview.application_reason}</p>
            <p>规则：{preview.policy_version} · 决策码：{preview.decision_code}</p>
            {preview.requires_evidence && <p>需要补充图片或视频凭证。</p>}
            {preview.requires_human && <p>该申请需要人工审核。</p>}
            {preview.eligible && <button disabled={busy} onClick={confirmCase}>确认提交</button>}
          </div>}
          {caseResult && <p className="success">{caseResult}</p>}
          {error && <p className="error" role="alert">{error}</p>}
        </section>
      </div>
      <footer>本页面使用演示数据和简化规则；模型、正式认证、图片与人工队列将在后续阶段接入。</footer>
    </main>
  );
}

