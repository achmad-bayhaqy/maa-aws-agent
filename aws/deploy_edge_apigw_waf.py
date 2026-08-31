#!/usr/bin/env python3
"""MAA AWS Agent - Task 6: Edge Lambda (proxy) + API Gateway REST (Cognito authorizer,
CORS) + WAF WebACL x2 (rate-based, associated ke stage API & user pool Cognito)."""
import io
import json
import os
import sys
import time
import zipfile

import boto3

sys.path.insert(0, "/home/z/my-project/aws")
from lib_common import ACCOUNT_ID, REGION, log, load_state, save_state

st = load_state()
iam = boto3.client("iam")
lam = boto3.client("lambda", region_name=REGION)
apig = boto3.client("apigateway", region_name=REGION)
waf = boto3.client("wafv2", region_name=REGION)

EDGE_ROLE = "maa-agent-edge-role"
EDGE_FN = "maa-agent-edge"
API_NAME = "maa-agent-api"
STAGE = "v1"

# ---------------------------------------------------------------- IAM
trust = {"Version": "2012-10-17", "Statement": [
    {"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
try:
    role_arn = iam.get_role(RoleName=EDGE_ROLE)["Role"]["Arn"]
    log(f"= {EDGE_ROLE} exists")
except iam.exceptions.NoSuchEntityException:
    role_arn = iam.create_role(RoleName=EDGE_ROLE, AssumeRolePolicyDocument=json.dumps(trust),
                               Description="MAA agent edge proxy",
                               Tags=[{"Key": "Project", "Value": "maa-agent"}])["Role"]["Arn"]
    time.sleep(3)
    log(f"+ {EDGE_ROLE} created")

policy = {
    "Version": "2012-10-17",
    "Statement": [
        {"Sid": "Logs", "Effect": "Allow",
         "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
         "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT_ID}:*"},
        {"Sid": "SelfInvoke", "Effect": "Allow",
         "Action": ["lambda:InvokeFunction"],
         "Resource": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:{EDGE_FN}*"},
        {"Sid": "InvokeRuntime", "Effect": "Allow",
         "Action": ["bedrock-agentcore:InvokeAgentRuntime", "bedrock-agentcore:CallMcpGateway"],
         # data plane memvalidasi pada child resource runtime-endpoint/DEFAULT
         "Resource": f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT_ID}:runtime/*"},
        {"Sid": "Tables", "Effect": "Allow",
         "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
                    "dynamodb:Query", "dynamodb:Scan"],
         "Resource": [f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/{st['sessions_table']}",
                      f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/{st['sessions_table']}/index/*",
                      f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/{st['confirm_table']}"]},
        {"Sid": "TraceLogs", "Effect": "Allow",
         "Action": ["logs:GetLogEvents", "logs:DescribeLogStreams"],
         "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT_ID}:log-group:/maa/agent/trace:*"},
        {"Sid": "KbDocs", "Effect": "Allow",
         "Action": ["s3:ListBucket", "s3:GetBucketLocation", "s3:GetObject", "s3:PutObject",
                    "s3:DeleteObject"],
         "Resource": [f"arn:aws:s3:::{st['kb_bucket']}", f"arn:aws:s3:::{st['kb_bucket']}/*"]},
        {"Sid": "ArtifactsRW", "Effect": "Allow",
         "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
         "Resource": [f"arn:aws:s3:::{st['art_bucket']}",
                      f"arn:aws:s3:::{st['art_bucket']}/*"]},
        {"Sid": "KmsForPresign", "Effect": "Allow",
         "Action": ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"],
         "Resource": st["kms_arn"]},
        {"Sid": "KbSync", "Effect": "Allow",
         "Action": ["bedrock:ListDataSources", "bedrock:StartIngestionJob",
                    "bedrock:GetIngestionJob"],
         "Resource": f"arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:knowledge-base/{st.get('kb_id', '*')}"},
        {"Sid": "CognitoAdmin", "Effect": "Allow",
         "Action": ["cognito-idp:AdminUserGlobalSignOut", "cognito-idp:ListUsers",
                    "cognito-idp:AdminGetUser", "cognito-idp:AdminCreateUser",
                    "cognito-idp:AdminDeleteUser", "cognito-idp:AdminEnableUser",
                    "cognito-idp:AdminDisableUser", "cognito-idp:AdminUpdateUserAttributes"],
         "Resource": st["user_pool_arn"]},
    ],
}
iam.put_role_policy(RoleName=EDGE_ROLE, PolicyName="maa-agent-edge-policy",
                    PolicyDocument=json.dumps(policy))
log(f"  edge policy set")

# ---------------------------------------------------------------- Lambda
zbuf = io.BytesIO()
with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
    z.write("/home/z/my-project/aws/lambda_edge/handler.py", "handler.py")
env = {
    "RUNTIME_ARN": st["agent_runtime_arn"],
    "SESSIONS_TABLE": st["sessions_table"],
    "TRACES_TABLE": st["traces_table"],
    "KB_BUCKET": st["kb_bucket"],
    "ART_BUCKET": st["art_bucket"],
    "MODELS_KEY": "models/allowed-chat-models.json",
    "KB_ID": st.get("kb_id", ""),
    "USER_POOL_ID": st["user_pool_id"],
    "KMS_KEY_ID": st["kms_key_id"],
    "CONF_TABLE": st["confirm_table"],
    "TRACE_LOG_GROUP": st.get("trace_log_group", "/maa/agent/trace"),
}
try:
    fn = lam.get_function(FunctionName=EDGE_FN)
    for attempt in range(10):
        try:
            lam.update_function_code(FunctionName=EDGE_FN, ZipFile=zbuf.getvalue())
            while lam.get_function_configuration(FunctionName=EDGE_FN)["LastUpdateStatus"] == "InProgress":
                time.sleep(3)
            lam.update_function_configuration(
                FunctionName=EDGE_FN, Timeout=240, MemorySize=256,
                Environment={"Variables": env}, Description="MAA edge proxy v2")
            while lam.get_function_configuration(FunctionName=EDGE_FN)["LastUpdateStatus"] == "InProgress":
                time.sleep(3)
            break
        except lam.exceptions.ResourceConflictException:
            log(f"  lambda update in progress, retry {attempt+1}/10")
            time.sleep(6)
    log(f"= {EDGE_FN} updated")
except lam.exceptions.ResourceNotFoundException:
    fn = None
    for attempt in range(6):
        try:
            fn = lam.create_function(
                FunctionName=EDGE_FN,
                Runtime="python3.12",
                Role=role_arn,
                Handler="handler.lambda_handler",
                Code={"ZipFile": zbuf.getvalue()},
                Timeout=240,
                MemorySize=256,
                Environment={"Variables": env},
                Description="MAA AWS Agent edge proxy (API GW -> AgentCore Runtime)",
                Tags={"Project": "maa-agent"},
            )
            break
        except lam.exceptions.InvalidParameterValueException as e:
            if "cannot be assumed" in str(e) and attempt < 5:
                log(f"  role propagation lag, retry {attempt+1}/5 (15s)")
                time.sleep(15)
                continue
            raise
    while lam.get_function_configuration(FunctionName=EDGE_FN)["State"] != "Active":
        time.sleep(3)
    log(f"+ {EDGE_FN} created")
fn_arn = fn["FunctionArn"] if isinstance(fn, dict) and "FunctionArn" in fn else \
    boto3.client("lambda", region_name=REGION).get_function(FunctionName=EDGE_FN)["Configuration"]["FunctionArn"]
log(f"  lambda: {fn_arn}")

# ---------------------------------------------------------------- API Gateway
api_id = st.get("api_id")
if not api_id:
    api = apig.create_rest_api(
        name=API_NAME,
        endpointConfiguration={"types": ["REGIONAL"]},
        description="MAA AWS Agent API (Cognito authorizer + WAF)",
        tags={"Project": "maa-agent"},
    )
    api_id = api["id"]
    st["api_id"] = api_id
    save_state(st)
    log(f"+ REST API created: {api_id}")

root_id = apig.get_resources(restApiId=api_id)["items"][0]["id"]

# authorizer
auths = apig.get_authorizers(restApiId=api_id)["items"]
auth_id = next((a["id"] for a in auths if a["name"] == "maa-cognito-authorizer"), None)
if not auth_id:
    auth_id = apig.create_authorizer(
        restApiId=api_id,
        name="maa-cognito-authorizer",
        type="COGNITO_USER_POOLS",
        providerARNs=[st["user_pool_arn"]],
        identitySource="method.request.header.Authorization",
        authorizerResultTtlInSeconds=60,
    )["id"]
    log("+ authorizer created")
    time.sleep(5)

ROUTES = [
    ("/chat", ["POST", "OPTIONS"]),
    ("/chat/confirm", ["POST", "OPTIONS"]),
    ("/chat/status", ["GET", "OPTIONS"]),
    ("/chat/trace", ["GET", "OPTIONS"]),
    ("/chat/sessions", ["GET", "OPTIONS"]),
    ("/models", ["GET", "OPTIONS"]),
    ("/me", ["GET", "OPTIONS"]),
    ("/kb/docs", ["GET", "DELETE", "OPTIONS"]),
    ("/kb/presign", ["POST", "OPTIONS"]),
    ("/kb/sync", ["POST", "OPTIONS"]),
    ("/admin/signout", ["POST", "OPTIONS"]),
    ("/admin/users", ["GET", "POST", "DELETE", "OPTIONS"]),
    ("/admin/users/status", ["POST", "OPTIONS"]),
    ("/admin/users/set-password", ["POST", "OPTIONS"]),
    ("/admin/users/resend-invite", ["POST", "OPTIONS"]),
    ("/uploads/presign", ["POST", "OPTIONS"]),
    ("/translate", ["POST", "OPTIONS"]),
    ("/docs/content", ["GET", "POST", "OPTIONS"]),
    ("/docs/list", ["GET", "OPTIONS"]),
]

# build resource map (root path is "" in API Gateway)
resources = {r["path"]: r["id"] for r in apig.get_resources(restApiId=api_id, limit=200)["items"]}
resources[""] = root_id
for path, _ in ROUTES:
    parts = path.strip("/").split("/")
    cur = ""
    for part in parts:
        parent = cur
        cur = f"{cur}/{part}"
        if cur not in resources:
            try:
                rid = apig.create_resource(restApiId=api_id, parentId=resources[parent],
                                           pathPart=part)["id"]
            except apig.exceptions.ConflictException:
                # eventual consistency: re-fetch and reuse
                time.sleep(2)
                items = apig.get_resources(restApiId=api_id, limit=400)["items"]
                for r in items:
                    resources[r["path"]] = r["id"]
                rid = resources[cur]
            resources[cur] = rid
log(f"resources ready: {len(resources)}")

CORS_HEADERS = {
    "method.response.header.Access-Control-Allow-Origin": "'*'",
    "method.response.header.Access-Control-Allow-Headers": "'Authorization,Content-Type'",
    "method.response.header.Access-Control-Allow-Methods": "'GET,POST,DELETE,OPTIONS'",
}


def _safe(fn, **kw):
    try:
        fn(**kw)
        return True
    except (apig.exceptions.ConflictException, apig.exceptions.NotFoundException):
        return False


def add_method(rid, verb):
    kw = dict(restApiId=api_id, resourceId=rid, httpMethod=verb, apiKeyRequired=False)
    if verb == "OPTIONS":
        kw["authorizationType"] = "NONE"
    else:
        kw["authorizationType"] = "COGNITO_USER_POOLS"
        kw["authorizerId"] = auth_id
    _safe(apig.put_method, **kw)
    if verb == "OPTIONS":
        # WAJIB AWS_PROXY: lambda mengembalikan header CORS.
        # MOCK tanpa Gateway Responses CORS = browser gagal preflight (silent error).
        uri = f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/{fn_arn}/invocations"
        _safe(apig.put_integration, restApiId=api_id, resourceId=rid, httpMethod="OPTIONS",
              type="AWS_PROXY", integrationHttpMethod="POST", uri=uri)
        _safe(apig.put_method_response, restApiId=api_id, resourceId=rid,
              httpMethod="OPTIONS", statusCode="200")
        return
    uri = f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/{fn_arn}/invocations"
    _safe(apig.put_integration, restApiId=api_id, resourceId=rid, httpMethod=verb,
          type="AWS_PROXY", integrationHttpMethod="POST", uri=uri)
    _safe(apig.put_method_response, restApiId=api_id, resourceId=rid, httpMethod=verb,
          statusCode="200",
          responseParameters={f"method.response.header.{k}": False for k in CORS_HEADERS})
    _safe(apig.put_integration_response, restApiId=api_id, resourceId=rid, httpMethod=verb,
          statusCode="200", responseTemplates={"application/json": ""},
          responseParameters={f"method.response.header.{k}": v for k, v in CORS_HEADERS.items()})


for path, verbs in ROUTES:
    rid = resources[path]
    for verb in verbs:
        add_method(rid, verb)
log("methods + integrations wired")

# lambda permission for api gateway
try:
    apig_src = f"arn:aws:execute-api:{REGION}:{ACCOUNT_ID}:{api_id}/*/*"
    lam.add_permission(FunctionName=EDGE_FN, StatementId="apigw-invoke",
                       Action="lambda:InvokeFunction", Principal="apigateway.amazonaws.com",
                       SourceArn=apig_src)
    log("+ lambda permission for apigw")
except Exception as e:
    if "ResourceConflictException" not in str(e):
        log(f"  permission warn: {str(e)[:120]}")

# deployment + stage
try:
    d = apig.create_deployment(restApiId=api_id, stageName=STAGE)
    log(f"+ deployed to stage {STAGE}")
except Exception as e:
    log(f"  deployment warn: {str(e)[:150]}")
    apig.create_deployment(restApiId=api_id)
    log(f"+ redeployed")

try:
    apig.update_stage(restApiId=api_id, stageName=STAGE, patchOperations=[
        {"op": "replace", "path": "/*/*/throttling/rateLimit", "value": "40"},
        {"op": "replace", "path": "/*/*/throttling/burstLimit", "value": "80"},
    ])
    log("  stage throttling: 40 rps / burst 80")
except Exception as e:
    log(f"  throttle warn: {str(e)[:120]}")

api_url = f"https://{api_id}.execute-api.{REGION}.amazonaws.com/{STAGE}"
st["api_url"] = api_url
save_state(st)
log(f"API URL: {api_url}")

# ---------------------------------------------------------------- WAF x2
def make_webacl(name, rate_limit, managed_rules=True):
    try:
        existing = waf.list_web_acls(Scope="REGIONAL", limit=100)["WebACLs"]
        for w in existing:
            if w["Name"] == name:
                log(f"  = {name} exists")
                return w["ARN"], w["Id"], w["LockToken"]
    except Exception:
        pass
    rules = [
        {"Name": "RateLimitPerIP", "Priority": 0,
         "Action": {"Block": {}}, "VisibilityConfig": {
             "SampledRequestsEnabled": True, "CloudWatchMetricsEnabled": True,
             "MetricName": f"{name}-rate"},
         "Statement": {"RateBasedStatement": {"Limit": rate_limit, "AggregateKeyType": "IP"}}},
    ]
    if managed_rules:
        rules += [
            {"Name": "AWSCommon", "Priority": 1,
             "OverrideAction": {"None": {}}, "VisibilityConfig": {
                 "SampledRequestsEnabled": True, "CloudWatchMetricsEnabled": True,
                 "MetricName": f"{name}-common"},
             "Statement": {"ManagedRuleGroupStatement": {
                 "VendorName": "AWS", "Name": "AWSManagedRulesCommonRuleSet"}}},
            {"Name": "AWSBadInputs", "Priority": 2,
             "OverrideAction": {"None": {}}, "VisibilityConfig": {
                 "SampledRequestsEnabled": True, "CloudWatchMetricsEnabled": True,
                 "MetricName": f"{name}-badinputs"},
             "Statement": {"ManagedRuleGroupStatement": {
                 "VendorName": "AWS", "Name": "AWSManagedRulesKnownBadInputsRuleSet"}}},
        ]
    try:
        r = waf.create_web_acl(
            Name=name, Scope="REGIONAL",
            DefaultAction={"Allow": {}},
            Rules=rules,
            VisibilityConfig={"SampledRequestsEnabled": True, "CloudWatchMetricsEnabled": True,
                              "MetricName": name},
            Description=f"MAA agent rate limiting - {name}",
            Tags=[{"Key": "Project", "Value": "maa-agent"}],
        )
        summary = r["Summary"]
    except waf.exceptions.WAFDuplicateItemException:
        for w in waf.list_web_acls(Scope="REGIONAL", Limit=100)["WebACLs"]:
            if w["Name"] == name:
                summary = w
                break
        log(f"  = {name} (duplicate, reusing)")
    log(f"+ {name} created (limit {rate_limit}/5min)")
    return summary["ARN"], summary["Id"], summary["LockToken"]


def associate(acl_arn, resource_arn, label):
    for attempt in range(6):
        try:
            waf.associate_web_acl(WebACLArn=acl_arn, ResourceArn=resource_arn)
            log(f"+ {label} associated")
            return
        except Exception as e:
            if attempt < 5 and ("Unavailable" in str(e) or "retrieve" in str(e)):
                log(f"  {label}: entity not ready, retry {attempt+1}/6 (15s)")
                time.sleep(15)
                continue
            log(f"  {label} associate warn: {str(e)[:150]}")
            return


api_acl_arn, _, _ = make_webacl("maa-agent-api-waf", 2000, managed_rules=True)
cog_acl_arn, _, _ = make_webacl("maa-agent-cognito-waf", 100, managed_rules=False)
stage_arn = f"arn:aws:apigateway:{REGION}::/restapis/{api_id}/stages/{STAGE}"
associate(api_acl_arn, stage_arn, "WAF -> API stage")
associate(cog_acl_arn, st["user_pool_arn"], "WAF -> Cognito user pool")

save_state(st)
log("=== EDGE + APIGW + WAF DEPLOY COMPLETE ===")
