#!/usr/bin/env python3
"""Setup user E2E v3.4: e2e-tester (superadmin, TOTP known-secret, password permanent).
Idempotent: hapus dulu jika ada, lalu create fresh. Tulis aws/maa-user-credentials.json."""
import base64
import hashlib
import hmac
import json
import os
import struct
import sys
import time

import boto3


def totp_now(secret_b32):
    key = base64.b32decode(secret_b32 + "=" * ((8 - len(secret_b32) % 8) % 8))
    counter = int(time.time() // 30)
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return f"{(struct.unpack('>I', h[o:o+4])[0] & 0x7FFFFFFF) % 10**6:06d}"


def wait_next_totp_window():
    """Tunggu sampai jendela TOTP 30s baru dimulai (+ buffer 2s)."""
    now = time.time()
    nxt = (int(now // 30) + 1) * 30
    wait = nxt - now + 2
    print(f"waiting {wait:.0f}s for fresh TOTP window...")
    time.sleep(wait)


HERE = os.path.dirname(os.path.abspath(__file__))
st = json.load(open(os.path.join(HERE, "state.json")))
POOL = st["user_pool_id"]
USERNAME = "e2e-tester"
PASSWORD = "E2e#Maav34!Global2026"

cog = boto3.client("cognito-idp", region_name=st["region"])

# 0) pastikan group superadmin ada
try:
    cog.get_group(GroupName="superadmin", UserPoolId=POOL)
except cog.exceptions.ResourceNotFoundException:
    cog.create_group(GroupName="superadmin", UserPoolId=POOL,
                     Description="MAA superadmin")
    print("group superadmin created")

# 1) hapus user lama bila ada
try:
    cog.admin_delete_user(UserPoolId=POOL, Username=USERNAME)
    print("old e2e-tester deleted")
    time.sleep(2)
except cog.exceptions.UserNotFoundException:
    pass
except Exception as e:
    print("delete warn:", str(e)[:120])

# 2) create + set password permanen
cog.admin_create_user(
    UserPoolId=POOL, Username=USERNAME,
    UserAttributes=[
        {"Name": "email", "Value": "e2e-tester@maa-agent.local"},
        {"Name": "email_verified", "Value": "true"},
        {"Name": "custom:role", "Value": "superadmin"},
    ],
    MessageAction="SUPPRESS")
cog.admin_set_user_password(UserPoolId=POOL, Username=USERNAME,
                            Password=PASSWORD, Permanent=True)
cog.admin_add_user_to_group(UserPoolId=POOL, Username=USERNAME, GroupName="superadmin")
print("user created + password set + superadmin group")

# 3) auth: USER_PASSWORD_AUTH -> MFA_SETUP -> Associate/VerifySoftwareToken -> tokens
r = cog.initiate_auth(AuthFlow="USER_PASSWORD_AUTH",
                      AuthParameters={"USERNAME": USERNAME, "PASSWORD": PASSWORD},
                      ClientId=st["app_client_id"])
chal = r.get("ChallengeName")
secret = None
if chal == "MFA_SETUP":
    sess = r["Session"]
    a = cog.associate_software_token(Session=sess)
    secret = a["SecretCode"]
    time.sleep(1)
    v = cog.verify_software_token(Session=a["Session"], UserCode=totp_now(secret))
    assert v["Status"] == "SUCCESS", v
    r = cog.respond_to_auth_challenge(
        ClientId=st["app_client_id"], ChallengeName="MFA_SETUP", Session=v["Session"],
        ChallengeResponses={"USERNAME": USERNAME, "ANSWER": "true"})
elif chal == "SOFTWARE_TOKEN_MFA":
    print("NOTE: user already had TOTP?? unexpected")
    sys.exit(1)

assert "AuthenticationResult" in r, json.dumps(r, default=str)[:300]
res = r["AuthenticationResult"]
print("auth OK; id_token len:", len(res["IdToken"]))

# 4) verifikasi login kedua: SOFTWARE_TOKEN_MFA dengan TOTP compute
wait_next_totp_window()
r2 = cog.initiate_auth(AuthFlow="USER_PASSWORD_AUTH",
                       AuthParameters={"USERNAME": USERNAME, "PASSWORD": PASSWORD},
                       ClientId=st["app_client_id"])
assert r2.get("ChallengeName") == "SOFTWARE_TOKEN_MFA", json.dumps(r2, default=str)[:300]
r3 = cog.respond_to_auth_challenge(
    ClientId=st["app_client_id"], ChallengeName="SOFTWARE_TOKEN_MFA",
    Session=r2["Session"],
    ChallengeResponses={"USERNAME": USERNAME,
                        "SOFTWARE_TOKEN_MFA_CODE": totp_now(secret)})
assert "AuthenticationResult" in r3
print("TOTP relogin OK")

creds = {"username": USERNAME, "password": PASSWORD, "totp_secret": secret,
         "role": "superadmin", "pool_id": POOL, "client_id": st["app_client_id"]}
path = os.path.join(HERE, "maa-user-credentials.json")
with open(path, "w") as f:
    json.dump(creds, f, indent=2)
print("saved:", path)
