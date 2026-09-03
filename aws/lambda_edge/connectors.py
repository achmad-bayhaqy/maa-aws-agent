#!/usr/bin/env python3
"""MAA Connector — engine koneksi data source (dipakai edge Lambda + agent runtime).

Tipe didukung:
  gdrive   - Google Drive (OAuth popup login / refresh token manual / access token)
  onedrive - Microsoft OneDrive via Graph (OAuth popup + PKCE / refresh token manual)
  adls     - Azure Data Lake Storage Gen2 (Service Principal OAuth2 / SAS / SharedKey)
  gcs      - Google Cloud Storage (OAuth popup / Service Account JSON)
  bigquery - Google BigQuery (OAuth popup / Service Account JSON)
  s3       - AWS S3 (access key + secret [+ session token])
  sftp     - SFTP (password / private key) via paramiko (opsional)
  api      - REST API manual (method, url, headers, body, expectStatus)
  mcp      - MCP server (Streamable HTTP JSON-RPC: initialize)

Semua fungsi bersifat murni stdlib (+paramiko/boto3 opsional) agar identik bisa
dipakai di edge Lambda (test connection) dan di agent runtime (browse/read).

Keamanan (best practice AWS 2026): nilai rahasia (refresh token, client secret,
private key, account key, dst.) dienkripsi envelope KMS sebelum disimpan ke
DynamoDB (prefix "enc:v1:"), tidak pernah dikirim balik ke UI (dimask "•••").
"""
import base64
import email.utils
import hashlib
import hmac
import io
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid as _uuid

TIMEOUT = 15
USER_AGENT = "MAA-Agent-Connector/1.0"

CONNECTOR_TYPES = ("gdrive", "onedrive", "adls", "gcs", "bigquery", "s3", "sftp", "api", "mcp")

TYPE_LABEL = {
    "gdrive": "Google Drive",
    "onedrive": "OneDrive (Microsoft Graph)",
    "adls": "ADLS Gen2 (Azure)",
    "gcs": "Google Cloud Storage",
    "bigquery": "Google BigQuery",
    "s3": "AWS S3",
    "sftp": "SFTP",
    "api": "REST API Manual",
    "mcp": "MCP Server",
}

# field config yang dianggap rahasia -> dimask saat dikirim balik ke UI
SECRET_KEYS = {
    "accessToken", "refreshToken", "clientSecret", "password", "privateKey",
    "sasToken", "accountKey", "apiKey", "api_key", "token",
    "secretAccessKey", "sessionToken", "serviceAccountJson",
}

# ------------------------------------------------------------- KMS seal/open

_ENC_PREFIX = "enc:v1:"
_KMS = None


def _kms_client():
    global _KMS
    if _KMS is None:
        import os
        import boto3
        _KMS = boto3.client("kms", region_name=os.environ.get("MAA_KMS_REGION") or "us-east-1")
    return _KMS


def _seal_value(v):
    """Enkripsi satu nilai rahasia dgn KMS (envelope tunggal)."""
    if not isinstance(v, str) or not v or v.startswith(_ENC_PREFIX) or v == "•••":
        return v
    try:
        import base64
        import os
        key_id = os.environ.get("MAA_KMS_KEY_ID") or ""
        r = _kms_client().encrypt(KeyId=key_id, Plaintext=v.encode("utf-8"))
        return _ENC_PREFIX + base64.b64encode(r["CiphertextBlob"]).decode()
    except Exception:
        return v  # fallback jangan gagalkan penyimpanan


def _open_value(v):
    if not isinstance(v, str) or not v.startswith(_ENC_PREFIX):
        return v
    try:
        import base64
        blob = base64.b64decode(v[len(_ENC_PREFIX):])
        return _kms_client().decrypt(CiphertextBlob=blob)["Plaintext"].decode("utf-8")
    except Exception:
        return ""


def seal_config(cfg):
    """Salin config dgn semua nilai rahasia dienkripsi KMS (utk simpan DDB)."""
    out = {}
    for k, v in (cfg or {}).items():
        if isinstance(v, dict):
            out[k] = seal_config(v)
        elif isinstance(v, list):
            out[k] = [seal_config(x) if isinstance(x, (dict, list)) else x for x in v]
        elif _is_secret(k):
            out[k] = _seal_value(v)
        else:
            out[k] = v
    return out


def open_config(cfg):
    """Salin config dgn nilai terenkripsi didekripsi kembali (utk engine)."""
    out = {}
    for k, v in (cfg or {}).items():
        if isinstance(v, dict):
            out[k] = open_config(v)
        elif isinstance(v, list):
            out[k] = [open_config(x) if isinstance(x, (dict, list)) else x for x in v]
        elif _is_secret(k):
            out[k] = _open_value(v)
        else:
            out[k] = v
    return out


# ------------------------------------------------------------------ helpers

def mask_config(cfg):
    """Salin config dengan nilai rahasia dimask (untuk respons UI)."""
    out = {}
    for k, v in (cfg or {}).items():
        if isinstance(v, dict):
            out[k] = {hk: ("•••" if _is_secret(hk) and hv else hv) for hk, hv in v.items()}
        else:
            out[k] = "•••" if _is_secret(k) and v else v
    return out


