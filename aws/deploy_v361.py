#!/usr/bin/env python3
"""MAA AWS Agent - v3.6.1: OAuth popup login konektor + tipe baru (GCS/BigQuery/S3).

Yang dipasang (idempotent):
  1. IAM edge role: + kms:Encrypt (seal secret konektor) utk key app
  2. Edge Lambda: kode baru (handler.py + connectors.py + paramiko vendor) +
     env MAA_KMS_KEY_ID / MAA_KMS_REGION / OAUTH_STATE_SECRET / MAA_FRONTEND_ORIGIN
  3. API GW routes: /connectors/oauth/settings GET|POST, /connectors/oauth/start GET,
     /connectors/oauth/exchange POST (+ OPTIONS CORS)
  4. state.json: oauth_state_secret (persist utk redeploy berikutnya)

Runtime diperbarui via deploy_runtime_connectors.py (main.py + connectors.py baru).
Frontend diperbarui via deploy_amplify.py (manual build - enableAutoBuild=False).

Pakai: source ../scripts/awsenv.sh && python3 aws/deploy_v361.py
"""
import io
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile

import boto3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_common import REGION, log, load_state, save_state

HERE = os.path.dirname(os.path.abspath(__file__))
EDGE_ROLE = "maa-agent-edge-role"
EDGE_FN = "maa-agent-edge"

st = load_state()
api_id = st["api_id"]

# ------------------------------------------------- 1. IAM: kms:Encrypt utk edge
log("=== 1/4 IAM edge role: + kms:Encrypt ===")
iam = boto3.client("iam")
pol = iam.get_role_policy(RoleName=EDGE_ROLE, PolicyName="maa-agent-edge-policy")["PolicyDocument"]
stmt_kms = next((s for s in pol["Statement"] if any("kms:" in a for a in s.get("Action", []))), None)
if stmt_kms:
    acts = set(stmt_kms.get("Action", []))
    need = {"kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"}
    if need.issubset(acts):
        log("  = policy KMS sudah lengkap")
    else:
        acts |= need
        stmt_kms["Action"] = sorted(acts)
        iam.put_role_policy(RoleName=EDGE_ROLE, PolicyName="maa-agent-edge-policy",
                            PolicyDocument=json.dumps(pol))
        log("  + policy KMS diperbarui (Encrypt ditambah)")
else:
    stmt = {"Sid": "KMSConnectorSecrets", "Effect": "Allow",
            "Action": ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"],
            "Resource": [st["kms_arn"]]}
    pol["Statement"].append(stmt)
    iam.put_role_policy(RoleName=EDGE_ROLE, PolicyName="maa-agent-edge-policy",
                        PolicyDocument=json.dumps(pol))
    log("  + statement KMS dibuat")

# ------------------------------------------------- 2. edge lambda kode + env
log("=== 2/4 Edge Lambda kode + env (OAuth konektor) ===")
with tempfile.TemporaryDirectory() as td:
    pkg = os.path.join(td, "pkg")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-t", pkg,
                        "--no-deps", "paramiko", "cryptography", "bcrypt", "pynacl", "cffi", "pycparser"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        log("  pip vendor gagal (lanjut tanpa SFTP): " + (r.stderr or "")[-200:])
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in ("handler.py", "connectors.py"):
            z.write(os.path.join(HERE, "lambda_edge", fn), fn)
        for base, _, files in os.walk(pkg):
            for f in files:
                full = os.path.join(base, f)
                z.write(full, os.path.relpath(full, pkg))
    log(f"  zip kode: {zbuf.tell()/1e6:.1f} MB")
    s3 = boto3.client("s3", region_name=REGION)
    art = st["art_bucket"]
    skey = f"code/edge-{uuid.uuid4().hex[:8]}.zip"
    s3.put_object(Bucket=art, Key=skey, Body=zbuf.getvalue(),
                  ServerSideEncryption="aws:kms", SSEKMSKeyId=st["kms_key_id"],
                  ContentType="application/zip")

lam = boto3.client("lambda", region_name=REGION)
env = lam.get_function_configuration(FunctionName=EDGE_FN)["Environment"]["Variables"]
env["CONNECTORS_TABLE"] = st.get("connectors_table", "maa-connectors")
env["MAA_KMS_KEY_ID"] = st["kms_key_id"]
env["MAA_KMS_REGION"] = REGION
if not env.get("OAUTH_STATE_SECRET"):
    # sumber kebenaran = env Lambda (tidak disimpan ke git); buat bila belum ada
    env["OAUTH_STATE_SECRET"] = secrets.token_hex(32)
if not env.get("MAA_FRONTEND_ORIGIN"):
    env["MAA_FRONTEND_ORIGIN"] = (st.get("amplify_url") or "").rstrip("/")
