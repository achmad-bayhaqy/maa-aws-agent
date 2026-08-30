#!/usr/bin/env python3
"""CRITICAL FIX: browser CORS.
1. OPTIONS route -> AWS_PROXY (Lambda returns CORS headers; mock config was silently
   missing response parameters -> preflight failed -> browser chat did nothing).
2. Gateway Responses (UNAUTHORIZED/ACCESS_DENIED/THROTTLED/DEFAULT_4XX/DEFAULT_5XX)
   with Access-Control-Allow-* so auth errors are readable by fetch().
3. WAF: body-inspection rules (XSS/SQLi/Log4j) -> Count to avoid false-positive
   blocks on security-topic chat payloads; rate-limit stays Block.
4. Lambda: models cache TTL 3600s -> 300s + redeploy code.
5. CloudWatch log retention 7 days (cost).
6. Redeploy stage + verify preflight."""
import io, json, time, zipfile, subprocess, sys
import boto3

sys.path.insert(0, "/home/z/my-project/aws")
st = json.load(open("/home/z/my-project/aws/state.json"))
REGION = st["region"]
API = st["api_id"]
STAGE = "v1"

apig = boto3.client("apigateway", region_name=REGION)
lam = boto3.client("lambda", region_name=REGION)
waf = boto3.client("wafv2", region_name=REGION)
logs = boto3.client("logs", region_name=REGION)

def log(m): print(m, flush=True)

# ---------- 1. OPTIONS -> AWS_PROXY ----------
root = apig.get_resources(restApiId=API, limit=400)["items"]
res = {r["path"]: r["id"] for r in root}
ROUTES = ["/chat", "/chat/confirm", "/chat/status", "/chat/trace", "/chat/sessions",
          "/models", "/kb/docs", "/kb/presign", "/kb/sync", "/admin/signout"]
fn_arn = lam.get_function(FunctionName="maa-agent-edge")["Configuration"]["FunctionArn"]
uri = f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/{fn_arn}/invocations"

for path in ROUTES:
    rid = res[path]
    try:
        apig.delete_method(restApiId=API, resourceId=rid, httpMethod="OPTIONS")
    except Exception:
        pass
    apig.put_method(restApiId=API, resourceId=rid, httpMethod="OPTIONS",
                    authorizationType="NONE", apiKeyRequired=False)
    apig.put_integration(restApiId=API, resourceId=rid, httpMethod="OPTIONS",
                         type="AWS_PROXY", integrationHttpMethod="POST", uri=uri)
    log(f"  OPTIONS AWS_PROXY: {path}")
log("1. OPTIONS -> AWS_PROXY done")

# ---------- 2. Gateway responses with CORS ----------
GR = {"Access-Control-Allow-Origin": "'*'",
      "Access-Control-Allow-Headers": "'Authorization,Content-Type'",
      "Access-Control-Allow-Methods": "'GET,POST,DELETE,OPTIONS'"}
for rt_ in ("UNAUTHORIZED", "ACCESS_DENIED", "THROTTLED", "DEFAULT_4XX", "DEFAULT_5XX"):
    ops = [{"op": "replace", "path": f"/responseParameters/gatewayresponse.header.{k}",
            "value": v} for k, v in GR.items()]
    try:
        apig.update_gateway_response(restApiId=API, responseType=rt_, patchOperations=ops)
        log(f"  gateway response updated: {rt_}")
    except Exception:
        ops2 = [{"op": "add", "path": "/responseParameters",
                 "value": f"gatewayresponse.header.{list(GR.keys())[0]}"}]
        # fallback: create via patch on default
        try:
            apig.update_gateway_response(restApiId=API, responseType=rt_, patchOperations=[
                {"op": "add", "path": f"/responseParameters/gatewayresponse.header.{k}",
                 "value": v} for k, v in GR.items()])
            log(f"  gateway response created: {rt_}")
        except Exception as e:
            log(f"  gateway response WARN {rt_}: {str(e)[:100]}")
log("2. gateway responses done")

