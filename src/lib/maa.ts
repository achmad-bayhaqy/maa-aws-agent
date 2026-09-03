// MAA AWS Agent — frontend helpers (Cognito + API contract v3)

export const CONFIG = {
  region: process.env.NEXT_PUBLIC_REGION || "us-east-1",
  poolId: process.env.NEXT_PUBLIC_COGNITO_POOL_ID || "",
  clientId: process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID || "",
  apiUrl: process.env.NEXT_PUBLIC_API_URL || "",
  idleTimeoutMs: 15 * 60 * 1000, // FR 1.4: sesi hangus 15 menit tanpa aktivitas
};

export const COG_URL = `https://cognito-idp.${CONFIG.region}.amazonaws.com/`;

export type Tokens = { IdToken: string; AccessToken: string; RefreshToken?: string };

async function cognito(op: string, payload: Record<string, unknown>): Promise<Record<string, any>> {
  const res = await fetch(COG_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": `AWSCognitoIdentityProviderService.${op}` },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.message || `${op} gagal (${res.status})`) as Error & { code?: string };
    err.code = data.__type || "";
    throw err;
  }
  return data;
}

export type LoginResult =
  | { kind: "tokens"; tokens: Tokens }
  | { kind: "mfa_setup"; session: string; username: string }
  | { kind: "mfa_challenge"; session: string; username: string }
  | { kind: "new_password"; session: string; username: string };

export async function login(username: string, password: string): Promise<LoginResult> {
  const r = await cognito("InitiateAuth", {
    AuthFlow: "USER_PASSWORD_AUTH",
    AuthParameters: { USERNAME: username, PASSWORD: password },
    ClientId: CONFIG.clientId,
  });
  if (r.AuthenticationResult) return { kind: "tokens", tokens: r.AuthenticationResult };
  if (r.ChallengeName === "NEW_PASSWORD_REQUIRED")
    return { kind: "new_password", session: r.Session, username };
  if (r.ChallengeName === "MFA_SETUP")
    return { kind: "mfa_setup", session: r.Session, username };
  if (r.ChallengeName === "SOFTWARE_TOKEN_MFA")
    return { kind: "mfa_challenge", session: r.Session, username };
  throw new Error(`Challenge tak dikenal: ${r.ChallengeName}`);
}

/** Challenge NEW_PASSWORD_REQUIRED: user undangan menyetel password baru.
 *  Respons bisa langsung tokens ATAU lanjut ke MFA_SETUP / SOFTWARE_TOKEN_MFA. */
export async function respondNewPasswordRequired(
  session: string,
  username: string,
  newPassword: string
): Promise<LoginResult & { tokens?: Tokens }> {
  const r = await cognito("RespondToAuthChallenge", {
    ChallengeName: "NEW_PASSWORD_REQUIRED",
    ClientId: CONFIG.clientId,
    Session: session,
    ChallengeResponses: { USERNAME: username, NEW_PASSWORD: newPassword },
  });
  if (r.AuthenticationResult) return { kind: "tokens", tokens: r.AuthenticationResult };
  if (r.ChallengeName === "MFA_SETUP")
    return { kind: "mfa_setup", session: r.Session, username };
  if (r.ChallengeName === "SOFTWARE_TOKEN_MFA")
    return { kind: "mfa_challenge", session: r.Session, username };
  throw new Error(`Setelah set password, challenge tak dikenal: ${r.ChallengeName}`);
}

export async function associateSoftwareToken(session: string): Promise<string> {
  const r = await cognito("AssociateSoftwareToken", { Session: session });
  return r.SecretCode as string;
}

export async function verifySoftwareToken(session: string, code: string): Promise<string> {
  const r = await cognito("VerifySoftwareToken", {
    Session: session, UserCode: code, FriendlyDeviceName: "MAA Mobile",
  });
  return r.Session as string;
}

export async function completeMfaSetup(session: string, username: string): Promise<Tokens> {
  const r = await cognito("RespondToAuthChallenge", {
    ChallengeName: "MFA_SETUP",
    ClientId: CONFIG.clientId,
    Session: session,
    ChallengeResponses: { USERNAME: username, PREFERRED_CHALLENGE: "SOFTWARE_TOKEN_MFA" },
  });
  return r.AuthenticationResult as Tokens;
}

