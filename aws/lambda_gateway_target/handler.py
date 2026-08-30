#!/usr/bin/env python3
"""MAA AWS Agent - Gateway Target Lambda: tool web eksternal (Full Core v3).

Tool (via AgentCore Gateway MCP, inbound auth AWS_IAM):
- web_search  : pencarian web gratis via DuckDuckGo (2 mesin fallback).
- web_fetch   : ambil isi halaman; GET cepat dulu, fallback AgentCore Browser
                (CDP over websocket, SigV4-signed) untuk halaman ber-JS.

Event dari Gateway dinormalisasi (toolName/tool/name + arguments/parameters/input).
"""
import html as htmllib
import json
import os
import re
import time
import urllib.parse
import urllib.request

REGION = os.environ.get("AWS_REGION", "us-east-1")
BROWSER_ID = os.environ.get("BROWSER_ID", "aws.browser.v1")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")


def _norm(event):
    tool = (event.get("toolName") or event.get("tool") or event.get("name") or "")
    args = (event.get("arguments") or event.get("parameters") or event.get("input") or {})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = {}
    return tool, args or {}


# ------------------------------------------------------------------ web_search
DDG_HTML = "https://html.duckduckgo.com/html/?q={q}"
DDG_LITE = "https://lite.duckduckgo.com/lite/?q={q}"


def _http_get(url, timeout=9):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "text/html", "Accept-Language": "en-US,en;q=0.9,id;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def _strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s)
    return htmllib.unescape(re.sub(r"\s+", " ", s)).strip()


