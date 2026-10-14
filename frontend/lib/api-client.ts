/**
 * 浏览器端 API 客户端。
 *
 * 安全边界：
 * 1. access token 只放在模块内存里，不写入 localStorage 或 Cookie。
 * 2. refresh token 由后端放进 HttpOnly Cookie，前端 JavaScript 无法读取。
 * 3. 普通业务请求使用 Authorization 请求头；只有认证接口发送 Cookie。
 * 4. 每次登录周期都有独立 session epoch，旧会话的异步结果不能进入新会话。
 */

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:18080"
).replace(/\/$/, "");

const DEFAULT_REQUEST_TIMEOUT_MS = 15_000;

export type ApiRequestInit = RequestInit & {
  /** 单次 HTTP 尝试的超时时间；不填写时使用 15 秒。 */
  timeoutMs?: number;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
};

export type CurrentUser = {
  account_id: number;
  username: string;
  role: "customer" | "support" | "admin";
  customer_id: number | null;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * 请求属于已经失效的登录周期。
 *
 * 页面遇到这个错误时应静默丢弃结果，因为登出或换号流程已经负责更新界面。
 */
export class SessionChangedError extends Error {
  constructor() {
    super("登录状态已经发生变化");
    this.name = "SessionChangedError";
  }
}

let accessToken: string | null = null;

// epoch 每次登录或登出时递增。业务请求会记住发起时的值；只要值发生变化，
// 原请求就不能刷新令牌、重放请求或把结果交给新账号界面。
let sessionEpoch = 0;

// 同一个标签页、同一个 epoch 只允许进行一次刷新。Map 还让 logout 能等待所有
// 已发出的刷新响应落定，再删除最新 Cookie，避免晚到 Set-Cookie 覆盖退出响应。
const refreshesByEpoch = new Map<number, Promise<string>>();

export function captureSessionEpoch(): number {
  return sessionEpoch;
}

export function isSessionEpochCurrent(epoch: number): boolean {
  return epoch === sessionEpoch;
}

export function isSessionChangedError(error: unknown): error is SessionChangedError {
  return error instanceof SessionChangedError;
}

/** 供页面在最终认证失败时立即隔离当前登录周期。 */
export function invalidateLocalSession(): void {
  advanceSessionEpoch();
}

function advanceSessionEpoch(): number {
  sessionEpoch += 1;
  accessToken = null;
  return sessionEpoch;
}

function assertCurrentSession(expectedEpoch: number): void {
  if (!isSessionEpochCurrent(expectedEpoch)) throw new SessionChangedError();
}

async function readResponse<T>(response: Response): Promise<T> {
  if (response.status === 204 || response.status === 205) return undefined as T;

  const contentType = response.headers.get("content-type") ?? "";
  let data: unknown;

  try {
    data = contentType.includes("application/json")
      ? await response.json()
      : await response.text();
  } catch {
    throw new ApiError("服务器返回了无法解析的数据，请稍后重试。", response.status);
  }

  if (!response.ok) {
    throw new ApiError(getResponseErrorMessage(data, response.status), response.status);
  }

  return data as T;
}

function getResponseErrorMessage(data: unknown, status: number): string {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail?: unknown }).detail;

    if (typeof detail === "string" && detail.trim()) return detail;

    // FastAPI/Pydantic 的请求校验错误会把 detail 返回为数组。界面只提取字段名，
    // 避免把英文框架错误和内部校验结构直接展示给普通用户。
    if (Array.isArray(detail)) {
      const fields = detail
        .map((item) => {
          if (!item || typeof item !== "object" || !("loc" in item)) return null;
          const location = (item as { loc?: unknown }).loc;
          return Array.isArray(location) ? String(location.at(-1) ?? "") : null;
        })
        .filter((field): field is string => Boolean(field));
      const uniqueFields = [...new Set(fields)];
      return uniqueFields.length > 0
        ? `请求参数 ${uniqueFields.join("、")} 格式不正确，请检查后重试。`
        : "请求参数格式不正确，请检查后重试。";
    }
  }

  if (typeof data === "string" && data.trim() && status < 500) return data;
  if (status >= 500) return "服务器暂时无法处理请求，请稍后重试。";
  return "请求失败，请稍后重试。";
}

async function publicRequest<T>(
  path: string,
  init: ApiRequestInit = {},
  includeCookie = false,
): Promise<T> {
  const {
    timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
    signal: callerSignal,
    ...fetchInit
  } = init;
  const headers = new Headers(fetchInit.headers);

  // 只有确实发送 JSON 请求体时才声明 Content-Type，避免给空的 POST 请求
  // 增加没有必要的请求头。
  if (
    fetchInit.body
    && !(fetchInit.body instanceof FormData)
    && !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  const controller = new AbortController();
  let timeoutReached = false;
  const abortFromCaller = () => controller.abort(callerSignal?.reason);

  if (callerSignal?.aborted) {
    controller.abort(callerSignal.reason);
  } else {
    callerSignal?.addEventListener("abort", abortFromCaller, { once: true });
  }

  const timeoutId = globalThis.setTimeout(() => {
    timeoutReached = true;
    controller.abort();
  }, timeoutMs);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...fetchInit,
      headers,
      credentials: includeCookie ? "include" : "omit",
      signal: controller.signal,
    });
    // 在计时器仍然生效时读取响应体，避免服务器只返回响应头后长期不结束正文。
    return await readResponse<T>(response);
  } catch (error) {
    if (timeoutReached) {
      throw new ApiError("请求超时，请检查网络或稍后重试。", 408);
    }
    if (callerSignal?.aborted) {
      throw new ApiError("请求已取消。", 0);
    }
    if (error instanceof ApiError) throw error;
    // 浏览器通常把 fetch 网络故障表示为 TypeError，不同运行时也可能给出
    // DOMException。这里统一转换，避免把英文底层错误直接显示给用户。
    throw new ApiError("无法连接服务器，请检查后端服务和网络连接。", 0);
  } finally {
    globalThis.clearTimeout(timeoutId);
    callerSignal?.removeEventListener("abort", abortFromCaller);
  }

}