export async function respondMfaChallenge(session: string, username: string, code: string): Promise<Tokens> {
  const r = await cognito("RespondToAuthChallenge", {
    ChallengeName: "SOFTWARE_TOKEN_MFA",
    ClientId: CONFIG.clientId,
    Session: session,
    ChallengeResponses: { USERNAME: username, SOFTWARE_TOKEN_MFA_CODE: code },
  });
  return r.AuthenticationResult as Tokens;
}

export async function revokeToken(refreshToken: string): Promise<void> {
  try {
    await cognito("RevokeToken", { Token: refreshToken, ClientId: CONFIG.clientId });
  } catch {
    /* best-effort */
  }
}

// ---------------- API (contract v3) ----------------
function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

async function apiFetch<T>(method: string, path: string, token: string, body?: unknown, query?: Record<string, string>): Promise<T> {
  const url = CONFIG.apiUrl + path + (query ? "?" + new URLSearchParams(query).toString() : "");
  const res = await fetch(url, {
    method,
    headers: authHeaders(token),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || data.message || `API ${res.status}`) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return data as T;
}

// ----- tipe inti -----

/** Mode pemilihan model (routing) — hanya 4, sesuai kontrak v3.4.2. */
export type ChatMode = "AUTO" | "FAST" | "DEEP" | "MANUAL";

/**
 * Mode tugas agent (gaya kerja) — TERPISAH dari pemilihan model.
 * STANDARD = percakapan normal; lainnya memicu perilaku agent khusus
 * (loop lebih panjang, prompt tambahan, tool khusus) di runtime.
 */
export type AgentMode =
  | "STANDARD"
  | "LONG"
  | "FULLSTACK"
  | "PRESENTATION"
  | "TODO"
  | "MULTI"
  | "RESEARCH";

export type MessageVersion = { text: string; ts: number; model?: string };

export type TodoItem = { content: string; status: "pending" | "in_progress" | "completed" | string };

/** Lampiran pada pesan (upload user atau artefak agent). */
export type MessageAtt = {
  name?: string;
  key?: string;
  size?: number;
  kind?: string; // upload | image | pdf | text | file | deck | webapp
  type?: string; // runtime mengirim "type": "image" — dipetakan ke kind saat render
  url?: string;
  slides?: number;
  files?: number;
};

export type ChatMessage = {
  role: "user" | "assistant" | string;
  text: string;
  ts: number;
  model?: string;
  edited?: boolean;
  versions?: MessageVersion[];
  atts?: MessageAtt[];
};

export type PendingConfirm = {
  confirmToken: string;
  challenge: string;
  operation: { tool: string; input: Record<string, unknown> };
};

export type Clarify = { question: string; options: string[] };

export type Attachment = { type: string; url: string; name?: string };

export type AutoRoute = { chosen: "FAST" | "DEEP" | "MANUAL" | string; model: string; reason?: string };

export type ChatStatus = {
  sessionId: string;
  status: "processing" | "done" | "error";
  mode?: string;
  modelId?: string;
  autoRoute?: AutoRoute;
  title?: string;
  messages: ChatMessage[];
  pendingConfirmation?: PendingConfirm | null;
  clarify?: Clarify | null;
  todos?: TodoItem[] | null;
  attachments?: Attachment[] | null;
  err?: string;
};

export type TraceEvent = { ts: string; type: string; content: string; model?: string };

export type SessionRow = {
  sessionId: string;
  title: string;
  status: string;
  mode?: string;
  createdAt?: string;
  updatedAt?: string;
};

export type MaaModel = {
  modelId: string;
  name: string;
  provider: string;
  group?: string;
  toolCompatible?: boolean;
  cacheSupported?: boolean;
  reasoning?: boolean;
};

export type ModelsResponse = {
  autoDefaults: { fast: string; deep: string };
  models: MaaModel[];
};

export type MeInfo = {
  userId: string;
  username: string;
  email?: string;
  role: "user" | "superadmin" | string;
};

export type AdminUser = {
  username: string;
  email?: string;
  name?: string; // preferred_username (nama tampilan, v3.5)
  status?: "CONFIRMED" | "FORCE_CHANGE_PASSWORD" | "UNCONFIRMED" | string;
  enabled?: boolean;
  created?: string;
  role?: string;
};

// ----- endpoint chat -----

export type SendChatBody = {
  message: string;
  mode: ChatMode;
  /** Mode tugas agent (gaya kerja) — default STANDARD. */
  agentMode?: AgentMode;
  /** Skill Library yang dimuat eksplisit dari picker UI (v4.0). */
  skill?: string;
  modelId?: string;
  sessionId?: string;
  editFrom?: number;
  attachments?: { key: string; name: string; contentType: string; size: number }[];
  /** true = jalankan ulang dari pesan user terakhir (jawaban lama jadi versi) */
  regenerate?: boolean;
};

export const sendChat = (token: string, body: SendChatBody) =>
  apiFetch<{ sessionId: string; status: string }>("POST", "/chat", token, body);

export const getStatus = (token: string, sessionId: string) =>
  apiFetch<ChatStatus>("GET", "/chat/status", token, undefined, { sessionId });

export const getTrace = (token: string, sessionId: string, after: number) =>
  apiFetch<{ events: TraceEvent[] }>("GET", "/chat/trace", token, undefined, { sessionId, after: String(after) });

export const getSessions = (token: string) =>
  apiFetch<{ sessions: SessionRow[] }>("GET", "/chat/sessions", token);

export const deleteSession = (token: string, sessionId: string) =>
  apiFetch<{ deleted: boolean }>("DELETE", "/chat/sessions", token, undefined, { sessionId });

export const getModels = (token: string) => apiFetch<ModelsResponse>("GET", "/models", token);

export const confirmDestructive = (
  token: string,
  sessionId: string,
  confirmToken: string,
  typed1: string,
  typed2: string
) =>
  apiFetch<{ status: string; message?: string; result?: Record<string, unknown> }>(
    "POST", "/chat/confirm", token, { sessionId, confirmToken, typed1, typed2 }
  );

// ----- knowledge base -----

export const listKbDocs = (token: string) =>
  apiFetch<{ docs: { key: string; name: string; size: number; updated: string }[] }>("GET", "/kb/docs", token);

export const presignUpload = (token: string, name: string, contentType: string) =>
  apiFetch<{ uploadUrl: string; key: string; headers: Record<string, string> }>("POST", "/kb/presign", token, { name, contentType });

export const deleteKbDoc = (token: string, key: string) =>
  apiFetch<{ deleted: boolean }>("DELETE", "/kb/docs", token, undefined, { key });

/** Buka isi dokumen KB (v3.5 — read/edit dari UI). */
export const getKbDocContent = (token: string, key: string) =>
  apiFetch<{ key: string; content: string; updated?: string }>("GET", "/kb/doc", token, undefined, { key });

/** Simpan hasil edit dokumen KB (v3.5) — re-index otomatis di sisi server. */
export const saveKbDocContent = (token: string, key: string, content: string) =>
  apiFetch<{ saved: boolean; key: string; ingestion?: string }>("POST", "/kb/doc", token, { key, content });

/** Daftar Skills Library terpasang (v3.5). */
export type MaaSkill = { name: string; folder: string; key: string; description?: string; size: number; updated?: string };
export const listSkills = (token: string) =>
  apiFetch<{ skills: MaaSkill[] }>("GET", "/skills/list", token);

/** Buka isi SKILL.md satu skill (v3.5). */
export const getSkillContent = (token: string, key: string) =>
  apiFetch<{ key: string; content: string; updated?: string }>("GET", "/skills/get", token, undefined, { key });

export const syncKb = (token: string) =>
  apiFetch<{ jobId: string; status: string }>("POST", "/kb/sync", token);

// ----- upload lampiran chat (v3.4) -----

export const presignChatUpload = (
  token: string,
  name: string,
  contentType: string,
  size: number
) => apiFetch<{ uploadUrl: string; key: string; headers: Record<string, string> }>("POST", "/uploads/presign", token, { name, contentType, size });

// ---------------- normalisasi payload (hardening tipe) ----------------

/** Pastikan nilai adalah array; parse bila string JSON (kompat data lama DDB). */
export function asArray<T>(v: unknown): T[] {
  if (Array.isArray(v)) return v as T[];
  if (typeof v === "string" && v.startsWith("[")) {
    try {
      const p = JSON.parse(v);
      return Array.isArray(p) ? (p as T[]) : [];
    } catch {
      return [];
    }
  }
  return [];
}

// ----- dokumentasi editable (v3.4) -----

export const listSiteDocs = (token: string) =>
  apiFetch<{ docs: { key: string; name: string; size: number; updated: string }[] }>("GET", "/docs/list", token);

export const getDocContent = (token: string, key: string) =>
  apiFetch<{ key: string; content: string; updated?: string }>("GET", "/docs/content", token, undefined, { key });

export const saveDocContent = (token: string, key: string, content: string) =>
  apiFetch<{ saved: boolean }>("POST", "/docs/content", token, { key, content });

// ----- profil & admin -----

export const getMe = (token: string) => apiFetch<MeInfo>("GET", "/me", token);

export const adminListUsers = (token: string) =>
  apiFetch<{ users: AdminUser[] }>("GET", "/admin/users", token);

export const adminInviteUser = (token: string, email: string, role: "user" | "superadmin") =>
  apiFetch<{ username: string; tempPasswordSent: boolean }>("POST", "/admin/users", token, { email, role });

export const adminSetUserStatus = (token: string, username: string, enabled: boolean) =>
  apiFetch<{ updated: boolean }>("POST", "/admin/users/status", token, { username, enabled });

export const adminSetPassword = (token: string, username: string, password: string) =>
  apiFetch<{ updated: boolean; note?: string }>("POST", "/admin/users/set-password", token, { username, password });

export const adminResendInvite = (token: string, username: string) =>
  apiFetch<{ resent: boolean }>("POST", "/admin/users/resend-invite", token, { username });

export const adminDeleteUser = (token: string, username: string) =>
  apiFetch<{ deleted: boolean }>("DELETE", "/admin/users", token, undefined, { username });

/** Management User v3.5: ganti nama tampilan (rename). */
export const adminRenameUser = (token: string, username: string, name: string) =>
  apiFetch<{ updated: boolean; username: string; name: string }>("POST", "/admin/users/rename", token, { username, name });

/** Management User v3.5: ganti role (user <-> superadmin). */
export const adminSetUserRole = (token: string, username: string, role: "user" | "superadmin") =>
  apiFetch<{ updated: boolean; username: string; role: string }>("POST", "/admin/users/role", token, { username, role });

export const signOutAll = (token: string) => apiFetch<{ signedOut: boolean }>("POST", "/admin/signout", token);

// ---------------- konektor (data source ala Claude AI) ----------------

export type ConnectorType =
  | "gdrive" | "onedrive" | "adls" | "gcs" | "bigquery" | "s3" | "sftp" | "api" | "mcp";

export type Connector = {
  connectorId: string;
  name: string;
  type: ConnectorType | string;
  owner?: string;
  config?: Record<string, unknown>;
  status?: "ok" | "failed" | "untested" | string;
  lastTestAt?: number;
  lastTestOk?: boolean;
  lastTestMsg?: string;
  createdAt?: number;
  updatedAt?: number;
};

export type ConnectorTestResult = { ok: boolean; message: string; detail: string };

export const listConnectors = (token: string) =>
  apiFetch<{ connectors: Connector[] }>("GET", "/connectors", token);

export const createConnector = (
  token: string, name: string, type: ConnectorType | string, config: Record<string, unknown>,
) => apiFetch<Connector>("POST", "/connectors", token, { name, type, config });

export const updateConnector = (
  token: string, connectorId: string, patch: { name?: string; config?: Record<string, unknown> },
) => apiFetch<Connector>("POST", "/connectors/update", token, { connectorId, ...patch });

export const deleteConnector = (token: string, connectorId: string) =>
  apiFetch<{ deleted: string }>("DELETE", "/connectors", token, undefined, { id: connectorId });

/** Test koneksi — connectorId utk konektor tersimpan; tanpa connectorId,
 *  config = { type, config } (form baru) -> dikirim top-level sesuai kontrak edge. */
export const testConnector = (
  token: string, connectorId?: string, config?: Record<string, unknown>,
) => {
  const body = connectorId
    ? { connectorId, ...(config ? { config } : {}) }
    : {
        type: (config as { type?: string } | undefined)?.type ?? "",
        config: (config as { config?: Record<string, unknown> } | undefined)?.config ?? {},
      };
  return apiFetch<ConnectorTestResult>("POST", "/connectors/test", token, body);
};

// ---------------- konektor OAuth popup (Google / Microsoft) ----------------

export type OAuthSettings = {
  redirectUri: string;
  google: { configured: boolean; clientId: string };
  microsoft: { configured: boolean; clientId: string };
};

export const getOAuthSettings = (token: string) =>
  apiFetch<OAuthSettings>("GET", "/connectors/oauth/settings", token);

export const saveOAuthSettings = (
  token: string, payload: { google?: { clientId?: string; clientSecret?: string }; microsoft?: { clientId?: string; clientSecret?: string; tenant?: string } },
) => apiFetch<{ saved: boolean }>("POST", "/connectors/oauth/settings", token, payload);

export const startOAuth = (token: string, type: ConnectorType | string) =>
  apiFetch<{ url: string; provider: string; redirectUri: string }>("GET", "/connectors/oauth/start", token, undefined, { type });

export const exchangeOAuth = (
  token: string, payload: { code: string; state: string; name?: string },
) =>
  apiFetch<{ connectorId: string; name: string; type: string; ok: boolean; message: string; detail: string }>(
    "POST", "/connectors/oauth/exchange", token, payload);

// ---------------- storage ----------------
const KEY = "maa.session";
const REMEMBER_KEY = "maa.remember";

export function saveSession(username: string, tokens: Tokens, remember = false) {
  const payload = JSON.stringify({ username, tokens, savedAt: Date.now() });
  sessionStorage.setItem(KEY, payload);
  try {
    if (remember) localStorage.setItem(REMEMBER_KEY, payload);
    else localStorage.removeItem(REMEMBER_KEY);
  } catch {
    /* abaikan */
  }
}
export function loadSession(): { username: string; tokens: Tokens } | null {
  const parse = (raw: string | null) => {
    try {
      if (!raw) return null;
      const s = JSON.parse(raw);
      if (!s?.tokens?.IdToken) return null;
      return s as { username: string; tokens: Tokens };
    } catch {
      return null;
    }
  };
  const s = parse(sessionStorage.getItem(KEY)) || parse(localStorage.getItem(REMEMBER_KEY));
  if (s && sessionStorage.getItem(KEY) === null) {
    // hidupkan ulang tab: salin dari remember-me ke sessionStorage
    try {
      sessionStorage.setItem(KEY, localStorage.getItem(REMEMBER_KEY) || "");
    } catch {
      /* abaikan */
    }
  }
  return s;
}
export function clearSession() {
  sessionStorage.removeItem(KEY);
  try {
    localStorage.removeItem(REMEMBER_KEY);
  } catch {
    /* abaikan */
  }
}

/** Sesi terakhir per user (URL routing fallback saat login). */
export function saveLastSession(userId: string, sessionId: string) {
  try {
    localStorage.setItem(`maa.last.${userId}`, sessionId);
  } catch {
    /* abaikan */
  }
}
export function loadLastSession(userId: string): string | null {
  try {
    return localStorage.getItem(`maa.last.${userId}`);
  } catch {
    return null;
  }
}

/** Parse path "/c/<sessionId>" → id | null. */
export function sessionIdFromPath(pathname: string): string | null {
  const m = /^\/c\/([A-Za-z0-9_-]+)/.exec(pathname);
  return m ? m[1] : null;
}

// ---------------- util UI ----------------

/** Waktu relatif ringkas bahasa Indonesia: "2 mnt lalu", "3 jam lalu", "5 hr lalu". */
export function relTime(iso?: string | number): string {
  if (!iso) return "";
  const t = typeof iso === "number" ? iso : Date.parse(iso);
  if (!Number.isFinite(t)) return "";
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return "baru saja";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} mnt lalu`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} jam lalu`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d} hr lalu`;
  const w = Math.floor(d / 7);
  if (w < 5) return `${w} mgg lalu`;
  return new Date(t).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" });
}

export function fmtClock(ts: string | number): string {
  const n = typeof ts === "number" ? ts : Number(ts);
  if (!Number.isFinite(n) || n <= 0) return "";
  return new Date(n).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function fmtBytes(n: number): string {
  if (n > 1_048_576) return `${(n / 1_048_576).toFixed(1)} MB`;
  if (n > 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${n} B`;
}

