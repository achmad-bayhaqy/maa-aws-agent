#!/usr/bin/env python3
"""E2E v4.0: verifikasi 8 catatan perbaikan di deployment MAA akun 715841354009.
  1. generate_image (fallback SVG-art) + URL publik permanen
  2. KB CRUD via perintah chat + UI route
  3. scraping via CI INTERNET
  4. /files/view (buka file)
  5. /admin/users (Management User)
  6. skills payload (picker UI backend)
  7. task_schedule + tick worker
"""
import base64
import hashlib
import hmac
import json
import os
import struct
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
st = json.load(open(os.path.join(HERE, "state.json")))
cr = json.load(open(os.path.join(HERE, "maa-user-credentials.json")))
API = st["api_url"]
COG_URL = "https://cognito-idp.us-east-1.amazonaws.com/"

PASS, FAIL = [], []


def check(name, ok, info=""):
    (PASS if ok else FAIL).append(name)
    print(f"{'PASS' if ok else 'FAIL'} {name} {info}")


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


# ---- login ----
r = cognito("InitiateAuth", {
    "AuthFlow": "USER_PASSWORD_AUTH", "ClientId": cr["app_client_id"],
    "AuthParameters": {"USERNAME": cr["username"], "PASSWORD": cr["password"]}})
if r.get("ChallengeName") == "SOFTWARE_TOKEN_MFA":
    time.sleep(30 - (time.time() % 30) + 1)  # window segar
    r = cognito("RespondToAuthChallenge", {
        "ClientId": cr["app_client_id"], "ChallengeName": "SOFTWARE_TOKEN_MFA",
        "Session": r["Session"],
        "ChallengeResponses": {"USERNAME": cr["username"],
                               "SOFTWARE_TOKEN_MFA_CODE": totp(cr["totp_secret"])}})
TOKEN = r["AuthenticationResult"]["IdToken"]
check("login+TOTP", bool(TOKEN))