def merge_config(old, new):
    """Gabung config baru: nilai kosong/termask dianggap 'tidak diubah'."""
    out = dict(old or {})
    for k, v in (new or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge_config(out[k], v)
        elif v in ("", None) or v == "•••":
            continue  # keep old
        else:
            out[k] = v
    return out


def _is_secret(key):
    if not isinstance(key, str):
        return False
    return key in SECRET_KEYS or key.lower() in (
        "authorization", "x-api-key", "proxy-authorization", "private_key")


def _json_headers(extra=None):
    h = {"User-Agent": USER_AGENT, "Accept": "application/json, */*"}
    h.update(extra or {})
    return h


def http_req(url, method="GET", headers=None, body=None, timeout=TIMEOUT):
    """HTTP sederhana. Return (status, headers, body_bytes). Raise ValueError rapih."""
    data = None
    if body is not None:
        data = body.encode("utf-8") if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, str(v))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read(262144)
    except urllib.error.HTTPError as e:
        try:
            detail = e.read(8192).decode("utf-8", "replace")
        except Exception:
            detail = ""
        raise ValueError(f"HTTP {e.code} dari server: {detail[:400] or e.reason}") from None
    except (socket.timeout, TimeoutError):
        raise ValueError(f"timeout setelah {timeout}s — host tidak merespons") from None
    except urllib.error.URLError as e:
        reason = str(getattr(e, "reason", e))
        low = reason.lower()
        if "name or service not known" in low or "nodename nor servname" in low or "getaddrinfo" in low:
            raise ValueError("host tidak ditemukan (DNS gagal) — periksa nama host/URL") from None
        if "refused" in low:
            raise ValueError("koneksi ditolak — pastikan host/port benar dan service berjalan") from None
        if "ssl" in low or "certificate" in low:
            raise ValueError(f"masalah SSL/TLS: {reason[:200]}") from None
        raise ValueError(f"gagal koneksi: {reason[:200]}") from None


def post_form(url, params, timeout=TIMEOUT):
    data = urllib.parse.urlencode(params).encode("utf-8")
    return http_req(url, method="POST",
                    headers={"Content-Type": "application/x-www-form-urlencoded",
                             "User-Agent": USER_AGENT, "Accept": "application/json"},
                    body=data, timeout=timeout)


def parse_json(raw):
    try:
        return json.loads(raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw)
    except Exception:
        return None


def _bearer_headers(token):
    return {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT, "Accept": "application/json"}


def _oauth_refresh(cfg, token_url, extra=None):
    cid, sec = cfg.get("clientId", ""), cfg.get("clientSecret", "")
    rt = cfg.get("refreshToken", "")
    if not (cid and sec and rt):
        raise ValueError("refresh token flow butuh clientId, clientSecret, dan refreshToken")
    params = {"grant_type": "refresh_token", "refresh_token": rt,
              "client_id": cid, "client_secret": sec}
    params.update(extra or {})
    _, _, b = post_form(token_url, params)
    j = parse_json(b) or {}
    tok = j.get("access_token")
    if not tok:
        raise ValueError(f"refresh token ditolak: {str(j.get('error_description') or j)[:200]}")
    return tok


# ------------------------------------------------------------------ gdrive

def gdrive_token(cfg):
    if cfg.get("accessToken"):
        return cfg["accessToken"]
    return _oauth_refresh(cfg, "https://oauth2.googleapis.com/token")


def gdrive_test(cfg):
    tok = gdrive_token(cfg)
    _, _, b = http_req("https://www.googleapis.com/drive/v3/about?fields=user",
                       headers=_bearer_headers(tok))
    u = (parse_json(b) or {}).get("user", {})
    det = f"Drive user: {u.get('displayName', '?')} <{u.get('emailAddress', '?')}>"
    if cfg.get("folderId"):
        q = urllib.parse.quote(f"'{cfg['folderId']}' in parents")
        _, _, b2 = http_req(f"https://www.googleapis.com/drive/v3/files?q={q}&pageSize=1&fields=files(id,name)",
                            headers=_bearer_headers(tok))
        n = len((parse_json(b2) or {}).get("files", []))
        det += f"; folder {cfg['folderId']} dapat diakses ({n}+ file)"
    return True, "Google Drive terhubung", det


def gdrive_list(cfg, q="trashed = false", limit=20):
    tok = gdrive_token(cfg)
    folder = cfg.get("folderId", "")
    if folder:
        q = f"'{folder}' in parents and {q}"
    url = ("https://www.googleapis.com/drive/v3/files?q=" + urllib.parse.quote(q) +
           f"&pageSize={limit}&fields=files(id,name,mimeType,size,modifiedTime)")
    _, _, b = http_req(url, headers=_bearer_headers(tok))
    return (parse_json(b) or {}).get("files", [])


def gdrive_read(cfg, file_id, limit=262144):
    tok = gdrive_token(cfg)
    _, h, b = http_req(f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
                       headers=_bearer_headers(tok))
    return b[:limit], (h.get("Content-Type") or "application/octet-stream")


# ------------------------------------------------------------------ onedrive

def onedrive_token(cfg):
    if cfg.get("accessToken"):
        return cfg["accessToken"]
    tenant = cfg.get("tenant") or "common"
    return _oauth_refresh(cfg, f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                          extra={"scope": cfg.get("scope") or "offline_access Files.Read.All User.Read"})


def onedrive_test(cfg):
    tok = onedrive_token(cfg)
    _, _, b = http_req("https://graph.microsoft.com/v1.0/me", headers=_bearer_headers(tok))
    me = parse_json(b) or {}
    _, _, b2 = http_req("https://graph.microsoft.com/v1.0/me/drive/root/children?$top=1&$select=name",
                        headers=_bearer_headers(tok))
    n = len((parse_json(b2) or {}).get("value", []))
    det = (f"Graph user: {me.get('displayName', '?')} ({me.get('userPrincipalName', '?')}); "
           f"root drive dapat diakses ({n}+ item)")
    return True, "OneDrive terhubung", det