async function refreshAccessToken(expectedEpoch: number): Promise<string> {
  assertCurrentSession(expectedEpoch);

  const existing = refreshesByEpoch.get(expectedEpoch);
  if (existing) return existing;

  let refreshPromise: Promise<string>;
  refreshPromise = publicRequest<TokenResponse>(
    "/api/v1/auth/refresh",
    { method: "POST" },
    true,
  )
    .then((tokens) => {
      // 即使响应成功，只要用户在等待期间登出或换号，就不能把旧 token 写回来。
      assertCurrentSession(expectedEpoch);
      accessToken = tokens.access_token;
      return tokens.access_token;
    })
    .catch((error) => {
      if (isSessionEpochCurrent(expectedEpoch)) accessToken = null;
      throw error;
    })
    .finally(() => {
      if (refreshesByEpoch.get(expectedEpoch) === refreshPromise) {
        refreshesByEpoch.delete(expectedEpoch);
      }
    });

  refreshesByEpoch.set(expectedEpoch, refreshPromise);
  return refreshPromise;
}

/**
 * 调用需要登录的业务接口。
 *
 * 第一次返回 401 时，客户端尝试用 HttpOnly Cookie 刷新 access token，
 * 然后把原请求重放一次。请求始终绑定发起时的 session epoch：登出或换号后，
 * 它既不能使用新账号的刷新 Cookie，也不能把旧账号结果返回给页面。
 */
export async function authenticatedRequest<T>(
  path: string,
  init: ApiRequestInit = {},
): Promise<T> {
  const requestEpoch = captureSessionEpoch();

  async function send(token: string | null): Promise<T> {
    assertCurrentSession(requestEpoch);
    const headers = new Headers(init.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);

    const data = await publicRequest<T>(path, { ...init, headers });
    assertCurrentSession(requestEpoch);
    return data;
  }

  try {
    return await send(accessToken);
  } catch (error) {
    if (isSessionChangedError(error)) throw error;
    if (!(error instanceof ApiError) || error.status !== 401) throw error;
  }

  // 这次检查阻止旧请求在 logout 或新账号 login 后使用当前 Cookie 刷新。
  assertCurrentSession(requestEpoch);
  const newToken = await refreshAccessToken(requestEpoch);
  assertCurrentSession(requestEpoch);

  try {
    return await send(newToken);
  } catch (error) {
    if (
      error instanceof ApiError
      && error.status === 401
      && isSessionEpochCurrent(requestEpoch)
    ) {
      accessToken = null;
    }
    throw error;
  }
}

export async function login(username: string, password: string): Promise<CurrentUser> {
  // 登录代表一个全新的身份周期。先让旧请求失效，并等待旧 refresh 的 Set-Cookie
  // 被浏览器处理完成，避免旧 Cookie 响应晚于新账号的登录响应。
  const loginEpoch = advanceSessionEpoch();
  const oldRefreshes = [...refreshesByEpoch.values()];
  if (oldRefreshes.length > 0) await Promise.allSettled(oldRefreshes);
  assertCurrentSession(loginEpoch);

  const tokens = await publicRequest<TokenResponse>(
    "/api/v1/auth/login",
    {
      method: "POST",
      body: JSON.stringify({ username, password }),
    },
    // 登录响应会设置刷新 Cookie，所以跨端口开发环境也必须启用 credentials。
    true,
  );

  assertCurrentSession(loginEpoch);
  accessToken = tokens.access_token;

  try {
    return await authenticatedRequest<CurrentUser>("/api/v1/auth/me");
  } catch (error) {
    if (isSessionEpochCurrent(loginEpoch)) accessToken = null;
    throw error;
  }
}

/** 页面刷新后 access token 已丢失，通过刷新 Cookie 恢复登录状态。 */
export async function restoreSession(): Promise<CurrentUser | null> {
  const restoreEpoch = captureSessionEpoch();

  try {
    await refreshAccessToken(restoreEpoch);
    assertCurrentSession(restoreEpoch);
    return await authenticatedRequest<CurrentUser>("/api/v1/auth/me");
  } catch (error) {
    if (isSessionChangedError(error)) throw error;
    if (isSessionEpochCurrent(restoreEpoch)) accessToken = null;
    // 没有 Cookie、Cookie 过期或已撤销都表示正常的“未登录”状态。
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export async function logout(): Promise<void> {
  // 先递增 epoch，立即阻止旧业务请求回写或发起新的 refresh。
  const logoutEpoch = advanceSessionEpoch();

  // 不直接中断已经到达后端的 refresh：服务端可能已轮换 Cookie。等响应完成后，
  // 再发送 logout，浏览器就会携带最新 Cookie，删除响应也不会被晚到刷新覆盖。
  const pendingRefreshes = [...refreshesByEpoch.values()];
  if (pendingRefreshes.length > 0) await Promise.allSettled(pendingRefreshes);
  assertCurrentSession(logoutEpoch);

  await publicRequest<void>(
    "/api/v1/auth/logout",
    { method: "POST" },
    true,
  );
}
