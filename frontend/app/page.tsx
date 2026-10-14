"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import {
  ApiError,
  authenticatedRequest,
  captureSessionEpoch,
  CurrentUser,
  invalidateLocalSession,
  isSessionChangedError,
  isSessionEpochCurrent,
  login,
  logout,
  restoreSession,
} from "../lib/api-client";

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

type SessionStatus = "checking" | "anonymous" | "authenticated";

// NEXT_PUBLIC_ 变量会在 Next.js 构建时写入浏览器代码。只有本地 Docker
// 明确传入 true 才展示演示凭据，其他环境默认使用空白登录表单。
const showDemoCredentials =
  process.env.NEXT_PUBLIC_SHOW_DEMO_CREDENTIALS === "true";

const roleNames: Record<CurrentUser["role"], string> = {
  customer: "顾客",
  support: "客服",
  admin: "管理员",
};

export default function Home() {
  const [sessionStatus, setSessionStatus] = useState<SessionStatus>("checking");
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [username, setUsername] = useState(showDemoCredentials ? "demo-alice" : "");
  const [password, setPassword] = useState(showDemoCredentials ? "MallMate123!" : "");
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");

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

  // access token 只存在内存中，因此浏览器刷新页面后需要利用 HttpOnly
  // refresh Cookie 换取新令牌，再调用 /me 恢复当前用户。
  useEffect(() => {
    let active = true;

    restoreSession()
      .then((user) => {
        if (!active) return;
        setCurrentUser(user);
        setSessionStatus(user ? "authenticated" : "anonymous");
      })
      .catch((caught: unknown) => {
        if (!active) return;
        setAuthError(getErrorMessage(caught));
        setSessionStatus("anonymous");
      });

    return () => {
      active = false;
    };
  }, []);

  function resetWorkspace() {
    setConversationId(undefined);
    setMessages([]);
    setPreview(undefined);
    previewKey.current = null;
    setCaseResult("");
    setError("");
    setBusy(false);
  }

  function handleRequestError(caught: unknown) {
    // 登出或换号已经更新了页面，旧会话的晚到结果不需要提示错误。
    if (isSessionChangedError(caught)) return;

    if (caught instanceof ApiError && caught.status === 401) {
      invalidateLocalSession();
      resetWorkspace();
      setCurrentUser(null);
      setSessionStatus("anonymous");
      setAuthError("登录状态已失效，请重新登录。");
      return;
    }
    setError(getErrorMessage(caught));
  }

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthBusy(true);
    setAuthError("");

    try {
      const user = await login(username.trim(), password);
      resetWorkspace();
      setCurrentUser(user);
      setSessionStatus("authenticated");
    } catch (caught) {
      setAuthError(getErrorMessage(caught));
    } finally {
      setAuthBusy(false);
    }
  }

  async function submitLogout() {
    setAuthBusy(true);
    setAuthError("");

    // logout() 在返回 Promise 时已经递增 session epoch。界面立即离开业务区，
    // 后台再等待正在进行的 refresh 并撤销最新刷新会话。
    const logoutRequest = logout();
    resetWorkspace();
    setCurrentUser(null);
    setSessionStatus("anonymous");

    try {
      await logoutRequest;
    } catch (caught) {
      if (isSessionChangedError(caught)) return;
      // 后端退出失败时仍清理本地登录态，同时说明刷新会话可能未成功撤销。
      setAuthError(`已清除本地登录状态；服务器退出失败：${getErrorMessage(caught)}`);
    } finally {
      setAuthBusy(false);
    }
  }

  async function sendChat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = chatInput.trim();
    if (!message) return;
    const requestEpoch = captureSessionEpoch();
    setBusy(true);
    setError("");
    setChatInput("");
    setMessages((old) => [...old, { role: "user", text: message }]);

    try {
      const data = await authenticatedRequest<{
        conversation_id: string;
        answer: string;
        sources: Source[];
      }>("/api/v1/chat", {
        method: "POST",
        body: JSON.stringify({ message, conversation_id: conversationId }),
      });
      if (!isSessionEpochCurrent(requestEpoch)) return;
      setConversationId(data.conversation_id);
      setMessages((old) => [
        ...old,
        { role: "assistant", text: data.answer, sources: data.sources },
      ]);
    } catch (caught) {
      // 网络错误也可能晚于登出或换号到达；旧会话的任何结果都应静默丢弃。
      if (!isSessionEpochCurrent(requestEpoch)) return;
      handleRequestError(caught);
    } finally {
      if (isSessionEpochCurrent(requestEpoch)) setBusy(false);
    }
  }

  async function makePreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const requestEpoch = captureSessionEpoch();
    setBusy(true);
    setError("");
    setPreview(undefined);
    previewKey.current = null;
    setCaseResult("");

    try {
      const data = await authenticatedRequest<Preview>("/api/v1/after-sales/preview", {
        method: "POST",
        body: JSON.stringify({
          order_id: Number(orderId),
          case_type: caseType,
          reason,
        }),
      });
      if (!isSessionEpochCurrent(requestEpoch)) return;
      setPreview(data);
      previewKey.current = crypto.randomUUID();
    } catch (caught) {
      if (!isSessionEpochCurrent(requestEpoch)) return;
      handleRequestError(caught);
    } finally {
      if (isSessionEpochCurrent(requestEpoch)) setBusy(false);
    }
  }

  async function confirmCase() {
    if (!preview?.eligible) return;
    const requestEpoch = captureSessionEpoch();
    setBusy(true);
    setError("");

    try {
      const key = previewKey.current ?? crypto.randomUUID();
      previewKey.current = key;
      const data = await authenticatedRequest<{ case_id: number; status: string }>(
        "/api/v1/after-sales/confirm",
        {
          method: "POST",
          headers: { "Idempotency-Key": key },
          body: JSON.stringify({
            order_id: preview.order_id,
            case_type: preview.case_type,
            reason: preview.application_reason,
            confirmed: true,
          }),
        },
      );
      if (!isSessionEpochCurrent(requestEpoch)) return;
      setCaseResult(`申请 #${data.case_id} 已创建，状态：${data.status}`);
      setPreview(undefined);
      previewKey.current = null;
    } catch (caught) {
      if (!isSessionEpochCurrent(requestEpoch)) return;
      handleRequestError(caught);
    } finally {
      if (isSessionEpochCurrent(requestEpoch)) setBusy(false);
    }
  }

  if (sessionStatus === "checking") {
    return (
      <main className="session-page">
        <section className="session-card" aria-live="polite">
          <span className="eyebrow">MALLMATE</span>
          <h1>正在恢复登录状态</h1>
          <p className="hint">正在检查安全会话，请稍候。</p>
          <div className="loading-bar" aria-hidden="true" />
        </section>
      </main>
    );
  }

  if (sessionStatus === "anonymous" || !currentUser) {
    return (
      <main className="session-page">
        <section className="session-card">
          <span className="eyebrow">MALLMATE / SECURE ACCESS</span>
          <h1>登录电商售后助手</h1>
          <p className="hint">登录后可以查询本人订单、咨询客服并提交售后申请。</p>

          <form className="login-form" onSubmit={submitLogin}>
            <label>
              登录账号
              <input
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                disabled={authBusy}
                minLength={3}
                required
              />
            </label>
            <label>
              登录密码
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                disabled={authBusy}
                minLength={8}
                required
              />
            </label>
            <button disabled={authBusy || !username.trim() || !password}>
              {authBusy ? "正在登录…" : "登录"}
            </button>
          </form>

          {showDemoCredentials && (
            <div className="demo-note">
              <strong>本地开发账号</strong>
              <span>demo-alice / MallMate123!</span>
            </div>
          )}
          {authError && <p className="error" role="alert">{authError}</p>}
        </section>
      </main>
    );
  }

  return (
    <main>
      <header>
        <div>
          <span className="eyebrow">MALLMATE / AGENT</span>
          <h1>电商客服与售后 Agent</h1>
        </div>
        <div className="account-box">
          <div>
            <strong>{currentUser.username}</strong>
            <span>{roleNames[currentUser.role]}</span>
          </div>
          <button className="secondary-button" onClick={submitLogout} disabled={authBusy}>
            {authBusy ? "正在退出…" : "退出登录"}
          </button>
        </div>
      </header>

      <div className="grid">
        <section className="panel chat">
          <h2>客服对话</h2>
          <p className="hint">试试“退货上门取件要多久”、“查询订单 1001”或“订单 1002 的物流到哪了”。</p>
          <div className="messages" aria-live="polite">
            {messages.length === 0 && <p className="empty">发送一条消息开始咨询。</p>}
            {messages.map((item, index) => (
              <div key={index} className={`bubble ${item.role}`}>
                <strong>{item.role === "user" ? "你" : "MallMate"}</strong>
                <p>{item.text}</p>
                {item.sources?.map((source) => (
                  <small key={source.uri}>
                    来源：{source.title} · {source.version} · {source.uri}
                  </small>
                ))}
              </div>
            ))}
          </div>
          <form className="input-row" onSubmit={sendChat}>
            <input
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              placeholder="输入问题"
              aria-label="输入问题"
            />
            <button disabled={busy || !chatInput.trim()}>发送</button>
          </form>
        </section>

        <section className="panel">
          <h2>售后申请</h2>
          <p className="hint">先查看规则结果，再确认创建申请。</p>
          <form className="case-form" onSubmit={makePreview}>
            <label>
              订单号
              <input
                value={orderId}
                onChange={(event) => {
                  setOrderId(event.target.value);
                  setPreview(undefined);
                  previewKey.current = null;
                }}
                inputMode="numeric"
              />
            </label>
            <label>
              申请类型
              <select
                value={caseType}
                onChange={(event) => {
                  setCaseType(event.target.value as "refund" | "return" | "exchange");
                  setPreview(undefined);
                  previewKey.current = null;
                }}
              >
                <option value="refund">退款</option>
                <option value="return">退货</option>
                <option value="exchange">换货</option>
              </select>
            </label>
            <label>
              问题说明
              <textarea
                value={reason}
                onChange={(event) => {
                  setReason(event.target.value);
                  setPreview(undefined);
                  previewKey.current = null;
                }}
                rows={4}
              />
            </label>
            <button disabled={busy}>查看申请预览</button>
          </form>

          {preview && (
            <div className="preview">
              <strong>{preview.eligible ? "可以提交审核" : "暂不能提交"}</strong>
              <p>{preview.reason}</p>
              <p>订单 {preview.order_id} · {preview.case_type} · {preview.application_reason}</p>
              <p>规则：{preview.policy_version} · 决策码：{preview.decision_code}</p>
              {preview.requires_evidence && <p>需要补充图片或视频凭证。</p>}
              {preview.requires_human && <p>该申请需要人工审核。</p>}
              {preview.eligible && (
                <button disabled={busy} onClick={confirmCase}>确认提交</button>
              )}
            </div>
          )}
          {caseResult && <p className="success">{caseResult}</p>}
          {error && <p className="error" role="alert">{error}</p>}
        </section>
      </div>
      <footer>当前账号只能访问后端认证和授权规则允许的数据。</footer>
    </main>
  );
}

function getErrorMessage(caught: unknown): string {
  if (caught instanceof Error) return caught.message;
  return "请求失败，请稍后重试";
}
