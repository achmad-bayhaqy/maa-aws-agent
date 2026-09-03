#!/usr/bin/env python3
"""MAA AWS Agent - v3.6: deploy fitur Konektor (data source ala Claude AI).

Yang dipasang (idempotent):
  1. Tabel DynamoDB maa-connectors (pk connectorId)
  2. IAM edge role: + akses dynamodb utk tabel konektor
  3. Edge Lambda env CONNECTORS_TABLE + kode baru (handler.py + connectors.py
     + paramiko ter-vendor utk test/browse SFTP) via S3
  4. API GW routes: /connectors GET|POST|DELETE, /connectors/test POST,
     /connectors/update POST (+OPTIONS CORS)
  5. state.json: connectors_table

Pakai: source ../scripts/awsenv.sh && python3 aws/deploy_connectors.py
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile

import boto3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_common import ACCOUNT_ID, REGION, log, load_state, save_state

HERE = os.path.dirname(os.path.abspath(__file__))
EDGE_ROLE = "maa-agent-edge-role"
EDGE_FN = "maa-agent-edge"
TABLE = "maa-connectors"

st = load_state()
api_id = st["api_id"]
API_ROOT = st["api_url"].rsplit("/", 1)[0]  # .../prolambda-stage root

# ---------------------------------------------------------------- 1. DDB table
log("=== 1/5 Tabel DynamoDB " + TABLE + " ===")
ddb = boto3.client("dynamodb", region_name=REGION)
try:
    ddb.describe_table(TableName=TABLE)
    log("  = tabel sudah ada")
except ddb.exceptions.ResourceNotFoundException:
    ddb.create_table(
        TableName=TABLE,
        KeySchema=[{"AttributeName": "connectorId", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "connectorId", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
        Tags=[{"Key": "Project", "Value": "maa-agent"}])
    ddb.get_waiter("table_exists").wait(TableName=TABLE)
    log("  + tabel dibuat")
st["connectors_table"] = TABLE
save_state(st)

# ---------------------------------------------------------------- 2. IAM policy
log("=== 2/5 IAM edge role ===")
iam = boto3.client("iam")
table_arn = f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/{TABLE}"
pol = iam.get_role_policy(RoleName=EDGE_ROLE, PolicyName="maa-agent-edge-policy")["PolicyDocument"]
stmt_ddb = next((s for s in pol["Statement"] if any("dynamodb:" in a for a in s.get("Action", []))), None)
if stmt_ddb:
    acts = set(stmt_ddb.get("Action", []))
    acts.add("dynamodb:DeleteItem")  # v3.6: hapus konektor
    stmt_ddb["Action"] = sorted(acts)
if stmt_ddb and table_arn not in stmt_ddb.get("Resource", []):
    stmt_ddb["Resource"] = list(stmt_ddb.get("Resource", [])) + [table_arn]
if "dynamodb:DeleteItem" in stmt_ddb.get("Action", []) and table_arn in stmt_ddb.get("Resource", []):
    iam.put_role_policy(RoleName=EDGE_ROLE, PolicyName="maa-agent-edge-policy",
                        PolicyDocument=json.dumps(pol))
    log("  + policy diperbarui (DeleteItem + tabel konektor)")
else:
    log("  = policy sudah lengkap")

# ---------------------------------------------------------------- 3. kode edge (+paramiko)
log("=== 3/5 Kode edge Lambda (vendor paramiko utk SFTP) ===")
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
                z.write(full, os.path.relpath(full, pkg))  # root zip: paramiko/..., bukan pkg/...
    zsize = zbuf.tell()
    log(f"  zip kode: {zsize/1e6:.1f} MB")
    s3 = boto3.client("s3", region_name=REGION)
    art = st["art_bucket"]
    skey = f"code/edge-{uuid.uuid4().hex[:8]}.zip"
    # bucket menolak PutObject non-KMS utk principal non maa-agent-* -> wajib SSE-KMS
    s3.put_object(Bucket=art, Key=skey, Body=zbuf.getvalue(),
                  ServerSideEncryption="aws:kms", SSEKMSKeyId=st["kms_key_id"],
                  ContentType="application/zip")

lam = boto3.client("lambda", region_name=REGION)
env = lam.get_function_configuration(FunctionName=EDGE_FN)["Environment"]["Variables"]
env["CONNECTORS_TABLE"] = TABLE
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
log(f"  = {EDGE_FN} kode+env diperbarui (timeout 120s utk SFTP lambat)")

# ---------------------------------------------------------------- 4. API GW routes
log("=== 4/5 API GW routes konektor ===")
apig = boto3.client("apigateway", region_name=REGION)
auths = apig.get_authorizers(restApiId=api_id)["items"]
auth_id = next((a["id"] for a in auths if a["name"] == "maa-cognito-authorizer"), None)
fn_arn = lam.get_function(FunctionName=EDGE_FN)["Configuration"]["FunctionArn"]

root_id = apig.get_resources(restApiId=api_id, limit=1)["items"][0]["id"]
resources = {r["path"]: r["id"] for r in apig.get_resources(restApiId=api_id, limit=400)["items"]}
resources[""] = root_id
ROUTES = [
    ("/connectors", ["GET", "POST", "DELETE", "OPTIONS"]),
    ("/connectors/test", ["POST", "OPTIONS"]),
    ("/connectors/update", ["POST", "OPTIONS"]),
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
                for r in apig.get_resources(restApiId=api_id, limit=400)["items"]:
                    resources[r["path"]] = r["id"]
CORS_HEADERS = {
    "method.response.header.Access-Control-Allow-Origin": "'*'",
    "method.response.header.Access-Control-Allow-Headers": "'Authorization,Content-Type'",
    "method.response.header.Access-Control-Allow-Methods": "'GET,POST,DELETE,OPTIONS'",
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
log("  + methods & integrations terpasang")

# ---------------------------------------------------------------- 5. deployment
log("=== 5/5 deployment API GW + selesai ===")
# permission invoke lama (apigw-invoke) scope .../{api_id}/*/* sudah mencakup path baru
STAGE = st["api_url"].rsplit("/", 1)[-1] or "v1"
try:
    apig.create_deployment(restApiId=api_id, stageName=STAGE)
    log(f"  + deployment stage '{STAGE}' dibuat (rute baru aktif)")
except Exception as e:
    log(f"  ! deployment warn: {str(e)[:150]}")
log(f"API: GET|POST|DELETE /{STAGE}/connectors | POST /{STAGE}/connectors/test | POST /{STAGE}/connectors/update")
