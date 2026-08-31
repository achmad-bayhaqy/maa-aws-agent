#!/usr/bin/env python3
"""Enroll TOTP user architect (tanpa pyotp — implementasi HMAC murni)."""
import base64
import hashlib
import hmac
import json
import os
import struct
import time

import boto3

HERE = os.path.dirname(os.path.abspath(__file__))
CRED_PATH = os.path.join(HERE, "maa-user-credentials.json")
creds = json.load(open(CRED_PATH))
c = boto3.client("cognito-idp", region_name="us-east-1")


def totp(secret_b32):
    key = base64.b32decode(secret_b32 + "=" * ((8 - len(secret_b32) % 8) % 8))
    counter = int(time.time() // 30)
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** 6:06d}"


r = c.initiate_auth(
    ClientId=creds["app_client_id"],
    AuthFlow="USER_PASSWORD_AUTH",
    AuthParameters={"USERNAME": creds["username"], "PASSWORD": creds["password"]},
)
name = r.get("ChallengeName", "")
session = r.get("Session", "")
print("challenge:", name)

if name == "MFA_SETUP":
    assoc = c.associate_software_token(Session=session)
    secret = assoc["SecretCode"]
    session = assoc.get("Session", session)
    for attempt in range(4):
        try:
            v = c.verify_software_token(Session=session, UserCode=totp(secret))
            session = v.get("Session", "")
            print("TOTP verified")
            break
        except Exception as e:
            print("retry:", str(e)[:80])
            time.sleep(20)
    else:
        raise SystemExit("verify gagal")
    r2 = c.respond_to_auth_challenge(
        ClientId=creds["app_client_id"],
        ChallengeName="MFA_SETUP",
        Session=session,
        ChallengeResponses={
            "USERNAME": creds["username"],
            "SOFTWARE_TOKEN_MFA_CODE": totp(secret),
        },
    )
    print("login akhir:", "AuthenticationResult" in r2)
    # set sebagai preferred MFA
    try:
        c.admin_set_user_mfa_preference(
            UserPoolId=creds["user_pool_id"], Username=creds["username"],
            SoftwareTokenMfaSettings={"Enabled": True, "PreferredMfa": True})
        print("preferred MFA: TOTP")
    except Exception as e:
        print("mfa pref warn:", str(e)[:100])
elif name in ("SOFTWARE_TOKEN_MFA",):
    print("user sudah ter-enroll TOTP — masukkan secret lama dari credentials file")
    raise SystemExit(1)
else:
    print("AuthenticationResult" in r and "login langsung OK (tanpa MFA)" or f"challenge tak terduga: {name}")
    if "AuthenticationResult" in r:
        secret = None
    else:
        raise SystemExit(1)

creds["totp_secret"] = secret
with open(CRED_PATH, "w") as f:
    json.dump(creds, f, indent=2)
print("totp_secret disimpan ->", CRED_PATH)
