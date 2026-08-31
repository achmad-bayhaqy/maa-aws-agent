#!/usr/bin/env python3
"""Deploy fix v3.3 (API GW DELETE route + edge lambda code/env).
Runtime sendiri di-deploy via deploy_runtime_v3.py (bentuk API benar + smoke)."""
import io
import sys
import time
import zipfile

import boto3

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from lib_common import log, load_state, save_state  # noqa: E402

REGION = "us-east-1"
st = load_state()
apig = boto3.client("apigateway", region_name=REGION)
lam = boto3.client("lambda", region_name=REGION)

# ---------------------------------------------------------------- 1. API GW: DELETE /chat/sessions
api_id = st["api_id"]
res = {r["path"]: r for r in apig.get_resources(restApiId=api_id, limit=400)["items"]}
sess_id = res["/chat/sessions"]["id"]
methods = apig.get_resource(restApiId=api_id, resourceId=sess_id).get("resourceMethods", {})
if "DELETE" not in methods:
    auths = apig.get_authorizers(restApiId=api_id)["items"]
    auth_id = next(a["id"] for a in auths if a["name"] == "maa-cognito-authorizer")
    fn_arn = lam.get_function(FunctionName="maa-agent-edge")["Configuration"]["FunctionArn"]
    uri = f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/{fn_arn}/invocations"
    apig.put_method(restApiId=api_id, resourceId=sess_id, httpMethod="DELETE",
                    authorizationType="COGNITO_USER_POOLS", authorizerId=auth_id,
                    apiKeyRequired=False)
    apig.put_integration(restApiId=api_id, resourceId=sess_id, httpMethod="DELETE",
                         type="AWS_PROXY", integrationHttpMethod="POST", uri=uri)
    apig.put_method_response(restApiId=api_id, resourceId=sess_id,
                             httpMethod="DELETE", statusCode="200")
    log("+ DELETE /chat/sessions created")
else:
    log("= DELETE /chat/sessions exists")

dep = apig.create_deployment(restApiId=api_id, stageName="v1")
log(f"stage v1 redeployed: {dep['id']}")

# ---------------------------------------------------------------- 2. Edge lambda
zbuf = io.BytesIO()
with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "lambda_edge", "handler.py"), "handler.py")
lam.update_function_code(FunctionName="maa-agent-edge", ZipFile=zbuf.getvalue())
while lam.get_function_configuration(FunctionName="maa-agent-edge")["LastUpdateStatus"] == "InProgress":
    time.sleep(2)
log("+ edge lambda code updated")

# ---------------------------------------------------------------- 3. env edge -> runtime terbaru
lam.update_function_configuration(
    FunctionName="maa-agent-edge",
    Environment={"Variables": {
        "RUNTIME_ARN": st["agent_runtime_arn"],
        "SESSIONS_TABLE": st["sessions_table"],
        "KB_BUCKET": st["kb_bucket"],
        "ART_BUCKET": st["art_bucket"],
        "KB_ID": st["kb_id"],
        "USER_POOL_ID": st["user_pool_id"],
        "KMS_KEY_ID": st["kms_key_id"],
        "CONF_TABLE": st["confirm_table"],
        "TRACE_LOG_GROUP": st.get("trace_log_group", "/maa/agent/trace"),
    }})
while lam.get_function_configuration(FunctionName="maa-agent-edge")["LastUpdateStatus"] == "InProgress":
    time.sleep(2)
log(f"+ edge env -> {st['agent_runtime_arn'][-20:]}")
log("=== DEPLOY V3.3 EDGE COMPLETE ===")
