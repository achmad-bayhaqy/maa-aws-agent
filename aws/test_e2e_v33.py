#!/usr/bin/env python3
"""E2E fix v3.3: (1) follow-up tidak buka sesi baru, (2) regenerate,
(3) delete sesi, (4) alur destruktif -> aws_delete_resource + pendingConfirmation."""
import base64
import hashlib
import hmac
import json
import struct
import time
import urllib.error
import urllib.parse
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


ok = lambda label, cond, extra="": print(f"{'PASS' if cond else 'FAIL'} {label} {extra}", flush=True)

# login
a = cognito("InitiateAuth", {"AuthFlow": "USER_PASSWORD_AUTH", "ClientId": st["app_client_id"],
                             "AuthParameters": {"USERNAME": cr["username"], "PASSWORD": cr["password"]}})
b = cognito("RespondToAuthChallenge", {"ChallengeName": a["ChallengeName"], "Session": a["Session"],
                                       "ClientId": st["app_client_id"],
                                       "ChallengeResponses": {"USERNAME": cr["username"],
                                                              "SOFTWARE_TOKEN_MFA_CODE": totp(cr["totp_secret"])}})
tok = b["AuthenticationResult"]["IdToken"]
ok("login", bool(tok))


def wait_done(sid, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        code, s = api("GET", "/chat/status", tok, query={"sessionId": sid})
        if isinstance(s, dict) and s.get("status") in ("done", "error"):
            return s
        time.sleep(3)
    return {"status": "timeout"}


# ===== TEST 1: follow-up tidak buka sesi baru =====
code, r1 = api("POST", "/chat", tok, {"message": "Sebutkan 1 instance EC2 apa saja secara singkat.", "mode": "FAST"})
sid = r1["sessionId"]
s = wait_done(sid)
n_msgs_1 = len(s.get("messages", []))
code, r2 = api("POST", "/chat", tok, {"message": "Kalau yang kedua apa?", "mode": "FAST", "sessionId": sid})
same_sid = r2.get("sessionId") == sid
s2 = wait_done(sid)
n_msgs_2 = len(s2.get("messages", []))
last_asst = next((m["text"] for m in reversed(s2.get("messages", []))
                  if m.get("role") == "assistant"), "")
ok("follow-up tetap 1 sesi", same_sid, f"sid={sid[:20]}")
ok("pesan lanjutan tercatat (4 pesan)", n_msgs_2 == n_msgs_1 + 2, f"{n_msgs_1} -> {n_msgs_2}")
ok("jawaban follow-up ada", bool(last_asst), f"'{last_asst[:80]}'")

# ===== TEST 2: regenerate =====
before_asst = last_asst
code, rg = api("POST", "/chat", tok, {"message": "", "mode": "FAST", "sessionId": sid, "regenerate": True})
ok("POST regenerate 202", code == 202, f"{code}")
s3 = wait_done(sid)
assts = [m for m in s3.get("messages", []) if m.get("role") == "assistant"]
new_asst = assts[-1] if assts else {}
vers = len(new_asst.get("versions", []))
ok("regenerate -> versions bertambah", vers >= 1, f"versions={vers}")
print(f"   jawaban baru: {str(new_asst.get('text',''))[:100]}", flush=True)

# ===== TEST 3: delete sesi =====
code, r3 = api("POST", "/chat", tok, {"message": "tes sesi sementara", "mode": "FAST"})
tmp_sid = r3["sessionId"]
wait_done(tmp_sid, 90)
code, d = api("DELETE", "/chat/sessions", tok, query={"sessionId": tmp_sid})
code2, ls = api("GET", "/chat/sessions", tok)
gone = not any(x["sessionId"] == tmp_sid for x in ls.get("sessions", []))
ok("delete sesi", code == 200 and gone, f"del={code} gone={gone}")

# ===== TEST 4: alur destruktif (tanpa eksekusi - hanya cek pendingConfirmation) =====
code, r4 = api("POST", "/chat", tok, {"message": "Hapus EC2 instance maa-demo-app-02 (i-0f0bc3c8994326102).", "mode": "AUTO"})
sid4 = r4["sessionId"]
s4 = wait_done(sid4, 150)
pend = s4.get("pendingConfirmation")
asst4 = next((m["text"] for m in reversed(s4.get("messages", [])) if m.get("role") == "assistant"), "")
ok("destructive -> pendingConfirmation muncul", bool(pend),
   f"challenge={pend.get('challenge','')[:40] if pend else '-'}")
ok("respons destruktif tidak kosong", bool(asst4), f"'{asst4[:100]}'")
print(f"   tool: {json.dumps(pend.get('operation'))[:150] if pend else '-'}", flush=True)

print("\nE2E-FIX-V3.3 SELESAI", flush=True)