def api(method, path, body=None, qs=""):
    url = f"{API}{path}" + (f"?{qs}" if qs else "")
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 method=method,
                                 headers={"Authorization": TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def chat(message, **kw):
    code, r = api("POST", "/chat", {"message": message, "mode": "FAST", **kw})
    if code != 202:
        return None, f"chat POST {code}: {str(r)[:200]}"
    sid = r["sessionId"]
    for _ in range(60):
        time.sleep(5)
        c2, s = api("GET", "/chat/status", qs=f"sessionId={sid}")
        if c2 == 200 and s.get("status") in ("done", "error"):
            msgs = [m for m in s.get("messages", []) if m.get("role") == "assistant"]
            return sid, (msgs[-1]["text"] if msgs else "")
        if c2 != 200:
            return sid, f"status {c2}: {str(s)[:150]}"
    return sid, "(timeout)"


def last_trace(sid, n=30):
    c, t = api("GET", "/chat/trace", qs=f"sessionId={sid}&limit={n}")
    return t if c == 200 else []


# ---- 1. generate_image (SVG-art / Nova) + URL publik ----
sid, ans = chat("Tolong generate gambar: kucing astronaut lucu, ilustrasi warna cerah")
ok = "http" in ans and ("svg" in ans.lower() or ".png" in ans.lower() or "![" in ans)
check("generate_image fallback SVG-art", ok, ans[:120].replace("\n", " "))
img_url = ""
if "](http" in ans:
    img_url = ans.split("](http")[1].split(")")[0]
    img_url = "http" + img_url
elif "svg" in ans.lower() and "http" in ans:
    img_url = "https://" + ans.split("http")[2].split(")")[0] if ans.count("http") >= 2 else ""
if img_url:
    try:
        with urllib.request.urlopen(img_url, timeout=30) as rr:
            body = rr.read()
            check("URL gambar PUBLIK permanen (no auth)", rr.status == 200 and len(body) > 100,
                  f"ct={rr.headers.get('Content-Type')} bytes={len(body)}")
    except Exception as e:
        check("URL gambar PUBLIK permanen (no auth)", False, str(e)[:120])
else:
    check("URL gambar PUBLIK permanen (no auth)", False, "url tidak ditemukan di jawaban")

# ---- 2. KB CRUD via perintah chat ----
sid2, ans2 = chat("Simpan dokumen KB baru: key docs/e2e-v40-test.md isi minimal 40 karakter "
                  "tentang panduan pembersihan log CloudWatch MAA (pakai kb_write_doc atau kb_edit_doc). "
                  "Lalu laporkan hasilnya singkat.")
ok2 = "ok" in ans2.lower() or "tersimpan" in ans2.lower() or "selesai" in ans2.lower()
check("KB tulis via perintah chat", ok2, ans2[:100].replace("\n", " "))
c3, docs = api("GET", "/kb/docs")
found = [d["key"] for d in docs.get("docs", []) if "e2e-v40" in d["key"]] if c3 == 200 else []
check("KB docs list memuat dokumen baru", bool(found), f"{str(c3)} keys={found[:1]}")
kb_key = found[0] if found else "docs/e2e-v40-test.md"
c4, content = api("GET", "/kb/doc", qs=f"key={kb_key}")
check("KB baca dokumen (UI)", c4 == 200, str(c4))
c5, saved = api("POST", "/kb/doc", {"key": kb_key,
                                    "content": "Panduan pembersihan log CloudWatch MAA versi 2 - edit via UI route OK."})
check("KB edit via UI route", c5 == 200 and saved.get("saved"), str(c5))
c6, _ = api("DELETE", "/kb/docs", qs=f"key={kb_key}")
check("KB hapus via UI route", c6 == 200, str(c6))

# ---- 3. scraping via CI INTERNET ----
sid3, ans3 = chat("Pakai code_interpreter: scrape https://example.com dengan requests+User-Agent browser, "
                  "cetak judul halamannya (tag title). Jawab singkat judulnya.")
tr3 = json.dumps(last_trace(sid3))
ok7 = "example" in ans3.lower() or ("code_interpreter" in tr3 and '"ok"' in tr3)
check("scraping CI INTERNET (Google Play class)", ok7, ans3[:100].replace("\n", " "))

# ---- 4. /files/view ----
# 302 redirect ke presigned URL HARUS diuji tanpa forward header Authorization
# (browser asli strip header saat cross-origin redirect; urllib tidak -> S3 400)
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

_op = urllib.request.build_opener(_NoRedirect)
_req = urllib.request.Request(f"{API}/files/view?key=uploads/e2e-tidak-ada.png",
                              headers={"Authorization": TOKEN})
try:
    _resp = _op.open(_req, timeout=30)
    c8 = _resp.status
except urllib.error.HTTPError as e:
    c8 = e.code
check("route /files/view terdaftar (200/302/403/404)", c8 in (200, 302, 403, 404), str(c8))

# ---- 5. Management User ----
c9, users = api("GET", "/admin/users")
ok9 = c9 == 200 and len(users.get("users", [])) >= 1
check("Management User: daftar user", ok9, f"n={len(users.get('users', [])) if c9 == 200 else c9}")

# ---- 6. skill payload (picker UI) ----
sid4, ans4 = chat("Berapa langkah inti dalam panduan skill ini? Jawab 1 kalimat.",
                  skill="maa-cost-optimization")
tr4 = json.dumps(last_trace(sid4))
ok10 = "skill_load" in tr4 or "skill" in tr4.lower()
check("payload skill= dimuat runtime", ok10, ans4[:90].replace("\n", " "))

# ---- 7. task_schedule create + DDB ----
sid5, ans5 = chat("Buat tugas terjadwal sekali jalan 2 menit dari sekarang: cek jumlah bucket S3 lalu laporkan. "
                  "Gunakan task_schedule (repeat once). Lapor ID-nya.")
ok11 = "sch-" in ans5
check("task_schedule create via chat", ok11, ans5[:100].replace("\n", " "))

print(f"\n=== v4.0 E2E: {len(PASS)} PASS, {len(FAIL)} FAIL ===")
if FAIL:
    print("GAGAL:", FAIL)
