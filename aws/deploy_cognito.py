#!/usr/bin/env python3
"""MAA AWS Agent - Task 4: Cognito User Pool with mandatory TOTP MFA.
Admin-created demo user, strong password policy, no self-signup."""
import json
import secrets
import string
import sys
import time

import boto3

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from lib_common import ACCOUNT_ID, REGION, log, load_state, save_state

st = load_state()
c = boto3.client("cognito-idp", region_name=REGION)

POOL_NAME = "maa-agent-users"

# ---------------------------------------------------------------- User Pool
if st.get("user_pool_id"):
    log(f"= user pool exists: {st['user_pool_id']}")
else:
    resp = c.create_user_pool(
        PoolName=POOL_NAME,
        Policies={
            "PasswordPolicy": {
                "MinimumLength": 12,
                "RequireUppercase": True,
                "RequireLowercase": True,
                "RequireNumbers": True,
                "RequireSymbols": True,
                "TemporaryPasswordValidityDays": 7,
            }
        },
        # Admin-created users only - no self-signup for a full-authority agent
        AdminCreateUserConfig={"AllowAdminCreateUserOnly": True},
        MfaConfiguration="OFF",  # enabled via update_user_pool (TOTP) right after
        DeletionProtection="ACTIVE",
        UsernameConfiguration={"CaseSensitive": False},
        UserPoolTags={"Project": "maa-agent"},
    )
    pool_id = resp["UserPool"]["Id"]
    # Enable TOTP MFA (REQUIRED) - this API version uses SetUserPoolMfaConfig
    c.set_user_pool_mfa_config(
        UserPoolId=pool_id,
        SoftwareTokenMfaConfiguration={"Enabled": True},
        MfaConfiguration="ON",
    )
    st["user_pool_id"] = pool_id
    save_state(st)
    log(f"+ user pool created (TOTP MFA REQUIRED): {pool_id}")

pool_id = st["user_pool_id"]
pool_arn = f"arn:aws:cognito-idp:{REGION}:{ACCOUNT_ID}:userpool/{pool_id}"
st["user_pool_arn"] = pool_arn

# ---------------------------------------------------------------- App Client
if st.get("app_client_id"):
    log(f"= app client exists: {st['app_client_id']}")
else:
    client = c.create_user_pool_client(
        UserPoolId=pool_id,
        ClientName="maa-web-client",
        GenerateSecret=False,
        ExplicitAuthFlows=[
            "ALLOW_USER_PASSWORD_AUTH",
            "ALLOW_USER_SRP_AUTH",
            "ALLOW_REFRESH_TOKEN_AUTH",
        ],
        PreventUserExistenceErrors="ENABLED",
        AccessTokenValidity=60,
        IdTokenValidity=60,
        RefreshTokenValidity=30,  # days
        TokenValidityUnits={"AccessToken": "minutes", "IdToken": "minutes", "RefreshToken": "days"},
        ReadAttributes=["email", "preferred_username"],
        WriteAttributes=["email", "preferred_username"],
    )
    st["app_client_id"] = client["UserPoolClient"]["ClientId"]
    save_state(st)
    log(f"+ app client created: {st['app_client_id']}")

# ---------------------------------------------------------------- Admin user
USERNAME = "architect"
log("= preparing admin demo user")
# strong random password (delivered to user at the end)
alphabet = string.ascii_letters + string.digits
symbols = "!@#$%^&*()-_=+"
password = (
    "".join(secrets.choice(alphabet) for _ in range(10))
    + secrets.choice(string.ascii_uppercase)
    + secrets.choice(string.ascii_lowercase)
    + secrets.choice(string.digits)
    + secrets.choice(symbols)
)
password = "".join(secrets.SystemRandom().sample(password, len(password)))

try:
    c.admin_create_user(
        UserPoolId=pool_id,
        Username=USERNAME,
        MessageAction="SUPPRESS",
        UserAttributes=[{"Name": "email", "Value": "architect@maa.internal"},
                        {"Name": "email_verified", "Value": "true"}],
    )
    log(f"+ user '{USERNAME}' created")
except Exception as e:
    if "UserExistsException" in str(e):
        log(f"= user '{USERNAME}' exists")
    else:
        raise

c.admin_set_user_password(
    UserPoolId=pool_id, Username=USERNAME, Password=password, Permanent=True
)
log(f"+ permanent password set for '{USERNAME}'")

creds = {"username": USERNAME, "password": password,
         "user_pool_id": pool_id, "app_client_id": st["app_client_id"]}
with open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "maa-user-credentials.json"), "w") as f:
    json.dump(creds, f, indent=2)
log("credentials saved -> <aws dir>/maa-user-credentials.json")

st["demo_username"] = USERNAME
save_state(st)
log("=== COGNITO DEPLOY COMPLETE ===")