# ---------- 3. WAF rule action overrides (body inspection -> Count) ----------
def update_acl(name, overrides):
    acls = waf.list_web_acls(Scope="REGIONAL", Limit=100)["WebACLs"]
    cur = next((a for a in acls if a["Name"] == name), None)
    if not cur:
        log(f"  WAF {name} not found, skip")
        return
    full = waf.get_web_acl(Scope="REGIONAL", Id=cur["Id"], Name=name)["WebACL"]
    for rule in full.get("Rules", []):
        if rule["Name"].startswith("RateLimit"):
            continue
        stmt = rule.get("Statement", {})
        grp = stmt.get("ManagedRuleGroupStatement")
        if grp and overrides.get(rule["Name"]):
            grp.setdefault("RuleActionOverrides", [])
            grp["RuleActionOverrides"] = overrides[rule["Name"]]
    waf.update_web_acl(Scope="REGIONAL", Id=cur["Id"], Name=name,
                       DefaultAction=full["DefaultAction"], Rules=full["Rules"],
                       VisibilityConfig=full["VisibilityConfig"], LockToken=cur["LockToken"],
                       Description=full.get("Description", "MAA agent"))
    log(f"  WAF {name} updated with rule overrides")

update_acl("maa-agent-api-waf", {
    "AWSCommon": [
        {"Name": "CrossSiteScripting_BODY", "ActionToUse": {"Count": {}}},
        {"Name": "SQLi_BODY", "ActionToUse": {"Count": {}}},
    ],
    "AWSBadInputs": [
        {"Name": "Log4JRCE", "ActionToUse": {"Count": {}}},
    ],
})
log("3. WAF overrides done")

# ---------- 4. lambda code refresh (cache TTL 300s) ----------
src = open("/home/z/my-project/aws/lambda_edge/handler.py").read()
assert "300_000" in src, "handler.py TTL not patched yet"
zbuf = io.BytesIO()
with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("handler.py", src)
for attempt in range(10):
    try:
        lam.update_function_code(FunctionName="maa-agent-edge", ZipFile=zbuf.getvalue())
        while lam.get_function_configuration(FunctionName="maa-agent-edge")["LastUpdateStatus"] == "InProgress":
            time.sleep(3)
        log("4. edge lambda code updated (models cache TTL 300s)")
        break
    except lam.exceptions.ResourceConflictException:
        time.sleep(5)
log("4. lambda done")

# ---------- 5. log retention 7 days ----------
for lg in logs.describe_log_groups(logGroupNamePrefix="/aws/lambda/maa-agent")["logGroups"]:
    logs.put_retention_policy(logGroupName=lg["logGroupName"], retentionInDays=7)
    log(f"  retention 7d: {lg['logGroupName']}")
for lg in logs.describe_log_groups(logGroupNamePrefix="/aws/bedrock-agentcore")["logGroups"]:
    logs.put_retention_policy(logGroupName=lg["logGroupName"], retentionInDays=7)
    log(f"  retention 7d: {lg['logGroupName']}")
log("5. log retention done")

# ---------- 6. deploy + verify ----------
apig.create_deployment(restApiId=API, stageName=STAGE)
log(f"6. deployed stage {STAGE}")
time.sleep(3)
url = f"https://{API}.execute-api.{REGION}.amazonaws.com/{STAGE}"
out = subprocess.run(["curl", "-s", "-o", "/dev/null", "-D", "-", "-X", "OPTIONS",
                      f"{url}/chat",
                      "-H", "Origin: https://main.d3m7p7m7eyo6tj.amplifyapp.com",
                      "-H", "Access-Control-Request-Method: POST",
                      "-H", "Access-Control-Request-Headers: authorization,content-type"],
                     capture_output=True, text=True, timeout=30).stdout
ok = "Access-Control-Allow-Origin" in out
log(f"PREFLIGHT VERIFY: {'PASS - ACAO present' if ok else 'FAIL'}")
print(out)
sys.exit(0 if ok else 1)