for attempt in range(10):
    try:
        lam.update_function_code(FunctionName=EDGE_FN, S3Bucket=art, S3Key=skey)
        while lam.get_function_configuration(FunctionName=EDGE_FN)["LastUpdateStatus"] == "InProgress":
            time.sleep(3)
        lam.update_function_configuration(FunctionName=EDGE_FN,
                                          Timeout=120, MemorySize=512,
                                          Environment={"Variables": env})
        while lam.get_function_configuration(FunctionName=EDGE_FN)["LastUpdateStatus"] == "InProgress":
            time.sleep(3)
        break
    except lam.exceptions.ResourceConflictException:
        log(f"  update in progress, retry {attempt+1}/10")
        time.sleep(6)
log(f"  = {EDGE_FN} kode+env diperbarui (OAUTH_STATE_SECRET={'set' if env.get('OAUTH_STATE_SECRET') else 'KOSONG'})")

# ------------------------------------------------- 3. API GW routes OAuth
log("=== 3/4 API GW routes OAuth konektor ===")
apig = boto3.client("apigateway", region_name=REGION)
auths = apig.get_authorizers(restApiId=api_id)["items"]
auth_id = next((a["id"] for a in auths if a["name"] == "maa-cognito-authorizer"), None)
fn_arn = lam.get_function(FunctionName=EDGE_FN)["Configuration"]["FunctionArn"]

resources = {r["path"]: r["id"] for r in apig.get_resources(restApiId=api_id, limit=400)["items"]}
ROUTES = [
    ("/connectors/oauth/settings", ["GET", "POST", "OPTIONS"]),
    ("/connectors/oauth/start", ["GET", "OPTIONS"]),
    ("/connectors/oauth/exchange", ["POST", "OPTIONS"]),
]
for path, _ in ROUTES:
    cur = ""
    for part in path.strip("/").split("/"):
        parent, cur = cur, f"{cur}/{part}"
        if cur not in resources:
            try:
                resources[cur] = apig.create_resource(restApiId=api_id, parentId=resources[parent],
                                                      pathPart=part)["id"]
            except apig.exceptions.ConflictException:
                time.sleep(2)
                for r2 in apig.get_resources(restApiId=api_id, limit=400)["items"]:
                    resources[r2["path"]] = r2["id"]
CORS_HEADERS = {
    "method.response.header.Access-Control-Allow-Origin": "'*'",
    "method.response.header.Access-Control-Allow-Headers": "'Authorization,Content-Type'",
    "method.response.header.Access-Control-Allow-Methods": "'GET,POST,OPTIONS'",
}


def _safe(fn_, **kw):
    try:
        fn_(**kw)
        return True
    except (apig.exceptions.ConflictException, apig.exceptions.NotFoundException):
        return False


uri = f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/{fn_arn}/invocations"
for path, verbs in ROUTES:
    rid = resources[path]
    for verb in verbs:
        kw = dict(restApiId=api_id, resourceId=rid, httpMethod=verb, apiKeyRequired=False)
        if verb == "OPTIONS":
            kw["authorizationType"] = "NONE"
        else:
            kw["authorizationType"] = "COGNITO_USER_POOLS"
            kw["authorizerId"] = auth_id
        _safe(apig.put_method, **kw)
        if verb == "OPTIONS":
            _safe(apig.put_integration, restApiId=api_id, resourceId=rid, httpMethod="OPTIONS",
                  type="AWS_PROXY", integrationHttpMethod="POST", uri=uri)
            _safe(apig.put_method_response, restApiId=api_id, resourceId=rid,
                  httpMethod="OPTIONS", statusCode="200")
            continue
        _safe(apig.put_integration, restApiId=api_id, resourceId=rid, httpMethod=verb,
              type="AWS_PROXY", integrationHttpMethod="POST", uri=uri)
        _safe(apig.put_method_response, restApiId=api_id, resourceId=rid, httpMethod=verb,
              statusCode="200",
              responseParameters={f"method.response.header.{k}": False for k in CORS_HEADERS})
        _safe(apig.put_integration_response, restApiId=api_id, resourceId=rid, httpMethod=verb,
              statusCode="200", responseTemplates={"application/json": ""},
              responseParameters={f"method.response.header.{k}": v for k, v in CORS_HEADERS.items()})
log("  + methods & integrations OAuth terpasang")

# ------------------------------------------------- 4. deployment
log("=== 4/4 deployment API GW ===")
STAGE = st["api_url"].rsplit("/", 1)[-1] or "v1"
try:
    apig.create_deployment(restApiId=api_id, stageName=STAGE)
    log(f"  + deployment stage '{STAGE}' dibuat (rute OAuth aktif)")
except Exception as e:
    log(f"  ! deployment warn: {str(e)[:150]}")
log(f"API: GET|POST /{STAGE}/connectors/oauth/settings | GET /{STAGE}/connectors/oauth/start"
    f" | POST /{STAGE}/connectors/oauth/exchange")
log("=== DEPLOY V3.6.1 (EDGE+APIGW) SELESAI — lanjut: deploy_runtime_connectors.py & deploy_amplify.py ===")