/**
 * Strip blok klarifikasi terstruktur dari teks markdown:
 * `[[CLARIFY]]{...json...}` (fallback bila status.clarify tidak terisi).
 */
export function stripClarifyBlock(text: string): { text: string; clarify: Clarify | null } {
  const re = /\[\[CLARIFY\]\]\s*(\{[\s\S]*?\})\s*$/;
  const m = re.exec(text || "");
  if (!m) return { text: text || "", clarify: null };
  try {
    const j = JSON.parse(m[1]) as { question?: string; options?: string[] };
    return {
      text: text.replace(re, "").trimEnd(),
      clarify: {
        question: j.question || "Agent butuh kejelasan",
        options: Array.isArray(j.options) ? j.options.map(String) : [],
      },
    };
  } catch {
    return { text: text.replace(re, "").trimEnd(), clarify: null };
  }
}

// ---------------- trace meta (ikon di trace-panel.tsx) ----------------

export const TRACE_META: Record<string, { label: string; tint: string; dot: string }> = {
  user_msg:         { label: "Perintah Pengguna",        tint: "text-[var(--ink)]",            dot: "bg-zinc-500 dark:bg-zinc-400" },
  thinking:         { label: "Proses Berpikir",          tint: "text-amber-700 dark:text-amber-400",  dot: "bg-amber-500" },
  tool_call:        { label: "Eksekusi Tool",            tint: "text-emerald-700 dark:text-emerald-400", dot: "bg-emerald-500" },
  tool_result:      { label: "Hasil Tool",               tint: "text-teal-700 dark:text-teal-300",    dot: "bg-teal-500" },
  kb_search:        { label: "Pencarian Knowledge Base", tint: "text-cyan-700 dark:text-cyan-400",    dot: "bg-cyan-500" },
  web_search:       { label: "Pencarian Web",            tint: "text-sky-700 dark:text-sky-400",      dot: "bg-sky-500" },
  code_interpreter: { label: "Interpreter Kode",         tint: "text-violet-700 dark:text-violet-400", dot: "bg-violet-500" },
  image_gen:        { label: "Pembuatan Gambar",         tint: "text-pink-700 dark:text-pink-400",    dot: "bg-pink-500" },
  memory_recall:    { label: "Pengambilan Memori",       tint: "text-indigo-700 dark:text-indigo-400", dot: "bg-indigo-500" },
  clarify:          { label: "Minta Klarifikasi",        tint: "text-amber-700 dark:text-amber-400",  dot: "bg-amber-500" },
  iac:              { label: "Infrastructure as Code",   tint: "text-lime-700 dark:text-lime-400",    dot: "bg-lime-500" },
  task_plan:        { label: "Rencana Tugas (Todo)",     tint: "text-sky-700 dark:text-sky-400",      dot: "bg-sky-500" },
  subagent:         { label: "Multi-Agent Subagent",     tint: "text-fuchsia-700 dark:text-fuchsia-400", dot: "bg-fuchsia-500" },
  deck:             { label: "Slide Deck Dibuat",        tint: "text-violet-700 dark:text-violet-400", dot: "bg-violet-500" },
  webapp:           { label: "Web App Ter-deploy",       tint: "text-lime-700 dark:text-lime-400",    dot: "bg-lime-500" },
  upload:           { label: "Lampiran Diproses",        tint: "text-zinc-700 dark:text-zinc-400",    dot: "bg-zinc-500" },
  guardrail:        { label: "Guardrail Keamanan",       tint: "text-orange-700 dark:text-orange-400", dot: "bg-orange-500" },
  translate:        { label: "Terjemahan EN→ID",         tint: "text-cyan-700 dark:text-cyan-400",    dot: "bg-cyan-500" },
  confirm_required: { label: "Menunggu Konfirmasi Ganda", tint: "text-orange-700 dark:text-orange-400", dot: "bg-orange-500" },
  confirm_executed: { label: "Konfirmasi Dieksekusi",    tint: "text-emerald-700 dark:text-emerald-400", dot: "bg-emerald-500" },
  self_heal:        { label: "Self-Healing",             tint: "text-lime-700 dark:text-lime-400",    dot: "bg-lime-500" },
  error:            { label: "Error",                    tint: "text-rose-700 dark:text-rose-400",    dot: "bg-rose-500" },
  response:         { label: "Respons Final",            tint: "text-emerald-700 dark:text-emerald-300", dot: "bg-emerald-500" },
};

export const traceLabel = (t: string) => TRACE_META[t]?.label ?? t;
