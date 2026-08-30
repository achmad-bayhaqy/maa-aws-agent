#!/usr/bin/env python3
"""MAA AWS Agent - Task 8: End-to-end backend test via API Gateway.
Flow: Cognito enrollment (TOTP) -> login+MFA -> chat FAST/DEEP/MANUAL ->
destructive double-confirmation -> KB -> Live Trace -> sessions."""
import base64
import hashlib
import hmac
import json
import struct
import time
import urllib.request
import uuid

import boto3

st = json.load(open("/home/z/my-project/aws/state.json"))
cr = json.load(open("/home/z/my-project/aws/maa-user-credentials.json"))
API = st["api_url"]
REGION = "us-east-1"
POOL = st["user_pool_id"]
CLIENT = st["app_client_id"]
COG_URL = f"https://cognito-idp.{REGION}.amazonaws.com/"

ddb = boto3.client("dynamodb", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)


def totp(secret_b32, t=None):
    key = base64.b32decode(secret_b32 + "=" * ((8 - len(secret_b32) % 8) % 8))
    counter = int((t or time.time()) // 30)
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return f"{(struct.unpack('>I', h[o:o+4])[0] & 0x7FFFFFFF) % 10**6:06d}"


def cognito(op, payload):
    req = urllib.request.Request(
        COG_URL, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/x-amz-json-1.1",
                 "X-Amz-Target": f"AWSCognitoIdentityProviderService.{op}"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"{op} -> {e.code}: {body[:200]}")


def api(method, path, token=None, body=None, query=None):
    url = f"{API}{path}"
    if query:
        url += "?" + "&".join(f"{k}={v}" for k, v in query.items())
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {str(detail)[:120]}")


print("=== 1. Enrollment flow (login pertama) ===")
r = cognito("InitiateAuth", {"AuthFlow": "USER_PASSWORD_AUTH", "AuthParameters": {
    "USERNAME": cr["username"], "PASSWORD": cr["password"]}, "ClientId": CLIENT})
if r.get("ChallengeName") == "SOFTWARE_TOKEN_MFA":
    check("login -> SOFTWARE_TOKEN_MFA", True, "sudah ter-enroll sebelumnya")
    SECRET = cr.get("totp_secret")
    code = totp(SECRET)
    r2 = cognito("RespondToAuthChallenge", {
        "ChallengeName": "SOFTWARE_TOKEN_MFA", "ClientId": CLIENT,
        "Session": r["Session"],
        "ChallengeResponses": {"USERNAME": cr["username"], "SOFTWARE_TOKEN_MFA_CODE": code}})
    tokens = r2["AuthenticationResult"]
else:
    check("login -> MFA_SETUP", r.get("ChallengeName") == "MFA_SETUP", r.get("ChallengeName"))
    s = cognito("AssociateSoftwareToken", {"Session": r["Session"]})
    SECRET = s["SecretCode"]
    cr["totp_secret"] = SECRET
    json.dump(cr, open("/home/z/my-project/aws/maa-user-credentials.json", "w"), indent=2)
    time.sleep(2)
    v = cognito("VerifySoftwareToken", {"Session": s["Session"], "UserCode": totp(SECRET),
                                        "FriendlyDeviceName": "MAA Test"})
    check("verify TOTP", v["Status"] == "SUCCESS", v["Status"])
    r2 = cognito("RespondToAuthChallenge", {
        "ChallengeName": "MFA_SETUP", "ClientId": CLIENT, "Session": v["Session"],
        "ChallengeResponses": {"USERNAME": cr["username"],
                               "PREFERRED_CHALLENGE": "SOFTWARE_TOKEN_MFA"}})
    tokens = r2["AuthenticationResult"]
TOKEN = tokens["IdToken"]
check("mendapat JWT tokens", bool(TOKEN), f"access {len(tokens.get('AccessToken',''))}B id {len(TOKEN)}B")

# QR PNG untuk user
try:
    import qrcode
    uri = (f"otpauth://totp/MAA-AWS-Agent:{cr['username']}?secret={SECRET}"
           f"&issuer=MAA%20AWS%20Agent&algorithm=SHA1&digits=6&period=30")
    img = qrcode.make(uri)
    img.save("/home/z/my-project/aws/maa-totp-qr.png")
    print("  QR TOTP -> /home/z/my-project/aws/maa-totp-qr.png")
except ImportError:
    print("  (qrcode lib tidak ada - QR dibuat di frontend)")

print("\n=== 2. API basic ===")
code, out = api("GET", "/models", TOKEN)
check("GET /models", code == 200, f"{len(out.get('models', []))} models")
code, out = api("GET", "/kb/docs", TOKEN)
check("GET /kb/docs", code == 200 and len(out.get("docs", [])) >= 3, f"{len(out.get('docs', []))} docs")
code, out = api("GET", "/chat/sessions", TOKEN)
check("GET /chat/sessions", code == 200, out)


def chat_and_wait(message, mode="FAST", model_id=None, max_wait=300):
    code, out = api("POST", "/chat", TOKEN, {"message": message, "mode": mode, "modelId": model_id})
    if code != 202:
        return code, out, None, []
    sid = out["sessionId"]
    t0 = time.time()
    while time.time() - t0 < max_wait:
        c, s = api("GET", "/chat/status", TOKEN, query={"sessionId": sid})
        if c == 200 and s.get("status") in ("done", "error"):
            tr_code, tr = api("GET", "/chat/trace", TOKEN, query={"sessionId": sid})
            return c, s, sid, tr.get("events", []) if tr_code == 200 else []
        time.sleep(3)
    return 200, {"status": "timeout"}, sid, []


print("\n=== 3. Chat FAST: list EC2 ( harus menyebut 2 instance demo) ===")
c, s, sid, traces = chat_and_wait("Berapa instance EC2 di akun ini? Sebutkan nama dan statusnya.")
resp_text = (s.get("messages", [{}])[-1].get("text", "") if s.get("messages") else "")
check("chat FAST 202->done", c == 202 and s.get("status") == "done", s.get("status"))
check("jawaban menyebut demo instance", "maa-demo-app" in resp_text, resp_text[:120])
check("Live Trace ada tool_call", any(t["type"] == "tool_call" for t in traces),
      f"{len(traces)} events: {sorted(set(t['type'] for t in traces))}")

print("\n=== 4. Chat MANUAL glm-5: analisis biaya ===")
c, s, sid2, traces2 = chat_and_wait("Analisis biaya AWS 30 hari terakhir, sebutkan total dan top layanan. Ada idle resources?",
                                    mode="MANUAL", model_id="zai.glm-5")
resp2 = (s.get("messages", [{}])[-1].get("text", "") if s.get("messages") else "")
check("chat MANUAL done", s.get("status") == "done", s.get("status"))
check("jawaban biaya ada angka", any(ch.isdigit() for ch in resp2), resp2[:120])



def s3_bucket_exists(b):
    try:
        s3.head_bucket(Bucket=b)
        return True
    except Exception:
        return False

print("\n=== 5. Destructive double-confirmation via API ===")
B = f"maa-agent-e2e-del-{uuid.uuid4().hex[:6]}"
s3.create_bucket(Bucket=B)
print(f"  dummy bucket: {B}")
c, s, sid3, traces3 = chat_and_wait(f"Hapus bucket S3 bernama {B} sekarang.", mode="FAST")
check("agen TIDAK langsung menghapus", s3_bucket_exists(B), "bucket masih ada (menunggu konfirmasi)")
pend = ddb.scan(TableName="maa-agent-confirmations", FilterExpression="#s = :p AND sessionId = :sid",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":p": {"S": "pending"}, ":sid": {"S": sid3}})["Items"]
check("pending confirmation dibuat", len(pend) >= 1, f"{len(pend)} pending")
if pend:
    token, chal = pend[0]["confirmToken"]["S"], pend[0]["challenge"]["S"]
    c1, o1 = api("POST", "/chat/confirm", TOKEN, {"sessionId": sid3, "confirmToken": token,
                                                  "typed1": "SALAH", "typed2": "SALAH"})
    check("string salah -> ditolak", o1.get("status") == "mismatch", o1)
    c2, o2 = api("POST", "/chat/confirm", TOKEN, {"sessionId": sid3, "confirmToken": token,
                                                  "typed1": chal, "typed2": chal})
    check("string benar x2 -> executed", o2.get("status") == "executed", str(o2)[:150])
    time.sleep(2)
    check("bucket benar-benar terhapus", not s3_bucket_exists(B))


print("\n=== 6. DEEP mode quick (IaC) ===")
c, s, sid4, _ = chat_and_wait("Buatkan template CloudFormation S3 bucket sederhana via iac_generate, jangan deploy.",
                              mode="DEEP", max_wait=300)
check("DEEP mode done", s.get("status") == "done", s.get("status"))

print("\n=== RINGKASAN ===")
passed = sum(1 for _, ok, _ in results if ok)
print(f"{passed}/{len(results)} tests passed")
for name, ok, detail in results:
    if not ok:
        print(f"  FAIL: {name} :: {detail[:200]}")