def _parse_ddg(body):
    out = []
    # html.duckduckgo.com
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', body, re.S):
        href, title = m.group(1), _strip_tags(m.group(2))
        if href.startswith("//duckduckgo.com/l/?uddg="):
            q = href.split("uddg=")[1].split("&")[0]
            href = urllib.parse.unquote(q)
        if href.startswith("http"):
            out.append({"url": href, "title": title})
    if not out:
        # lite version: tabel sederhana <a rel="nofollow" href="...">
        for m in re.finditer(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', body, re.S):
            href, title = m.group(1), _strip_tags(m.group(2))
            if "duckduckgo.com" in href or not title:
                continue
            out.append({"url": href, "title": title})
    return out[:10]


def web_search(args):
    query = (args.get("query") or "").strip()
    if not query:
        return {"status": "error", "message": "query kosong"}
    q = urllib.parse.quote(query)
    results, engine, last_err, body = [], "", "", ""
    for name, tpl in (("ddg-html", DDG_HTML), ("ddg-lite", DDG_LITE)):
        try:
            body = _http_get(tpl.format(q=q))
            results = _parse_ddg(body)
            if results:
                engine = name
                break
        except Exception as e:
            last_err = f"{name}: {str(e)[:120]}"
            continue
    if not results:
        return {"status": "error", "message": f"pencarian gagal. {last_err}"}
    snips = [m.group(1) for m in
             re.finditer(r'class="result__snippet"[^>]*>(.*?)</a>', body, re.S)]
    for i, r in enumerate(results):
        r["snippet"] = _strip_tags(snips[i])[:300] if i < len(snips) else ""
    return {"status": "ok", "engine": engine, "count": len(results), "results": results[:8]}


# ------------------------------------------------------------------ web_fetch
FORBID = re.compile(r"^(file:|ftp:|data:)|localhost|127\.0\.0\.1|0\.0\.0\.0|169\.254\.|\[::1\]", re.I)


def _strip_html_to_text(html):
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<(br|/p|/div|/h[1-6]|/li|/tr)[^>]*>", "\n", html, flags=re.I)
    txt = htmllib.unescape(re.sub(r"<[^>]+>", " ", html))
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n", txt)
    return txt.strip()


def _fetch_plain(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,id;q=0.8"})
    with urllib.request.urlopen(req, timeout=13) as r:
        body = r.read(400_000).decode("utf-8", "ignore")
    title = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
    text = _strip_html_to_text(body)
    return (title.group(1) if title else ""), text


def _cdp_extract(ws_url, page_url, timeout_s=28):
    """Connect AgentCore Browser automation stream (SigV4-signed wss) via CDP."""
    import botocore.auth
    import botocore.awsrequest
    import botocore.session
    import websocket

    creds = botocore.session.get_session().get_credentials().get_frozen_credentials()
    req = botocore.awsrequest.AWSRequest(method="GET", url=ws_url, data=b"")
    botocore.auth.SigV4Auth(creds, "bedrock-agentcore", REGION).add_auth(req)
    hdrs = {k.lower(): v for k, v in req.headers.items()}
    ws = websocket.create_connection(
        ws_url, timeout=timeout_s,
        header=[f"{k}: {v}" for k, v in hdrs.items()],
        suppress_origin=True,
    )
    mid = [0]

    def call(method, params=None, session_id=None):
        mid[0] += 1
        msg = {"id": mid[0], "method": method}
        if params is not None:
            msg["params"] = params
        if session_id:
            msg["sessionId"] = session_id
        ws.send(json.dumps(msg))
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            raw = ws.recv()
            if not raw:
                continue
            data = json.loads(raw)
            if data.get("id") == mid[0]:
                if "error" in data:
                    raise RuntimeError(f"CDP {method}: {str(data['error'])[:200]}")
                return data.get("result", {})
        raise RuntimeError(f"CDP {method} timeout")

    try:
        tgt = call("Target.createTarget", {"url": page_url})
        tid = tgt["targetId"]
        att = call("Target.attachToTarget", {"targetId": tid, "flatten": True})
        sid_ = att["sessionId"]
        time.sleep(2.5)  # beri waktu JS render
        expr = ("(function(){var t=document.title;var b=document.body?document.body.innerText:'';"
                "return t+'\\n\\n'+b;})()")
        res = call("Runtime.evaluate", {"expression": expr, "returnByValue": True}, session_id=sid_)
        text = (res.get("result", {}) or {}).get("value", "") or ""
        call("Target.closeTarget", {"targetId": tid})
        return text
    finally:
        try:
            ws.close()
        except Exception:
            pass


def web_fetch(args):
    url = (args.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"status": "error", "message": "url harus http(s)"}
    if FORBID.search(url):
        return {"status": "error", "message": "url dilarang oleh kebijakan (internal/file)"}
    want_js = bool(args.get("js"))
    max_chars = min(int(args.get("max_chars", 6000)), 12000)
    title, text, method, note = "", "", "GET", ""
    if not want_js:
        try:
            title, text = _fetch_plain(url)
            if len(text) < 400:  # kemungkinan halaman ber-JS
                note = "konten GET pendek, beralih ke AgentCore Browser"
                method, text, title = "BROWSER", "", ""
        except Exception as e:
            note = f"GET gagal ({str(e)[:120]}), beralih ke AgentCore Browser"
            method = "BROWSER"
    if method == "BROWSER" or want_js:
        bac = boto3_client()
        sess = bac.start_browser_session(browserIdentifier=BROWSER_ID,
                                         sessionTimeoutSeconds=120)
        bsid = sess["sessionId"]
        ws_url = sess["streams"]["automationStream"]["streamEndpoint"]
        try:
            raw = _cdp_extract(ws_url, url)
            parts = raw.split("\n\n", 1)
            title = parts[0][:200] if len(parts) > 1 else title
            text = parts[1] if len(parts) > 1 else raw
            method = "AgentCore Browser (CDP)"
        except Exception as e:
            return {"status": "error", "message": f"browser extract gagal: {str(e)[:200]}",
                    "note": note}
        finally:
            try:
                bac.stop_browser_session(browserIdentifier=BROWSER_ID, sessionId=bsid)
            except Exception:
                pass
    if not text:
        return {"status": "error", "message": "halaman kosong"}
    return {"status": "ok", "url": url, "method": method, "title": title[:200],
            "note": note, "content": text[:max_chars]}


# ------------------------------------------------------------------ entry
def boto3_client():
    import boto3
    from botocore.config import Config
    return boto3.client("bedrock-agentcore", region_name=REGION,
                        config=Config(retries={"max_attempts": 2}, read_timeout=90))


TOOLS = {
    "web_search": (web_search, "Pencarian web gratis via DuckDuckGo"),
    "web_fetch": (web_fetch, "Ambil isi halaman web (GET cepat / AgentCore Browser utk JS)"),
}


def handler(event, context):
    tool, args = _norm(event if isinstance(event, dict) else {})
    fn = TOOLS.get(tool, (None, None))[0]
    print(json.dumps({"gw_event_tool": tool, "args": str(args)[:300]}))
    if fn is None:
        return {"status": "error", "message": f"tool '{tool}' tidak dikenal",
                "available": sorted(TOOLS.keys())}
    try:
        out = fn(args)
    except Exception as e:
        out = {"status": "error", "message": str(e)[:400]}
    print(json.dumps({"gw_result_tool": tool, "status": out.get("status")}))
    return out
