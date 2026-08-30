#!/usr/bin/env python3
"""Smoke E2E v3: login TOTP -> /me -> /models(autoDefaults) -> /chat AUTO ->
poll status -> trace -> edit pesan (editFrom) -> sessions. Cepat & ringkas."""
import base64
import hashlib
import hmac
import json
import struct
import time
import urllib.request

st = json.load(open("/home/z/my-project/aws/state.json"))
cr = json.load(open("/home/z/my-project/aws/maa-user-credentials.json"))
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


import urllib.parse  # noqa: E402

ok = lambda label, cond, extra="": print(f"{'PASS' if cond else 'FAIL'} {label} {extra}", flush=True)

# 1) login + MFA
a = cognito("InitiateAuth", {"AuthFlow": "USER_PASSWORD_AUTH",
                              "ClientId": st["app_client_id"],
                              "AuthParameters": {"USERNAME": cr["username"],
                                                 "PASSWORD": cr["password"]}})
sess = a.get("Session")
if sess:  # MFA challenge
    b = cognito("RespondToAuthChallenge", {"ChallengeName": a["ChallengeName"],
                                              "Session": sess, "ClientId": st["app_client_id"],
                                              "ChallengeResponses": {
                                                  "USERNAME": cr["username"],
                                                  "SOFTWARE_TOKEN_MFA_CODE": totp(cr["totp_secret"])}})
    tok = b["AuthenticationResult"]["IdToken"]  # kontrak API = ID token (sama dgn frontend)
else:
    tok = a["AuthenticationResult"]["IdToken"]
ok("login TOTP", bool(tok))

# 2) /me
code, me = api("GET", "/me", tok)
ok("/me", code == 200 and me.get("username") == "architect", f"{code} {json.dumps(me)[:120]}")

# 3) /models + autoDefaults
code, md = api("GET", "/models", tok)
n = len(md.get("models", [])) if isinstance(md, dict) else 0
ok("/models", code == 200 and n >= 88 and "autoDefaults" in md, f"{code} models={n} autoDefaults={md.get('autoDefaults') if isinstance(md, dict) else '-'}")

# 4) chat AUTO
code, ch = api("POST", "/chat", tok, {"message": "Sebut jumlah instance EC2 di akun ini secara singkat.", "mode": "AUTO"})
ok("POST /chat", code == 202 and ch.get("sessionId"), f"{code} {json.dumps(ch)[:100]}")
sid = ch["sessionId"]

final = None
for _ in range(40):
    time.sleep(3)
    code, s = api("GET", "/chat/status", tok, query={"sessionId": sid})
    if s.get("status") in ("done", "error"):
        final = s
        break
msgs = final.get("messages", []) if isinstance(final, dict) else []
reply = next((m["text"] for m in reversed(msgs) if m.get("role") == "assistant"), "")
ok("chat done", final and final.get("status") == "done" and reply,
   f"status={final.get('status') if isinstance(final, dict) else '?'} autoRoute={json.dumps(final.get('autoRoute')) if isinstance(final, dict) else '-'}")
print("   reply:", reply[:160].replace("\n", " "), flush=True)

# 5) trace
code, tr = api("GET", "/chat/trace", tok, query={"sessionId": sid, "after": 0})
evs = tr.get("events", []) if isinstance(tr, dict) else []
ok("/chat/trace", code == 200 and len(evs) >= 2, f"{code} events={len(evs)}")

# 6) edit pesan terakhir (editFrom versi pertama)
code, ed = api("POST", "/chat", tok, {"message": "Berapa total EC2? jawab 1 kalimat.",
                                      "mode": "FAST", "sessionId": sid, "editFrom": 0})
ok("POST /chat editFrom", code == 202, f"{code} {json.dumps(ed)[:100]}")
final2 = None
for _ in range(40):
    time.sleep(3)
    code, s = api("GET", "/chat/status", tok, query={"sessionId": sid})
    if s.get("status") in ("done", "error"):
        final2 = s
        break
msgs2 = final2.get("messages", []) if isinstance(final2, dict) else []
user_msg = next((m for m in msgs2 if m.get("role") == "user" and m.get("text", "").startswith("Berapa total")), None)
ok("edit versioning", bool(user_msg) and len(user_msg.get("versions", [])) >= 1,
   f"versions={len(user_msg.get('versions', [])) if user_msg else 0}")

# 7) sessions list
code, se = api("GET", "/chat/sessions", tok)
ok("/chat/sessions", code == 200 and any(s["sessionId"] == sid for s in se.get("sessions", [])), f"{code} n={len(se.get('sessions', [])) if isinstance(se, dict) else 0}")

print("\nE2E-SMOKE-V3 SELESAI", flush=True)
