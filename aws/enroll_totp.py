#!/usr/bin/env python3
"""Enroll TOTP utk user demo architect + simpan secret ke maa-user-credentials.json."""
import json
import sys
import time

import boto3
import pyotp

CRED_PATH = "/home/z/my-project/aws/maa-user-credentials.json"
creds = json.load(open(CRED_PATH))
c = boto3.client("cognito-idp")

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
    totp = pyotp.TOTP(secret)
    for attempt in range(4):
        try:
            v = c.verify_software_token(Session=session, UserCode=totp.now())
            session = v.get("Session", "")
            print("TOTP verified")
            break
        except c.exceptions.ExpiredCodeException:
            print("code expired, retry window baru...")
            time.sleep(20)
    else:
        sys.exit("verify gagal")
    # lengkapi challenge MFA_SETUP -> login penuh
    r2 = c.respond_to_auth_challenge(
        ClientId=creds["app_client_id"], ChallengeName="MFA_SETUP", Session=session,
        ChallengeResponses={"USERNAME": creds["username"], "SMS_OTP_CODE": "-",
                            "SOFTWARE_TOKEN_MFA_CODE": totp.now()})
    print("login penuh OK, access token diterima")
elif name in ("SOFTWARE_TOKEN_MFA", "SMS_MFA"):
    print("user sudah punya TOTP terdaftar")
    sys.exit(0)
else:
    print("challenge tak terduga:", name)
    sys.exit(1)

creds["totp_secret"] = secret
with open(CRED_PATH, "w") as f:
    json.dump(creds, f, indent=2)
print("totp_secret disimpan ->", CRED_PATH)
