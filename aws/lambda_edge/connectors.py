#!/usr/bin/env python3
"""MAA Connector — engine koneksi data source (dipakai edge Lambda + agent runtime).

Tipe didukung:
  gdrive   - Google Drive (OAuth access token / refresh token)
  onedrive - Microsoft OneDrive via Graph (OAuth access token / refresh token)
  adls     - Azure Data Lake Storage Gen2 (SAS token / storage account key)
  sftp     - SFTP (password / private key) via paramiko (opsional)
  api      - REST API manual (method, url, headers, body, expectStatus)
  mcp      - MCP server (Streamable HTTP JSON-RPC: initialize)

Semua fungsi bersifat murni stdlib (+paramiko opsional) agar identik bisa
dipakai di edge Lambda (test connection) dan di agent runtime (browse/read).
"""
import base64
import email.utils
import hashlib
import hmac
import io
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
import uuid as _uuid

TIMEOUT = 15
USER_AGENT = "MAA-Agent-Connector/1.0"

CONNECTOR_TYPES = ("gdrive", "onedrive", "adls", "sftp", "api", "mcp")

TYPE_LABEL = {
    "gdrive": "Google Drive",
    "onedrive": "OneDrive (Microsoft Graph)",
    "adls": "ADLS Gen2 (Azure)",
    "sftp": "SFTP",
    "api": "REST API Manual",
    "mcp": "MCP Server",
}

# field config yang dianggap rahasia -> dimask saat dikirim balik ke UI
SECRET_KEYS = {
    "accessToken", "refreshToken", "clientSecret", "password", "privateKey",
    "sasToken", "accountKey", "apiKey", "api_key", "token",
}


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


# ------------------------------------------------------------------ dispatcher

def test_connection(ctype, cfg):
    """Test koneksi -> (ok, message, detail). Tidak pernah raise."""
    try:
        fn = {"gdrive": gdrive_test, "onedrive": onedrive_test, "adls": adls_test,
              "sftp": sftp_test, "api": api_test, "mcp": mcp_test}.get(ctype)
        if fn is None:
            return False, f"tipe konektor '{ctype}' tidak dikenal", ""
        return fn(cfg or {})
    except ValueError as e:
        return False, str(e), ""
    except Exception as e:  # jangan pernah bikin API 500 krn test gagal
        return False, f"error tak terduga: {str(e)[:200]}", ""


def connector_list_files(ctype, cfg, path="", limit=25):
    fn = {"gdrive": lambda: gdrive_list(cfg, limit=limit),
          "onedrive": lambda: onedrive_list(cfg, path, limit),
          "adls": lambda: adls_list(cfg, path, limit),
          "sftp": lambda: sftp_list(cfg, path, limit)}.get(ctype)
    if fn:
        return fn()
    if ctype == "api":
        raise ValueError("konektor API manual tidak punya operasi list — gunakan read")
    if ctype == "mcp":
        return mcp_tools(cfg)
    raise ValueError(f"list tidak didukung utk tipe {ctype}")


def connector_read(ctype, cfg, path, limit=262144):
    fn = {"gdrive": lambda: gdrive_read(cfg, path, limit),
          "onedrive": lambda: onedrive_read(cfg, path, limit),
          "adls": lambda: adls_read(cfg, path, limit),
          "sftp": lambda: sftp_read(cfg, path, limit)}.get(ctype)
    if fn:
        return fn()
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
