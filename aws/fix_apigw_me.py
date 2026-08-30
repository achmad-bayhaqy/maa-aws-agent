#!/usr/bin/env python3
"""Fix API GW v3: buat /me (GET+OPTIONS) di root, hapus resource salah tempat
/admin/signout/me. OPTIONS pakai AWS_PROXY (lambda balas CORS) sesuai fix task-12."""
import json
import sys
import time

import boto3

sys.path.insert(0, "/home/z/my-project/aws")
from lib_common import load_state, save_state  # noqa: E402

REGION = "us-east-1"
apig = boto3.client("apigateway", region_name=REGION)
st = load_state()
api_id = st["api_id"]
fn_arn = boto3.client("lambda", region_name=REGION).get_function(
    FunctionName="maa-agent-edge")["Configuration"]["FunctionArn"]


def log(m):
    print(f"[fix] {m}", flush=True)


res = {r["path"]: r for r in apig.get_resources(restApiId=api_id, limit=400)["items"]}
root_id = res["/"]["id"]

# 1) hapus resource salah tempat /admin/signout/me
if "/admin/signout/me" in res:
    apig.delete_resource(restApiId=api_id, resourceId=res["/admin/signout/me"]["id"])
    log("deleted bogus resource /admin/signout/me")

# 2) pastikan /me di root
me_id = res.get("/me", {}).get("id")
if not me_id:
    me_id = apig.create_resource(restApiId=api_id, parentId=root_id, pathPart="me")["id"]
    log(f"created /me resource: {me_id}")
else:
    log(f"/me exists: {me_id}")

# authorizer
auths = apig.get_authorizers(restApiId=api_id)["items"]
auth_id = next((a["id"] for a in auths if a["name"] == "maa-cognito-authorizer"), None)
assert auth_id, "authorizer maa-cognito-authorizer tidak ditemukan"

uri = f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/{fn_arn}/invocations"


def _safe(fn, **kw):
    try:
        fn(**kw)
        return True
    except (apig.exceptions.ConflictException, apig.exceptions.NotFoundException):
        return False


# GET /me (Cognito + AWS_PROXY)
_safe(apig.put_method, restApiId=api_id, resourceId=me_id, httpMethod="GET",
      authorizationType="COGNITO_USER_POOLS", authorizerId=auth_id,
      apiKeyRequired=False)
_safe(apig.put_integration, restApiId=api_id, resourceId=me_id, httpMethod="GET",
      type="AWS_PROXY", integrationHttpMethod="POST", uri=uri)
_safe(apig.put_method_response, restApiId=api_id, resourceId=me_id, httpMethod="GET",
      statusCode="200")

# OPTIONS /me (AWS_PROXY — lambda mengembalikan header CORS)
_safe(apig.put_method, restApiId=api_id, resourceId=me_id, httpMethod="OPTIONS",
      authorizationType="NONE", apiKeyRequired=False)
_safe(apig.put_integration, restApiId=api_id, resourceId=me_id, httpMethod="OPTIONS",
      type="AWS_PROXY", integrationHttpMethod="POST", uri=uri)
_safe(apig.put_method_response, restApiId=api_id, resourceId=me_id,
      httpMethod="OPTIONS", statusCode="200")

# 3) cek OPTIONS route lain: pastikan AWS_PROXY (bukan MOCK) — mock tanpa CORS
fixed = 0
for r in apig.get_resources(restApiId=api_id, limit=400)["items"]:
    if r["path"] == "/":
        continue
    for m in r.get("resourceMethods", {}):
        if m != "OPTIONS":
            continue
        try:
            integ = apig.get_integration(restApiId=api_id, resourceId=r["id"],
                                         httpMethod="OPTIONS")
            if integ.get("type") == "MOCK":
                apig.delete_integration(restApiId=api_id, resourceId=r["id"],
                                        httpMethod="OPTIONS")
                _safe(apig.put_method, restApiId=api_id, resourceId=r["id"],
                      httpMethod="OPTIONS", authorizationType="NONE", apiKeyRequired=False)
                _safe(apig.put_integration, restApiId=api_id, resourceId=r["id"],
                      httpMethod="OPTIONS", type="AWS_PROXY",
                      integrationHttpMethod="POST", uri=uri)
                _safe(apig.put_method_response, restApiId=api_id, resourceId=r["id"],
                      httpMethod="OPTIONS", statusCode="200")
                fixed += 1
                log(f"mock->aws_proxy: {r['path']}")
        except apig.exceptions.NotFoundException:
            # OPTIONS tanpa integration -> tambahkan
            _safe(apig.put_method, restApiId=api_id, resourceId=r["id"],
                  httpMethod="OPTIONS", authorizationType="NONE", apiKeyRequired=False)
            _safe(apig.put_integration, restApiId=api_id, resourceId=r["id"],
                  httpMethod="OPTIONS", type="AWS_PROXY", integrationHttpMethod="POST",
                  uri=uri)
            _safe(apig.put_method_response, restApiId=api_id, resourceId=r["id"],
                  httpMethod="OPTIONS", statusCode="200")
            fixed += 1
            log(f"added missing OPTIONS: {r['path']}")
log(f"options normalized: {fixed}")

# 4) deploy ulang stage v1
dep = apig.create_deployment(restApiId=api_id, stageName="v1")
log(f"deployment: {dep['id']}")
save_state(st)
log("=== APIGW /me FIX COMPLETE ===")
