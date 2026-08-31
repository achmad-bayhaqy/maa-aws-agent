#!/usr/bin/env python3
"""E2E v3.4.2: login TOTP -> /me -> guardrail bypass superadmin (trace)
-> agentMode TODO + legacy mode=LONG kompat -> upload GAMBAR (PNG) -> chat dgn
gambar -> /chat/status atts WAJIB array (fix crash) -> trace -> cleanup."""
import base64
import hashlib
import hmac
import json
import os
import struct
import time
import urllib.parse
import urllib.request
import zlib

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


def png_bytes():
    """PNG 1x1 merah valid (untuk test lampiran gambar)."""
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def wait_chat(sid, max_s=150):
    """Poll status sampai done/error; return (status, messages, trace_has)."""
    t0 = time.time()
    while time.time() - t0 < max_s:
        time.sleep(5)
        cs, stu = api("GET", "/chat/status", TOKEN, query={"sessionId": sid})
        if cs != 200:
            return f"http{cs}", [], ""
        if stu.get("status") == "done":
            return "done", stu.get("messages", ""), ""
        if stu.get("status") in ("failed", "error"):
            return "error:" + str(stu.get("err", ""))[:120], stu.get("messages", ""), ""
    return "timeout", [], ""


ok = lambda label, cond, extra="": print(f"{'PASS' if cond else 'FAIL'} {label} {extra}", flush=True)

# 1) login + TOTP
a = cognito("InitiateAuth", {"AuthFlow": "USER_PASSWORD_AUTH",
                             "AuthParameters": {"USERNAME": cr["username"], "PASSWORD": cr["password"]},
                             "ClientId": cr.get("client_id") or cr["app_client_id"]})
if a.get("ChallengeName") == "SOFTWARE_TOKEN_MFA":
    a = cognito("RespondToAuthChallenge", {
        "ClientId": cr.get("client_id") or cr["app_client_id"], "ChallengeName": "SOFTWARE_TOKEN_MFA",
        "Session": a["Session"],
        "ChallengeResponses": {"USERNAME": cr["username"],
                               "SOFTWARE_TOKEN_MFA_CODE": totp(cr["totp_secret"])}})
TOKEN = a["AuthenticationResult"]["IdToken"]
ok("login+TOTP", bool(TOKEN), f"(username={cr['username']})")

# 2) /me superadmin
c, me = api("GET", "/me", TOKEN)
ok("/me role=superadmin", c == 200 and me.get("role") == "superadmin", f"{c} role={me.get('role')}")

# 3) chat agentMode=TODO (mode tugas terpisah dari mode model)
msg = "Gunakan todo list: buat rencana 2 langkah untuk mengecek layanan storage AWS lalu kerjakan. Jawab singkat."
c, ch = api("POST", "/chat", TOKEN, {"message": msg, "mode": "FAST", "agentMode": "TODO"})
sid1 = ch.get("sessionId") if isinstance(ch, dict) else None
ok("POST /chat mode=FAST agentMode=TODO", c == 202 and bool(sid1), f"{c} sid={sid1}")
s1, msgs1, _ = wait_chat(sid1) if sid1 else ("skip", [], "")
asst1 = next((m.get("text", "") for m in reversed(msgs1) if m.get("role") == "assistant"), "")
ok("chat agentMode=TODO selesai", s1 == "done" and len(asst1) > 20, f"{s1} jawaban={asst1[:120]!r}")
c, t1 = api("GET", "/chat/trace", TOKEN, query={"sessionId": sid1})
tr1 = json.dumps(t1, ensure_ascii=False) if isinstance(t1, dict) else ""
ok("trace menandai tugas TODO + guardrail dilewati (superadmin)",
   "TODO" in tr1 and "DILEWATI" in tr1,
   f"events={len(t1.get('events', [])) if isinstance(t1, dict) else 0}")

# 4) legacy kompat: mode=LONG (klien v3.4 lama) -> dipetakan agentMode=LONG
msg2 = "Sebutkan 2 layanan database AWS dalam satu kalimat."
c, ch2 = api("POST", "/chat", TOKEN, {"message": msg2, "mode": "LONG"})
sid2 = ch2.get("sessionId") if isinstance(ch2, dict) else None
ok("POST /chat legacy mode=LONG (kompat v3.4)", c == 202 and bool(sid2), f"{c} sid={sid2}")
s2, msgs2, _ = wait_chat(sid2) if sid2 else ("skip", [], "")
ok("chat legacy LONG selesai", s2 == "done", f"{s2}")

# 5) upload GAMBAR (PNG) -> chat dgn lampiran gambar
img = png_bytes()
c, pr = api("POST", "/uploads/presign", TOKEN,
            {"name": "tes-gambar.png", "contentType": "image/png", "size": len(img)})
up_ok = c == 200 and pr.get("uploadUrl")
ok("presign gambar PNG", up_ok, f"{c} size={len(img)}B key={pr.get('key', '')[:50] if isinstance(pr, dict) else ''}")
if up_ok:
    c2, _ = raw_request("PUT", pr["uploadUrl"], body_bytes=img,
                        headers=pr.get("headers") or {"Content-Type": "image/png"})
    ok("S3 PUT gambar", c2 == 200, f"{c2}")
    msg3 = "Apa warna gambar yang saya lampirkan? Jawab satu kata."
    c3, ch3 = api("POST", "/chat", TOKEN,
                  {"message": msg3, "mode": "AUTO",
                   "attachments": [{"key": pr["key"], "name": "tes-gambar.png",
                                    "contentType": "image/png", "size": len(img)}]})
    sid3 = ch3.get("sessionId") if isinstance(ch3, dict) else None
    ok("POST /chat + lampiran gambar", c3 == 202 and bool(sid3), f"{c3} sid={sid3}")
    s3, msgs3, _ = wait_chat(sid3) if sid3 else ("skip", [], "")
    asst3 = next((m.get("text", "") for m in reversed(msgs3) if m.get("role") == "assistant"), "")
    low3 = asst3.lower()
    crash_bad = any(b in low3 for b in ["loop berhenti", "diblokir", "guardrail menahan"]) or s3 != "done"
    ok("chat gambar terjawab (tidak crash/error)", not crash_bad,
       f"{s3} jawaban={asst3[:120]!r}")
    # 6) FIX CRASH: atts WAJIB array, bukan string JSON
    user_atts = []
    for m in msgs3:
        if m.get("role") == "user" and "atts" in m:
            user_atts = m["atts"]
            break
    ok("atts di /chat/status berupa ARRAY (fix crash upload gambar)",
       isinstance(user_atts, list) and len(user_atts) > 0
       and all(isinstance(a, dict) for a in user_atts),
       f"tipe={type(user_atts).__name__} n={len(user_atts)} sample={json.dumps(user_atts[:1], ensure_ascii=False)[:140]}")
    api("DELETE", "/chat/sessions", TOKEN, query={"sessionId": sid3})

# 7) semua pesan sesi lain juga aman tipenya
all_arrays = True
for sid_x in (sid1, sid2):
    if not sid_x:
        continue
    cs, sx = api("GET", "/chat/status", TOKEN, query={"sessionId": sid_x})
    for m in (sx.get("messages", []) if isinstance(sx, dict) else []):
        for f in ("atts", "versions"):
            if f in m and not isinstance(m[f], list):
                all_arrays = False
ok("seluruh pesan atts/versions bertipe array (semua sesi)", all_arrays)

# cleanup
for sid_x in (sid1, sid2):
    if sid_x:
        api("DELETE", "/chat/sessions", TOKEN, query={"sessionId": sid_x})

print("\n=== E2E v3.4.2 SELESAI ===")
