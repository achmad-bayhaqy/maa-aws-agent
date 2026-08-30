#!/usr/bin/env python3
"""Diagnosis E2E chat produksi: login -> POST /chat -> poll status -> trace."""
import sys, time, json, hmac, hashlib, base64, struct, urllib.request, urllib.error

sys.path.insert(0, "/home/z/my-project/aws")
CREDS = json.load(open("/home/z/my-project/aws/maa-user-credentials.json"))
API = "https://bklw93lic3.execute-api.us-east-1.amazonaws.com/v1"
COG = f"https://cognito-idp.us-east-1.amazonaws.com/"


def totp(secret, t=None):
    t = t or int(time.time())
    key = base64.b32decode(secret.upper() + "=" * ((8 - len(secret) % 8) % 8))
    c = struct.pack(">Q", t // 30)
    h = hmac.new(key, c, hashlib.sha1).digest()
    o = h[19] & 0x0F
    return str((struct.unpack(">I", h[o:o+4])[0] & 0x7FFFFFFF) % 1000000).zfill(6)


def cog(op, payload):
    req = urllib.request.Request(COG, method="POST", data=json.dumps(payload).encode(), headers={
        "Content-Type": "application/x-amz-json-1.1",
        "X-Amz-Target": f"AWSCognitoIdentityProviderService.{op}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"__error": json.loads(e.read())}


def api(method, path, token, body=None, qs=None):
    url = API + path
    if qs:
        url += "?" + "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in qs.items())
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, method=method, data=data, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


print("== 1. LOGIN ==")
r = cog("InitiateAuth", {"AuthFlow": "USER_PASSWORD_AUTH", "AuthParameters": {
    "USERNAME": CREDS["username"], "PASSWORD": CREDS["password"]}, "ClientId": CREDS["app_client_id"]})
if r.get("__error"):
    print("LOGIN FAIL:", r["__error"]); sys.exit(1)
if r.get("ChallengeName") == "SOFTWARE_TOKEN_MFA":
    code = totp(CREDS["totp_secret"])
    print(f"  challenge MFA, code={code}")
    r2 = cog("RespondToAuthChallenge", {"ChallengeName": "SOFTWARE_TOKEN_MFA", "ClientId": CREDS["app_client_id"],
        "Session": r["Session"], "ChallengeResponses": {"USERNAME": CREDS["username"], "SOFTWARE_TOKEN_MFA_CODE": code}})
    if r2.get("__error"):
        print("MFA FAIL:", r2["__error"]); sys.exit(1)
    tok = r2["AuthenticationResult"]["IdToken"]
else:
    tok = r["AuthenticationResult"]["IdToken"]
print("  OK, token len:", len(tok))

print("== 2. POST /chat (FAST) ==")
st, body = api("POST", "/chat", tok, {"message": "Sebutkan 2 instance EC2 demo yang ada sekarang, singkat saja.", "mode": "FAST"})
print(" ", st, json.dumps(body, ensure_ascii=False)[:400])
if st != 202:
    sys.exit(1)
sid = body["sessionId"]

print("== 3. POLL status ==")
for i in range(24):
    time.sleep(5)
    st, s = api("GET", "/chat/status", tok, qs={"sessionId": sid})
    msgs = s.get("messages", [])
    last = msgs[-1] if msgs else {}
    print(f"  [{i*5}s] status={s.get('status')} n_msgs={len(msgs)} last_role={last.get('role','')} err={s.get('err','')}")
    if s.get("status") in ("done", "error"):
        if s.get("status") == "error":
            print("  SESSION ERROR DETAIL:", json.dumps(s, ensure_ascii=False)[:1000])
        break

print("== 4. TRACE ==")
st, t = api("GET", "/chat/trace", tok, qs={"sessionId": sid, "after": 0})
for e in t.get("events", []):
    print(f"  {e.get('type'):18s} {str(e.get('content'))[:140]}")

print("== 5. MODELS ==")
st, m = api("GET", "/models", tok)
if st == 200:
    models = m.get("models", m) if isinstance(m, dict) else m
    print("  count:", len(models) if isinstance(models, list) else "?")
    print("  sample:", json.dumps(models[:3] if isinstance(models, list) else m, ensure_ascii=False)[:300])
else:
    print("  FAIL:", st, m)