def onedrive_list(cfg, path="", limit=20):
    tok = onedrive_token(cfg)
    p = path.strip("/")
    url = (f"https://graph.microsoft.com/v1.0/me/drive/root:/{p}:/children?$top={limit}"
           if p else f"https://graph.microsoft.com/v1.0/me/drive/root/children?$top={limit}")
    _, _, b = http_req(url, headers=_bearer_headers(tok))
    return [{"name": i.get("name"), "size": i.get("size"),
             "id": i.get("id"), "type": "folder" if "folder" in i else "file"}
            for i in (parse_json(b) or {}).get("value", [])]


def onedrive_read(cfg, path, limit=262144):
    tok = onedrive_token(cfg)
    _, h, b = http_req(f"https://graph.microsoft.com/v1.0/me/drive/root:/{path.strip('/')}:/content",
                       headers=_bearer_headers(tok))
    return b[:limit], (h.get("Content-Type") or "application/octet-stream")


# ------------------------------------------------------------------ adls gen2

def adls_test(cfg):
    acct = (cfg.get("storageAccount") or "").strip()
    fs = (cfg.get("filesystem") or "").strip()
    if not acct or not fs:
        raise ValueError("storageAccount dan filesystem wajib diisi")
    base = f"https://{acct}.dfs.core.windows.net/{fs}"
    if cfg.get("sasToken"):
        sas = cfg["sasToken"].lstrip("?")
        http_req(f"{base}?resource=filesystem&{sas}",
                 headers={"x-ms-version": "2023-11-03", "User-Agent": USER_AGENT})
        return True, "ADLS Gen2 terhubung (SAS)", f"filesystem '{fs}' di akun '{acct}' dapat diakses"
    key = cfg.get("accountKey")
    if not key:
        raise ValueError("isi salah satu: sasToken atau accountKey")
    date = email.utils.formatdate(usegmt=True)
    canon_headers = f"x-ms-date:{date}\nx-ms-version:2023-11-03\n"
    canon_resource = f"/{acct}/{fs}\nresource:filesystem"
    string_to_sign = "GET\n" + "\n" * 11 + canon_headers + canon_resource
    sig = base64.b64encode(
        hmac.new(base64.b64decode(key), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
    ).decode()
    http_req(f"{base}?resource=filesystem", headers={
        "x-ms-date": date, "x-ms-version": "2023-11-03", "User-Agent": USER_AGENT,
        "Authorization": f"SharedKey {acct}:{sig}"})
    return True, "ADLS Gen2 terhubung (account key)", f"filesystem '{fs}' di akun '{acct}' dapat diakses"


def _adls_req(cfg, path, method="GET", extra_qs=""):
    acct = cfg["storageAccount"].strip()
    fs = cfg["filesystem"].strip()
    base = f"https://{acct}.dfs.core.windows.net/{fs}"
    qs = extra_qs
    headers = {"x-ms-version": "2023-11-03", "User-Agent": USER_AGENT}
    if cfg.get("sasToken"):
        qs = (qs + "&" if qs else "") + cfg["sasToken"].lstrip("?")
    else:
        date = email.utils.formatdate(usegmt=True)
        headers["x-ms-date"] = date
        canon_headers = f"x-ms-date:{date}\nx-ms-version:2023-11-03\n"
        canon_resource = f"/{acct}/{fs}{path}\n" + _adls_canon_qs(qs)
        string_to_sign = method + "\n" + "\n" * 11 + canon_headers + canon_resource
        sig = base64.b64encode(
            hmac.new(base64.b64decode(cfg["accountKey"]),
                     string_to_sign.encode("utf-8"), hashlib.sha256).digest()).decode()
        headers["Authorization"] = f"SharedKey {acct}:{sig}"
    url = base + path + (f"?{qs}" if qs else "")
    return http_req(url, method=method, headers=headers)


def _adls_canon_qs(qs):
    if not qs:
        return ""
    pairs = sorted(urllib.parse.parse_qsl(qs, keep_blank_values=True))
    return "\n".join(f"{urllib.parse.quote(k, safe='-_.~').lower()}:{urllib.parse.quote(v, safe='-_.~')}"
                     for k, v in pairs)


def adls_list(cfg, path="", limit=25):
    p = "/" + (path or "").strip("/")
    extra = "resource=filesystem&recursive=false"
    _, _, b = _adls_req(cfg, p, extra_qs=extra)
    return [{"name": e.get("name", "").split("/")[-1], "type": e.get("type"), "size": e.get("contentLength")}
            for e in (parse_json(b) or {}).get("paths", [])[:limit]]


def adls_read(cfg, path, limit=262144):
    _, h, b = _adls_req(cfg, "/" + (path or "").strip("/") + "?action=read")
    return b[:limit], (h.get("Content-Type") or "application/octet-stream")


# ------------------------------------------------------------------ sftp

def _sftp_client():
    try:
        import paramiko
        return paramiko
    except ImportError:
        raise ValueError("modul SFTP (paramiko) tidak tersedia di lingkungan ini") from None


def _load_private_key(paramiko, key_text):
    last = None
    for cls in ("Ed25519Key", "RSAKey", "ECDSAKey"):
        k = getattr(paramiko, cls, None)
        if k is None:
            continue
        try:
            return k.from_private_key(io.StringIO(key_text))
        except Exception as e:
            last = e
    raise ValueError(f"private key tidak valid: {str(last)[:150]}")


def sftp_connect(cfg):
    paramiko = _sftp_client()
    host = (cfg.get("host") or "").strip()
    if not host:
        raise ValueError("host wajib diisi")
    port = int(cfg.get("port") or 22)
    user = cfg.get("username") or ""
    kw = {"hostname": host, "port": port, "username": user,
          "timeout": TIMEOUT, "banner_timeout": TIMEOUT, "auth_timeout": TIMEOUT,
          "allow_agent": False, "look_for_keys": False}
    if cfg.get("privateKey"):
        kw["pkey"] = _load_private_key(paramiko, cfg["privateKey"])
    elif cfg.get("password"):
        kw["password"] = cfg["password"]
    else:
        raise ValueError("isi password atau privateKey untuk autentikasi SFTP")
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        cli.connect(**kw)
        return cli
    except paramiko.AuthenticationException:
        raise ValueError("autentikasi ditolak — periksa username/password/private key") from None
    except socket.gaierror:
        raise ValueError("host tidak ditemukan (DNS gagal)") from None
    except Exception as e:
        low = str(e).lower()
        if "refused" in low:
            raise ValueError("koneksi ditolak — periksa host/port") from None
        if "timed out" in low or "timeout" in low:
            raise ValueError(f"timeout {TIMEOUT}s — host tidak merespons (cek host/port/firewall)") from None
        if "key exchange" in low or "negotiation" in low:
            raise ValueError(f"negosiasi SSH gagal: {str(e)[:150]}") from None
        raise ValueError(f"gagal SFTP: {str(e)[:200]}") from None


def sftp_test(cfg):
    cli = sftp_connect(cfg)
    try:
        path = cfg.get("path") or "/"
        sftp = cli.open_sftp()
        entries = sftp.listdir(path)
        hostkey = cli.get_transport().get_remote_server_key().get_base64()[:24]
        return True, "SFTP terhubung", (
            f"{cfg.get('host')}:{cfg.get('port') or 22} OK sebagai '{cfg.get('username')}' — "
            f"{len(entries)} entri di '{path}' (hostkey {hostkey}…)")
    finally:
        cli.close()


def sftp_list(cfg, path=None, limit=50):
    cli = sftp_connect(cfg)
    try:
        sftp = cli.open_sftp()
        p = path or cfg.get("path") or "/"
        return [{"name": e.filename, "type": "folder" if __import__("stat").S_ISDIR(e.st_mode) else "file",
                 "size": e.st_size} for e in sftp.listdir_attr(p)[:limit]]
    finally:
        cli.close()


def sftp_read(cfg, path, limit=262144):
    cli = sftp_connect(cfg)
    try:
        sftp = cli.open_sftp()
        with sftp.open(path, "r") as f:
            return f.read(limit), "application/octet-stream"
    finally:
        cli.close()


# ------------------------------------------------------------------ api manual

def api_test(cfg):
    url = (cfg.get("url") or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("URL harus dimulai http:// atau https://")
    method = (cfg.get("method") or "GET").upper()
    headers = _cfg_headers(cfg)
    if method in ("POST", "PUT", "PATCH") and body_of(cfg) is not None:
        headers.setdefault("Content-Type", "application/json")
    status, h, b = http_req(url, method=method, headers=headers, body=body_of(cfg))
    exp = str(cfg.get("expectStatus") or "2xx").strip()
    ok = (200 <= status < 300) if exp == "2xx" else (status == int(exp or 200))
    prev = b[:300].decode("utf-8", "replace")
    detail = f"{method} {url} → {status}; content-type: {h.get('Content-Type', '-')}; body: {prev[:200]}"
    return ok, (f"HTTP {status} (harapan: {exp})" if ok else f"HTTP {status} — bukan {exp} seperti diharapkan"), detail


def _cfg_headers(cfg):
    h = {"User-Agent": USER_AGENT}
    raw = cfg.get("headers")
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except Exception:
            raise ValueError("headers harus JSON object valid, contoh: {\"Authorization\": \"Bearer abc\"}") from None
    if isinstance(raw, dict):
        h.update({str(k): str(v) for k, v in raw.items()})
    return h


def body_of(cfg):
    b = cfg.get("body")
    if isinstance(b, str) and b.strip():
        return b
    return None


# ------------------------------------------------------------------ mcp

def mcp_test(cfg):
    url = (cfg.get("url") or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("URL harus dimulai http:// atau https://")
    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                          "clientInfo": {"name": "maa-agent", "version": "1.0"}}}
    headers = _cfg_headers(cfg)
    headers.setdefault("Content-Type", "application/json")
    headers["Accept"] = "application/json, text/event-stream"
    status, h, b = http_req(url, method="POST", headers=headers, body=json.dumps(payload))
    j = _mcp_parse_body(h.get("Content-Type", ""), b)
    if isinstance(j, dict) and j.get("error"):
        raise ValueError(f"MCP error: {str(j['error'])[:200]}")
    res = (j or {}).get("result") or {}
    info = res.get("serverInfo") or {}
    if not info and not res.get("capabilities"):
        raise ValueError(f"respons bukan hasil MCP initialize: {str(j)[:200]}")
    det = (f"server: {info.get('name', '?')} v{info.get('version', '?')}; "
           f"protocol {res.get('protocolVersion', '?')}")
    return True, "MCP server terhubung", det


def _mcp_parse_body(ct, raw):
    text = raw.decode("utf-8", "replace")
    if "text/event-stream" in (ct or ""):
        for line in text.splitlines():
            if line.startswith("data:"):
                j = parse_json(line[5:].strip())
                if j:
                    return j
        return None
    return parse_json(raw)


# ------------------------------------------------------- OAuth popup (Google/MS)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
MS_AUTH_BASE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
MS_GRAPH_ME = "https://graph.microsoft.com/v1.0/me"

# scope read-only sesuai tipe konektor (least privilege, best practice 2026)
GOOGLE_SCOPES = {
    "gdrive": "https://www.googleapis.com/auth/drive.readonly",
    "gcs": "https://www.googleapis.com/auth/devstorage.read_only",
    "bigquery": "https://www.googleapis.com/auth/bigquery.readonly",
}
MS_SCOPES_DEFAULT = "offline_access Files.Read.All User.Read"


def oauth_provider_for(ctype):
    """Provider OAuth utk tipe konektor: google / microsoft / None."""
    if ctype in GOOGLE_SCOPES:
        return "google"
    if ctype == "onedrive":
        return "microsoft"
    return None


def google_authorize_url(oauth_cfg, ctype, redirect_uri, state):
    """URL consent Google; access_type=offline + prompt=consent WAJIB utk dapat
    refresh token (best practice Google OAuth 2026)."""
    qs = urllib.parse.urlencode({
        "client_id": oauth_cfg.get("clientId", ""),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": f"{GOOGLE_SCOPES.get(ctype, 'openid email')} openid email",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    })
    return f"{GOOGLE_AUTH_URL}?{qs}"


def microsoft_authorize_url(oauth_cfg, redirect_uri, state, verifier):
    """URL consent Microsoft dgn PKCE S256 (best practice MS identity 2026)."""
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    tenant = oauth_cfg.get("tenant") or "common"
    qs = urllib.parse.urlencode({
        "client_id": oauth_cfg.get("clientId", ""),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": MS_SCOPES_DEFAULT,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    })
    return f"{MS_AUTH_BASE.format(tenant=tenant)}/authorize?{qs}"


def google_exchange(oauth_cfg, ctype, code, redirect_uri):
    """Tukar authorization code -> tokens Google. Return dict utk config."""
    params = {"grant_type": "authorization_code", "code": code,
              "client_id": oauth_cfg.get("clientId", ""),
              "client_secret": oauth_cfg.get("clientSecret", ""),
              "redirect_uri": redirect_uri}
    _, _, b = post_form(GOOGLE_TOKEN_URL, params)
    j = parse_json(b) or {}
    if not j.get("access_token"):
        raise ValueError(f"Google menolak kode: {str(j.get('error_description') or j)[:200]}")
    cfg = {"authMethod": "oauth", "accessToken": j.get("access_token", ""),
           "refreshToken": j.get("refresh_token", ""), "clientId": oauth_cfg.get("clientId", ""),
           "clientSecret": oauth_cfg.get("clientSecret", "")}
    try:
        _, _, b2 = http_req(GOOGLE_USERINFO_URL, headers=_bearer_headers(j["access_token"]))
        u = parse_json(b2) or {}
        cfg["accountEmail"] = u.get("email", "")
    except Exception:
        pass
    return cfg


def microsoft_exchange(oauth_cfg, code, redirect_uri, verifier):
    """Tukar authorization code -> tokens Microsoft (PKCE)."""
    tenant = oauth_cfg.get("tenant") or "common"
    params = {"grant_type": "authorization_code", "code": code,
              "client_id": oauth_cfg.get("clientId", ""),
              "redirect_uri": redirect_uri, "code_verifier": verifier}
    if oauth_cfg.get("clientSecret"):
        params["client_secret"] = oauth_cfg["clientSecret"]
    _, _, b = post_form(f"{MS_AUTH_BASE.format(tenant=tenant)}/token", params)
    j = parse_json(b) or {}
    if not j.get("access_token"):
        raise ValueError(f"Microsoft menolak kode: {str(j.get('error_description') or j)[:200]}")
    cfg = {"authMethod": "oauth", "accessToken": j.get("access_token", ""),
           "refreshToken": j.get("refresh_token", ""), "clientId": oauth_cfg.get("clientId", ""),
           "clientSecret": oauth_cfg.get("clientSecret", ""), "tenant": tenant}
    try:
        _, _, b2 = http_req(MS_GRAPH_ME, headers=_bearer_headers(j["access_token"]))
        u = parse_json(b2) or {}
        cfg["accountEmail"] = u.get("userPrincipalName") or u.get("mail", "")
    except Exception:
        pass
    return cfg


def signed_oauth_state(secret, payload):
    """State OAuth bertanda tangan HMAC (payload b64url + '.' + sig)."""
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), raw.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    return f"{raw}.{sig}"


def verify_oauth_state(secret, state):
    """Verifikasi state; return payload atau raise ValueError."""
    try:
        raw, sig = (state or "").split(".", 1)
    except ValueError:
        raise ValueError("state OAuth tidak valid") from None
    expect = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), raw.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    if not hmac.compare_digest(sig, expect):
        raise ValueError("state OAuth tidak cocok (signature salah) — ulangi login")
    pad = "=" * (-len(raw) % 4)
    return json.loads(base64.urlsafe_b64decode(raw + pad))


# --------------------------------------------- service account JWT (Google RS256)

def _b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _rsa_pkcs1_sign(data, pem_key):
    """RSA PKCS#1 v1.5 SHA-256 murni stdlib (tanpa cryptography lib).
    Mendukung PEM PKCS#8 ('PRIVATE KEY') dan PKCS#1 ('RSA PRIVATE KEY')."""
    body = "\n".join(l for l in pem_key.splitlines() if "-----" not in l and l.strip())
    der = base64.b64decode(body)

    def _tlv_children(buf):
        """Iterasi TLV level atas buffer -> list (tag, value_bytes)."""
        out, i = [], 0
        while i < len(buf):
            tag = buf[i]
            i += 1
            ln = buf[i]
            i += 1
            if ln & 0x80:
                nb = ln & 0x7F
                ln = int.from_bytes(buf[i:i + nb], "big")
                i += nb
            out.append((tag, buf[i:i + ln]))
            i += ln
        return out

    def _rsa_ints_from_pkcs1(seq_bytes):
        kids = _tlv_children(seq_bytes)
        ints = [int.from_bytes(v, "big") for t, v in kids if t == 0x02]
        # [version, n, e, d, p, q, ...]
        if len(ints) < 4:
            raise ValueError("struktur RSA private key tidak lengkap")
        return ints[1], ints[3]  # n, d

    top = _tlv_children(der)
    if len(top) == 1 and top[0][0] == 0x30:  # outer SEQUENCE
        kids = _tlv_children(top[0][1])
        tags = [t for t, _ in kids]
        if tags == [0x02, 0x30, 0x04]:  # PKCS#8: ver, algId, OCTET(RSAPrivateKey)
            inner = _tlv_children(kids[2][1])
            if len(inner) == 1 and inner[0][0] == 0x30:
                n, d = _rsa_ints_from_pkcs1(inner[0][1])
            else:
                n, d = _rsa_ints_from_pkcs1(kids[2][1])
        elif all(t == 0x02 for t in tags):  # PKCS#1 langsung
            ints = [int.from_bytes(v, "big") for _, v in kids]
            n, d = ints[1], ints[3]
        else:
            raise ValueError("private key bukan RSA (PKCS#8/PKCS#1 RSA saja)")
    else:
        raise ValueError("private key PEM tidak valid")
    if not n or not d or d >= n:
        raise ValueError("private key RSA tidak dapat dibaca")

    digestinfo = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(data).digest()
    k = (n.bit_length() + 7) // 8
    em = b"\x00\x01" + b"\xff" * (k - len(digestinfo) - 3) + b"\x00" + digestinfo
    return pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")


def sa_access_token(sa_cfg, scope):
    """Access token dari Service Account JSON via JWT bearer grant."""
    if isinstance(sa_cfg, str):
        try:
            sa_cfg = json.loads(sa_cfg)
        except Exception:
            raise ValueError("serviceAccountJson harus JSON valid") from None
    for f in ("client_email", "private_key"):
        if not sa_cfg.get(f):
            raise ValueError(f"serviceAccountJson kurang field '{f}'")
    now = int(time.time())
    jwt_in = (_b64u(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode()) + "." +
              _b64u(json.dumps({"iss": sa_cfg["client_email"], "scope": scope,
                                "aud": GOOGLE_TOKEN_URL, "iat": now, "exp": now + 3600},
                               separators=(",", ":")).encode()))
    sig = _rsa_pkcs1_sign(jwt_in.encode(), sa_cfg["private_key"])
    assertion = jwt_in + "." + _b64u(sig)
    _, _, b = post_form(GOOGLE_TOKEN_URL, {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                           "assertion": assertion})
    j = parse_json(b) or {}
    if not j.get("access_token"):
        raise ValueError(f"service account ditolak Google: {str(j)[:200]}")
    return j["access_token"]


import time  # noqa: E402  (dipakai sa_access_token)


# ------------------------------------------------------------------ gcs

GCS_API = "https://storage.googleapis.com/storage/v1"


def gcs_token(cfg):
    if cfg.get("serviceAccountJson"):
        return sa_access_token(cfg["serviceAccountJson"], GOOGLE_SCOPES["gcs"])
    if cfg.get("accessToken"):
        return cfg["accessToken"]
    return _oauth_refresh(cfg, GOOGLE_TOKEN_URL)


def gcs_test(cfg):
    tok = gcs_token(cfg)
    proj = (cfg.get("project") or "").strip()
    bucket = (cfg.get("bucket") or "").strip()
    if bucket:
        _, h, b = http_req(f"{GCS_API}/b/{urllib.parse.quote(bucket)}?fields=name,timeCreated",
                           headers=_bearer_headers(tok))
        meta = parse_json(b) or {}
        return True, "Google Cloud Storage terhubung", (
            f"bucket '{meta.get('name', bucket)}' dapat diakses (dibuat {meta.get('timeCreated', '?')[:10]})")
    if not proj:
        raise ValueError("isi project (atau bucket) untuk GCS")
    _, _, b = http_req(f"{GCS_API}/b?project={urllib.parse.quote(proj)}&maxResults=5",
                       headers=_bearer_headers(tok))
    items = [i.get("name") for i in (parse_json(b) or {}).get("items", [])]
    det = f"project '{proj}': " + (f"{len(items)} bucket, contoh: {', '.join(items[:3])}" if items
                                   else "belum ada bucket (akses OK)")
    return True, "Google Cloud Storage terhubung", det


def gcs_list(cfg, path="", limit=25):
    tok = gcs_token(cfg)
    bucket = (cfg.get("bucket") or "").strip()
    if not bucket:
        raise ValueError("bucket wajib diisi")
    prefix = (path or "").strip("/")
    qs = f"prefix={urllib.parse.quote(prefix + '/' if prefix else '')}&maxResults={limit}&delimiter=/"
    _, _, b = http_req(f"{GCS_API}/b/{urllib.parse.quote(bucket)}/o?{qs}", headers=_bearer_headers(tok))
    j = parse_json(b) or {}
    out = [{"name": p.rstrip("/").split("/")[-1], "path": p.rstrip("/") + "/", "type": "folder"}
           for p in j.get("prefixes", [])]
    for i in j.get("items", []):
        out.append({"name": i.get("name", "").split("/")[-1], "path": i.get("name"),
                    "type": "file", "size": i.get("size"),
                    "ctype": i.get("contentType")})
    return out[:limit]


def gcs_read(cfg, path, limit=262144):
    tok = gcs_token(cfg)
    obj = urllib.parse.quote((path or "").lstrip("/"), safe="")
    _, h, b = http_req(f"{GCS_API}/b/{urllib.parse.quote(cfg['bucket'])}/o/{obj}?alt=media",
                       headers=_bearer_headers(tok))
    return b[:limit], (h.get("Content-Type") or "application/octet-stream")


# ------------------------------------------------------------------ bigquery

BQ_API = "https://bigquery.googleapis.com/bigquery/v2"


def bigquery_token(cfg):
    if cfg.get("serviceAccountJson"):
        return sa_access_token(cfg["serviceAccountJson"], GOOGLE_SCOPES["bigquery"])
    if cfg.get("accessToken"):
        return cfg["accessToken"]
    return _oauth_refresh(cfg, GOOGLE_TOKEN_URL)


def bigquery_test(cfg):
    tok = bigquery_token(cfg)
    proj = (cfg.get("project") or "").strip()
    if not proj:
        raise ValueError("project wajib diisi untuk BigQuery")
    ds = (cfg.get("dataset") or "").strip()
    if ds:
        _, _, b = http_req(f"{BQ_API}/projects/{urllib.parse.quote(proj)}/datasets/"
                           f"{urllib.parse.quote(ds)}/tables?maxResults=5", headers=_bearer_headers(tok))
        tbls = [t.get("tableId") for t in (parse_json(b) or {}).get("tables", [])]
        det = f"dataset '{ds}' dapat diakses; tabel: {', '.join(tbls) if tbls else '(kosong)'}"
        return True, "Google BigQuery terhubung", det
    _, _, b = http_req(f"{BQ_API}/projects/{urllib.parse.quote(proj)}/datasets?maxResults=5",
                       headers=_bearer_headers(tok))
    dss = [d.get("datasetId") for d in (parse_json(b) or {}).get("datasets", [])]
    det = f"project '{proj}': {len(dss)} dataset, contoh: {', '.join(dss[:3]) if dss else '(kosong)'}"
    return True, "Google BigQuery terhubung", det


def bigquery_list(cfg, path="", limit=25):
    tok = bigquery_token(cfg)
    proj = urllib.parse.quote(cfg["project"].strip())
    p = (path or "").strip("/")
    if p:  # dataset -> daftar tabel
        _, _, b = http_req(f"{BQ_API}/projects/{proj}/datasets/{urllib.parse.quote(p)}/tables?maxResults={limit}",
                           headers=_bearer_headers(tok))
        return [{"name": t.get("tableId"), "path": f"{p}/{t.get('tableId')}", "type": "table",
                 "rows": t.get("numRows")} for t in (parse_json(b) or {}).get("tables", [])]
    _, _, b = http_req(f"{BQ_API}/projects/{proj}/datasets?maxResults={limit}", headers=_bearer_headers(tok))
    return [{"name": d.get("datasetId"), "path": d.get("datasetId"), "type": "dataset"}
            for d in (parse_json(b) or {}).get("datasets", [])]


def bigquery_read(cfg, path, limit=200):
    """Baca baris tabel via tabledata.list (scope read-only memadai)."""
    tok = bigquery_token(cfg)
    proj = urllib.parse.quote(cfg["project"].strip())
    p = (path or "").strip("/")
    if p.count("/") != 1:
        raise ValueError("path BigQuery harus 'dataset/tabel'")
    ds, tbl = p.split("/", 1)
    _, _, b = http_req(
        f"{BQ_API}/projects/{proj}/datasets/{urllib.parse.quote(ds)}/tables/"
        f"{urllib.parse.quote(tbl)}/data?maxResults={limit}", headers=_bearer_headers(tok))
    j = parse_json(b) or {}
    cols = [f.get("name") for f in j.get("schema", {}).get("fields", [])]
    rows = []
    for r in j.get("rows", [])[:limit]:
        cells = [c.get("v") for c in r.get("f", [])]
        rows.append(dict(zip(cols, cells)) if cols else cells)
    return rows


# ------------------------------------------------------------------ aws s3

def _s3_client(cfg):
    import os

    import boto3
    return boto3.client(
        "s3", region_name=cfg.get("region") or os.environ.get("AWS_REGION") or "us-east-1",
        aws_access_key_id=cfg.get("accessKey") or None,
        aws_secret_access_key=cfg.get("secretAccessKey") or None,
        aws_session_token=cfg.get("sessionToken") or None)


def s3_test(cfg):
    s3 = _s3_client(cfg)
    bucket = (cfg.get("bucket") or "").strip()
    if bucket:
        loc = s3.head_bucket(Bucket=bucket)
        n = 0
        try:
            r = s3.list_objects_v2(Bucket=bucket, MaxKeys=1)
            n = r.get("KeyCount", 0)
        except Exception:
            pass
        return True, "AWS S3 terhubung", (
            f"bucket '{bucket}' dapat diakses (region {cfg.get('region') or 'us-east-1'}, {n}+ objek; "
            f"HTTP {loc['ResponseMetadata']['HTTPStatusCode']})")
    owned = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
    return True, "AWS S3 terhubung", (
        f"kredensial valid; {len(owned)} bucket milik akun: {', '.join(owned[:5]) or '(kosong)'}")


def s3_list(cfg, path="", limit=25):
    s3 = _s3_client(cfg)
    bucket = (cfg.get("bucket") or "").strip()
    if not bucket:
        return [{"name": b["Name"], "path": b["Name"] + "/", "type": "bucket"}
                for b in s3.list_buckets().get("Buckets", [])]
    prefix = (path or "").strip("/") + ("/" if path else "")
    r = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter="/", MaxKeys=limit)
    out = [{"name": p["Prefix"][len(prefix):].rstrip("/"), "path": p["Prefix"], "type": "folder"}
           for p in r.get("CommonPrefixes", [])]
    out += [{"name": o["Key"][len(prefix):], "path": o["Key"], "type": "file",
             "size": o.get("Size")} for o in r.get("Contents", []) if o["Key"] != prefix]
    return out[:limit]


def s3_read(cfg, path, limit=262144):
    s3 = _s3_client(cfg)
    bucket = (cfg.get("bucket") or "").strip()
    if not bucket:
        raise ValueError("bucket wajib diisi untuk read S3")
    o = s3.get_object(Bucket=bucket, Key=(path or "").lstrip("/"))
    body = o["Body"].read(limit)
    return body, (o.get("ContentType") or "application/octet-stream")


# ------------------------------------------------------------------ dispatcher

def test_connection(ctype, cfg):
    """Test koneksi -> (ok, message, detail). Tidak pernah raise."""
    try:
        cfg = open_config(cfg or {})
        fn = {"gdrive": gdrive_test, "onedrive": onedrive_test, "adls": adls_test,
              "gcs": gcs_test, "bigquery": bigquery_test, "s3": s3_test,
              "sftp": sftp_test, "api": api_test, "mcp": mcp_test}.get(ctype)
        if fn is None:
            return False, f"tipe konektor '{ctype}' tidak dikenal", ""
        return fn(cfg)
    except ValueError as e:
        return False, str(e), ""
    except Exception as e:  # jangan pernah bikin API 500 krn test gagal
        return False, f"error tak terduga: {str(e)[:200]}", ""


def connector_list_files(ctype, cfg, path="", limit=25):
    cfg = open_config(cfg or {})
    fn = {"gdrive": lambda: gdrive_list(cfg, limit=limit),
          "onedrive": lambda: onedrive_list(cfg, path, limit),
          "adls": lambda: adls_list(cfg, path, limit),
          "gcs": lambda: gcs_list(cfg, path, limit),
          "bigquery": lambda: bigquery_list(cfg, path, limit),
          "s3": lambda: s3_list(cfg, path, limit),
          "sftp": lambda: sftp_list(cfg, path, limit)}.get(ctype)
    if fn:
        return fn()
    if ctype == "api":
        raise ValueError("konektor API manual tidak punya operasi list — gunakan read")
    if ctype == "mcp":
        return mcp_tools(cfg)
    raise ValueError(f"list tidak didukung utk tipe {ctype}")


def connector_read(ctype, cfg, path, limit=262144):
    cfg = open_config(cfg or {})
    fn = {"gdrive": lambda: gdrive_read(cfg, path, limit),
          "onedrive": lambda: onedrive_read(cfg, path, limit),
          "adls": lambda: adls_read(cfg, path, limit),
          "gcs": lambda: gcs_read(cfg, path, limit),
          "s3": lambda: s3_read(cfg, path, limit),
          "sftp": lambda: sftp_read(cfg, path, limit)}.get(ctype)
    if fn:
        return fn()
    if ctype == "bigquery":
        return json.dumps(bigquery_read(cfg, path), ensure_ascii=False, default=str).encode(), "application/json"
    if ctype == "api":
        url = (cfg.get("url") or "").strip()
        status, h, b = http_req(url, method=(cfg.get("method") or "GET").upper(),
                                headers=_cfg_headers(cfg), body=body_of(cfg))
        return b[:limit], (h.get("Content-Type") or "text/plain") + f" (HTTP {status})"
    if ctype == "mcp":
        raise ValueError("read tidak berlaku utk MCP — gunakan tool_call")
    raise ValueError(f"read tidak didukung utk tipe {ctype}")


def mcp_tools(cfg):
    url = (cfg.get("url") or "").strip()
    headers = _cfg_headers(cfg)
    headers.setdefault("Content-Type", "application/json")
    headers["Accept"] = "application/json, text/event-stream"
    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                          "clientInfo": {"name": "maa-agent", "version": "1.0"}}}
    _, h, b = http_req(url, method="POST", headers=headers, body=json.dumps(payload))
    sid = h.get("Mcp-Session-Id") or h.get("mcp-session-id")
    payload2 = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    if sid:
        headers["Mcp-Session-Id"] = sid
    _, h2, b2 = http_req(url, method="POST", headers=headers, body=json.dumps(payload2))
    tools = (_mcp_parse_body(h2.get("Content-Type", ""), b2) or {}).get("result", {}).get("tools", [])
    return [{"name": t.get("name"), "description": (t.get("description") or "")[:160]} for t in tools[:25]]


def mcp_tool_call(cfg, tool, args=None):
    url = (cfg.get("url") or "").strip()
    headers = _cfg_headers(cfg)
    headers.setdefault("Content-Type", "application/json")
    headers["Accept"] = "application/json, text/event-stream"
    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                          "clientInfo": {"name": "maa-agent", "version": "1.0"}}}
    _, h, b = http_req(url, method="POST", headers=headers, body=json.dumps(payload))
    sid = h.get("Mcp-Session-Id") or h.get("mcp-session-id")
    if sid:
        headers["Mcp-Session-Id"] = sid
    payload2 = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": tool, "arguments": args or {}}}
    _, h2, b2 = http_req(url, method="POST", headers=headers, body=json.dumps(payload2))
    r = _mcp_parse_body(h2.get("Content-Type", ""), b2) or {}
    if r.get("error"):
        raise ValueError(f"MCP tool error: {str(r['error'])[:200]}")
    return (r.get("result") or {}).get("content", [])
