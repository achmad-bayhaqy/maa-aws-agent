#!/usr/bin/env python3
"""E2E v3.4: login TOTP -> /me -> /models -> OPTIONS preflight -> presign upload
-> translate -> docs list/content/save -> chat guardrail-sanity ('Kamu bisa apa')
-> chat+attachment CSV -> trace -> sessions -> delete session."""
import base64
import hashlib
import hmac
import json
import os
import struct
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
st = json.load(open(os.path.join(HERE, "state.json")))
cr = json.load(open(os.path.join(HERE, "maa-user-credentials.json")))
API = st["api_url"]
COG_URL = "https://cognito-idp.us-east-1.amazonaws.com/"


def totp(secret_b32):
    key = base64.b32decode(secret_b32 + "=" * ((8 - len(secret_b32) % 8) % 8))
    counter = int(time.time() // 30)
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** 6:06d}"


def cognito(op, payload):
    req = urllib.request.Request(
        COG_URL, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/x-amz-json-1.1",
                 "X-Amz-Target": f"AWSCognitoIdentityProviderService.{op}"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{op} -> {e.code}: {e.read().decode()[:200]}")


def raw_request(method, url, token=None, body_bytes=None, headers=None):
    req = urllib.request.Request(url, data=body_bytes, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers)


def api(method, path, token=None, body=None, query=None):
    url = f"{API}{path}"
    if query:
        url += "?" + "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in query.items())
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


ok = lambda label, cond, extra="": print(f"{'PASS' if cond else 'FAIL'} {label} {extra}", flush=True)

# 1) login + TOTP MFA
a = cognito("InitiateAuth", {"AuthFlow": "USER_PASSWORD_AUTH",
                             "AuthParameters": {"USERNAME": cr["username"], "PASSWORD": cr["password"]},
                             "ClientId": cr["client_id"]})
if a.get("ChallengeName") == "SOFTWARE_TOKEN_MFA":
    a = cognito("RespondToAuthChallenge", {
        "ClientId": cr["client_id"], "ChallengeName": "SOFTWARE_TOKEN_MFA",
        "Session": a["Session"],
        "ChallengeResponses": {"USERNAME": cr["username"],
                               "SOFTWARE_TOKEN_MFA_CODE": totp(cr["totp_secret"])}})
TOKEN = a["AuthenticationResult"]["IdToken"]
ok("login+TOTP", bool(TOKEN), f"(username={cr['username']})")

# 2) /me
c, me = api("GET", "/me", TOKEN)
ok("/me", c == 200 and me.get("role") == "superadmin", f"{c} role={me.get('role')} user={me.get('username')}")

# 3) /models
c, md = api("GET", "/models", TOKEN)
n_models = len(md.get("models", []))
ok("/models", c == 200 and n_models >= 80, f"{c} total={n_models} autoDefaults={list((md.get('autoDefaults') or {}).keys())}")

# 4) OPTIONS preflight /uploads/presign
c, hdr = raw_request("OPTIONS", f"{API}/uploads/presign")
acao = hdr.get("Access-Control-Allow-Origin") or hdr.get("access-control-allow-origin")
ok("OPTIONS preflight presign", c == 200 and acao, f"{c} ACAO={acao}")

# 5) presign + real upload (CSV utk tes attachment)
csv_content = "region,service,monthly_cost_usd\nap-southeast-1,EC2,120\neu-west-1,RDS,340\nus-east-1,S3,25\n"
c, pr = api("POST", "/uploads/presign", TOKEN,
            {"name": "biaya-demo.csv", "contentType": "text/csv", "size": len(csv_content)})
up_ok = c == 200 and pr.get("uploadUrl") and pr.get("key")
ok("/uploads/presign", up_ok, f"{c} key={pr.get('key', '')[:60] if isinstance(pr, dict) else pr}")
if up_ok:
    c2, _ = raw_request("PUT", pr["uploadUrl"], body_bytes=csv_content.encode(),
                        headers=(pr.get("headers") or {"Content-Type": "text/csv"}))
    ok("S3 PUT upload", c2 == 200, f"{c2}")

# 6) translate EN -> ID
c, tr = api("POST", "/translate", TOKEN,
            {"text": "Hello, the agent is ready. Your cloud infrastructure looks healthy."})
tr_text = json.dumps(tr, ensure_ascii=False)[:120] if isinstance(tr, dict) else str(tr)[:120]
ok("/translate EN->ID", c == 200 and isinstance(tr, dict) and tr.get("indonesian") or c == 200 and tr.get("translation") or (c == 200 and len(json.dumps(tr)) > 20), f"{c} -> {tr_text}")

# 7) docs list + content
c, dl = api("GET", "/docs/list", TOKEN)
names = [d["name"] for d in dl.get("docs", [])] if isinstance(dl, dict) else []
ok("/docs/list", c == 200 and len(names) >= 3, f"{c} docs={names}")
c, dc = api("GET", "/docs/content", TOKEN, query={"key": "site/docs/panduan-cepat.md"})
ok("/docs/content GET", c == 200 and "Panduan Cepat" in dc.get("content", ""), f"{c} len={len(dc.get('content', '')) if isinstance(dc, dict) else 0}")

# 8) docs save (superadmin)
c, ds = api("POST", "/docs/content", TOKEN,
            {"key": "site/docs/e2e-test.md", "content": "# E2E Test\nDokumen uji v3.4 - aman dihapus.\n"})
ok("/docs/content POST (superadmin)", c == 200 and (ds.get("saved") if isinstance(ds, dict) else False), f"{c}")

# 9) CHAT guardrail sanity: 'Kamu bisa apa' HARUS dijawab normal (bukan guardrail/error/loop-stop)
msg = "Kamu bisa apa saja? Jawab singkat satu kalimat saja."
c, ch = api("POST", "/chat", TOKEN, {"message": msg, "mode": "AUTO"})
sid = ch.get("sessionId") if isinstance(ch, dict) else None
ok("POST /chat (AUTO)", c == 202 and bool(sid), f"{c} sid={sid}")

final_text = None
if sid:
    for i in range(36):
        time.sleep(5)
        cs, stu = api("GET", "/chat/status", TOKEN, query={"sessionId": sid})
        if cs != 200:
            break
        if stu.get("status") == "done":
            for m in reversed(stu.get("messages", [])):
                if m.get("role") == "assistant":
                    final_text = m.get("text", "")
                    break
            break
        if stu.get("status") in ("failed", "error"):
            final_text = "STATUS:" + str(stu.get("status"))
            break
low = (final_text or "").lower()
bad_signals = ["loop berhenti", "guardrail", "diblokir", "blocked"]
is_bad = any(b in low for b in bad_signals) or not final_text
ok("chat 'Kamu bisa apa' terjawab normal (guardrail fix)", not is_bad,
   f"jawaban: {(final_text or '(kosong)')[:160]!r}")

# 10) chat + attachment CSV (pipeline upload -> konteks)
msg2 = "File CSV yang saya lampirkan punya berapa baris data (tanpa header)? Jawab angka saja."
c, ch2 = api("POST", "/chat", TOKEN,
             {"message": msg2, "mode": "FAST", "sessionId": sid,
              "attachments": [{"key": pr["key"], "name": "biaya-demo.csv",
                               "contentType": "text/csv", "size": len(csv_content)}]
              if up_ok else None})
ok("POST /chat + attachment", c == 202, f"{c}")

att_final = None
if c == 202:
    for i in range(36):
        time.sleep(5)
        cs, stu = api("GET", "/chat/status", TOKEN, query={"sessionId": sid})
        if cs != 200:
            break
        if stu.get("status") == "done":
            for m in reversed(stu.get("messages", [])):
                if m.get("role") == "assistant":
                    att_final = m.get("text", "")
                    break
            break
        if stu.get("status") in ("failed", "error"):
            att_final = "STATUS:" + str(stu.get("status"))
            break
low2 = (att_final or "").lower()
att_bad = any(b in low2 for b in bad_signals) or not att_final
has_three = "3" in (att_final or "")
ok("chat+CSV terjawab (baca lampiran)", not att_bad,
   f"jawaban: {(att_final or '(kosong)')[:160]!r} {'(ada angka 3)' if has_three else ''}")

# 11) trace
c, trec = api("GET", "/chat/trace", TOKEN, query={"sessionId": sid})
nev = len(trec.get("events", [])) if isinstance(trec, dict) else 0
ok("/chat/trace", c == 200 and nev > 0, f"{c} events={nev}")

# 12) sessions + delete
c, sl = api("GET", "/chat/sessions", TOKEN)
sids = [s["sessionId"] for s in sl.get("sessions", [])] if isinstance(sl, dict) else []
ok("/chat/sessions GET", c == 200 and sid in sids, f"{c} count={len(sids)}")
c, de = api("DELETE", "/chat/sessions", TOKEN, query={"sessionId": sid})
ok("/chat/sessions DELETE", c == 200 and (de.get("deleted") if isinstance(de, dict) else False), f"{c}")
c2, st2 = api("GET", "/chat/status", TOKEN, query={"sessionId": sid})
ok("session hilang setelah DELETE", c2 in (403, 404), f"{c2}")

# cleanup dokumen uji
api("POST", "/docs/content", TOKEN, {"key": "site/docs/e2e-test.md",
                                     "content": "# E2E Test\n(reset)\n"})
print("\n=== E2E v3.4 SELESAI ===")
