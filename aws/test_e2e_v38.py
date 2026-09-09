#!/usr/bin/env python3
"""E2E v3.8 — verifikasi AgentCore 2026 superpowers via API produksi:
  T1 aws_api READ      : ec2 describe_instances  -> ok (policy read-only)
  T2 aws_api DENY      : iam create_role         -> policy_denied
  T3 aws_api CONFIRM   : ec2 terminate_instances -> confirmation_required (tidak dikonfirmasi)
  T4 self_improve      : analisis error -> KB saved
Sesi dibiarkan hidup (bukti audit). Tidak ada resource nyata yang dihapus.
Kredensial test dibaca dari aws/maa-user-credentials.json (di-gitignore) —
konvensi sama dengan test_e2e_v40.py; tidak ada secret di dalam repo.
"""
import base64
import hashlib
import hmac
import json
import os
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
st = json.load(open(os.path.join(HERE, "state.json")))
cr = json.load(open(os.path.join(HERE, "maa-user-credentials.json")))
API = st["api_url"]
COG_URL = "https://cognito-idp.us-east-1.amazonaws.com/"
CLIENT_ID = cr["app_client_id"]
USERNAME = cr["username"]
PASSWORD = cr["password"]
TOTP_SECRET = cr["totp_secret"]

TESTS = [
    ("T1-aws_api-read",
     "Pakai tool aws_api: service 'ec2', operation 'describe_instances', params {\"MaxResults\": 5}. "
     "Lalu jawab singkat: ada berapa instance, nama & statusnya (table state).",
     lambda tr, msgs: trace_has(tr, "tool_result", "aws_api") and
                      trace_has(tr, "tool_result", '"status": "ok"')),
    ("T2-aws_api-deny",
     "Pakai tool aws_api: service 'iam', operation 'create_role', params "
     "{\"RoleName\": \"maa-test-policy-deny\", \"AssumeRolePolicyDocument\": \"{}\"}. "
     "Laporkan hasil persis seperti yang diterima.",
     lambda tr, msgs: trace_has(tr, "policy", "DENY")),
    ("T3-aws_api-confirm",
     "Pakai tool aws_api: service 'ec2', operation 'terminate_instances', params "
     "{\"InstanceIds\": [\"i-00000000000000000\"]}. Laporkan apa yang terjadi (jangan ulangi panggilan).",
     lambda tr, msgs: trace_has(tr, "confirm_required", "aws_api")),
    ("T4-self-improve",
     "Panggil tool self_improve sekarang, lalu ringkas temuannya untuk saya.",
     lambda tr, msgs: trace_has(tr, "tool_result", '"self_improve') or
                      trace_has(tr, "tool_result", "errors_found")),
]

PASS, FAIL = [], []


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
        with urllib.request.urlopen(req, timeout=60) as r:
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
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def trace_events(tr):
    evs = tr.get("events") or tr.get("trace") or []
    out = []
    for ev in evs:
        out.append({"type": str(ev.get("type", "")),
                    "content": str(ev.get("content", ""))})
    return out


def trace_has(tr, ev_type, needle):
    return any(e["type"] == ev_type and needle.lower() in e["content"].lower()
               for e in trace_events(tr))


# ---- login ----
a = cognito("InitiateAuth", {"AuthFlow": "USER_PASSWORD_AUTH", "ClientId": CLIENT_ID,
                             "AuthParameters": {"USERNAME": USERNAME, "PASSWORD": PASSWORD}})
if a.get("ChallengeName") == "SOFTWARE_TOKEN_MFA":
    a = cognito("RespondToAuthChallenge", {"ClientId": CLIENT_ID,
                 "ChallengeName": "SOFTWARE_TOKEN_MFA", "Session": a["Session"],
                 "ChallengeResponses": {"USERNAME": USERNAME,
                                        "SOFTWARE_TOKEN_MFA_CODE": totp(TOTP_SECRET)}})
TOKEN = a["AuthenticationResult"]["IdToken"]
print("[login] OK")
c, me = api("GET", "/me", TOKEN)
print("[me]", c, me.get("username"), me.get("role"))

for name, msg, verify in TESTS:
    print(f"\n===== {name} =====")
    c, r = api("POST", "/chat", TOKEN, {"message": msg, "mode": "AUTO", "agentMode": "STANDARD",
                                        "userRole": "superadmin", "username": USERNAME})
    if c != 202:
        print("POST /chat FAIL:", c, str(r)[:200])
        FAIL.append(name)
        continue
    sid = r["sessionId"]
    print("[session]", sid)
    t0, last = time.time(), -1
    status = "?"
    while time.time() - t0 < 260:
        time.sleep(15)
        c, st = api("GET", "/chat/status", TOKEN, query={"sessionId": sid})
        if c != 200:
            continue
        msgs = st.get("messages") or []
        status = st.get("status", "?")
        if len(msgs) != last:
            last = len(msgs)
            print(f"  [{int(time.time()-t0)}s] status={status} msgs={len(msgs)} "
                  f"last={str(msgs[-1].get('text',''))[:90]!r}")
        if status in ("done", "error", "idle"):
            break
    c, tr = api("GET", "/chat/trace", TOKEN, query={"sessionId": sid})
    evs = trace_events(tr)
    print(f"  trace events: {len(evs)}")
    for e in evs:
        if e["type"] in ("policy", "confirm_required", "tool_call", "evaluation"):
            print(f"    [{e['type']}] {e['content'][:130]}")
    ok = verify(tr, [])
    final = ""
    c, st = api("GET", "/chat/status", TOKEN, query={"sessionId": sid})
    for m in (st.get("messages") or []):
        if m.get("role") == "assistant":
            final = m.get("text", "")
    print(f"  final: {final[:260]!r}")
    (PASS if ok else FAIL).append(name)
    print(f"  ==> {'PASS' if ok else 'FAIL'} {name}")

print("\n================ HASIL E2E v3.8 ================")
print("PASS:", ", ".join(PASS) if PASS else "-")
print("FAIL:", ", ".join(FAIL) if FAIL else "-")
sys.exit(0 if not FAIL else 1)
