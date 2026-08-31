#!/usr/bin/env python3
"""MAA AWS Agent - Edge Lambda v3.4.2 (thin SigV4 proxy ke AgentCore Runtime).
v3.4.2: pemisahan mode MODEL (AUTO/FAST/DEEP/MANUAL) vs mode TUGAS agent
(STANDARD/LONG/FULLSTACK/PRESENTATION/TODO/MULTI), userRole utk bypass
guardrail superadmin, sanitasi atts (kompat data lama string JSON)."""
import json
import os
import time
import uuid
import boto3
from botocore.config import Config

REGION = os.environ.get("AWS_REGION", "us-east-1")
RUNTIME_ARN = os.environ["RUNTIME_ARN"]
SESSIONS_TABLE = os.environ["SESSIONS_TABLE"]
KB_BUCKET = os.environ["KB_BUCKET"]
ART_BUCKET = os.environ["ART_BUCKET"]
MODELS_KEY = os.environ.get("MODELS_KEY", "models/allowed-chat-models.json")
KB_ID = os.environ.get("KB_ID", "")
USER_POOL_ID = os.environ["USER_POOL_ID"]
KMS_KEY_ID = os.environ["KMS_KEY_ID"]
CONF_TABLE = os.environ["CONF_TABLE"]
TRACE_LOG_GROUP = os.environ.get("TRACE_LOG_GROUP", "/maa/agent/trace")

cfg = Config(retries={"max_attempts": 2, "mode": "standard"}, read_timeout=280)
lam = boto3.client("lambda", region_name=REGION, config=cfg)
ddb_res = boto3.resource("dynamodb", region_name=REGION, config=cfg)
sessions_tbl = ddb_res.Table(SESSIONS_TABLE)
s3 = boto3.client("s3", region_name=REGION, config=cfg)
# WAJIB SigV4 utk presigned URL dengan SSE-KMS (SigV2 default -> S3 tolak 400)
s3v4 = boto3.client("s3", region_name=REGION,
                    config=Config(signature_version="s3v4",
                                  retries={"max_attempts": 2, "mode": "standard"}))
cog = boto3.client("cognito-idp", region_name=REGION, config=cfg)
wlogs = boto3.client("logs", region_name=REGION, config=cfg)


def now_ms():
    return int(time.time() * 1000)


MODELS_CACHE = {"ts": 0, "data": None}


def get_models():
    if MODELS_CACHE["data"] and now_ms() - MODELS_CACHE["ts"] < 300_000:
        return MODELS_CACHE["data"]
    obj = s3.get_object(Bucket=ART_BUCKET, Key=MODELS_KEY)
    data = json.loads(obj["Body"].read())
    MODELS_CACHE["ts"] = now_ms()
    MODELS_CACHE["data"] = data
    return data


def invoke_runtime(payload):
    r = boto3.client("bedrock-agentcore", region_name=REGION, config=cfg).invoke_agent_runtime(
        agentRuntimeArn=RUNTIME_ARN,
        runtimeSessionId=payload["sessionId"],
        contentType="application/json",
        accept="application/json",
        payload=json.dumps(payload).encode(),
    )
    return json.loads(r["response"].read().decode())


def claims_of(event):
    c = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    groups = (c.get("cognito:groups") or "").split(",") if c.get("cognito:groups") else []
    role = "superadmin" if "superadmin" in groups else c.get("custom:role", "user")
    # ID token: cognito:username; access token: username
    username = c.get("cognito:username") or c.get("username") \
        or c.get("preferred_username") or "user"
    return {"userId": c.get("sub", "unknown"),
            "username": username,
            "email": c.get("email", ""),
            "role": role}


def is_superadmin(cl):
    return cl.get("role") == "superadmin"


# mode model (routing) - v3.4.2: hanya 4
MODEL_MODES = ("AUTO", "FAST", "DEEP", "MANUAL")
# mode tugas agent (gaya kerja) - terpisah dari model
AGENT_MODES = ("STANDARD", "LONG", "FULLSTACK", "PRESENTATION", "TODO", "MULTI")
# kompat klien lama (v3.4): mode=LONG/FULLSTACK/PRESENTATION dipetakan ke agentMode
LEGACY_AGENT_MODES = ("LONG", "FULLSTACK", "PRESENTATION")


def parse_modes(body):
    """Ekstrak (mode, agentMode) dari body klien, kompat v3.4 lama."""
    mode = body.get("mode", "AUTO")
    agent_mode = body.get("agentMode")
    if mode not in MODEL_MODES:
        if mode in LEGACY_AGENT_MODES:
            agent_mode = agent_mode or mode
        mode = "AUTO"
    if agent_mode not in AGENT_MODES:
        agent_mode = "STANDARD"
    return mode, agent_mode


def sanitize_messages(messages):
    """Normalisasi pesan utk UI: atts/versions wajib array (data lama runtime
    menyimpan atts sebagai string JSON di DDB -> crash render di klien)."""
    out = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        mm = dict(m)
        for f in ("atts", "versions"):
            v = mm.get(f)
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except Exception:
                    v = None
            if not isinstance(v, list):
                v = [x for x in (v or [])] if isinstance(v, list) else None
            if v is None and f in mm:
                mm.pop(f)
            elif v is not None:
                if f == "atts":
                    v = [_att_numeric(vv) if isinstance(vv, dict) else vv for vv in v]
                mm[f] = v
        mm["text"] = str(mm.get("text", "") or "")
        out.append(mm)
    return out


def _att_numeric(a):
    """Konversi field numerik atts yang terbaca Decimal/str (size, slides, files)."""
    for k in ("size", "slides", "files"):
        v = a.get(k)
        if isinstance(v, str) and v.isdigit():
            a[k] = int(v)
        elif v is not None and not isinstance(v, (int, float)):
            try:
                a[k] = int(float(v))
            except Exception:
                a.pop(k, None)
    return a


def resp(code, body):
    return {"statusCode": code,
            "headers": {"Content-Type": "application/json",
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Headers": "Authorization,Content-Type",
                        "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS"},
            "body": json.dumps(body, ensure_ascii=False, default=str)}


def handler(event, context):
    method = event.get("httpMethod", "GET")
    path = event.get("resource", event.get("path", ""))
    qs = event.get("queryStringParameters") or {}
    cl = claims_of(event)

    try:
        if method == "OPTIONS":
            return resp(200, {})

        # ---------------- identity ----------------
        if path == "/me" and method == "GET":
            email, role = cl.get("email", ""), cl.get("role", "user")
            if not email:
                try:
                    u = cog.admin_get_user(UserPoolId=USER_POOL_ID, Username=cl["username"])
                    for a in u.get("UserAttributes", []):
                        if a["Name"] == "email":
                            email = a["Value"]
                except Exception:
                    pass
            return resp(200, {"userId": cl["userId"], "username": cl["username"],
                              "email": email, "role": role})

        # ---------------- chat ----------------
        if path == "/chat" and method == "POST":
            body = json.loads(event.get("body") or "{}")
            message = (body.get("message") or "").strip()
            regenerate = bool(body.get("regenerate"))
            if not message and not regenerate:
                return resp(400, {"error": "message kosong"})
            if len(message) > 6000:
                return resp(400, {"error": "message terlalu panjang (max 6000)"})
            mode, agent_mode = parse_modes(body)
            # lampiran chat (v3.4): key harus di bawah uploads/{userId}/
            atts = []
            for a in (body.get("attachments") or [])[:8]:
                k = str(a.get("key", ""))
                if k.startswith(f"uploads/{cl['userId']}/") and ".." not in k:
                    atts.append({"key": k, "name": str(a.get("name", ""))[:120],
                                 "contentType": str(a.get("contentType", ""))[:80],
                                 "size": int(a.get("size", 0) or 0)})
            edit_from = body.get("editFrom")
            existing_sid = body.get("sessionId")
            if existing_sid:
                sid = existing_sid
                rec = sessions_tbl.get_item(Key={"sessionId": sid}).get("Item")
                if not rec or rec.get("userId") != cl["userId"]:
                    return resp(403, {"error": "bukan sesi Anda"})
                if regenerate:
                    # REGENERATE: jalankan ulang dari pesan user terakhir
                    # (tanpa mengubah teks) -> jawaban lama jadi versions
                    msgs = rec.get("messages", [])
                    lu = -1
                    for i, m in enumerate(msgs):
                        if m.get("role") == "user":
                            lu = i
                    if lu < 0:
                        return resp(400, {"error": "tidak ada pesan untuk diregenerasi"})
                    message = msgs[lu].get("text", "") or message
                    edit_from = lu
                if edit_from is not None:
                    # EDIT pesan user pada index edit_from (teks lama -> versions);
                    # pesan user ditulis runtime saat regenerasi.
                    # Tandai processing agar polling UI mulai sebelum runtime selesai.
                    sessions_tbl.update_item(Key={"sessionId": sid},
                        UpdateExpression="SET #s = :st, #mo = :mo, updatedAt = :u",
                        ExpressionAttributeNames={"#s": "status", "#mo": "mode"},
                        ExpressionAttributeValues={":st": "processing", ":mo": mode,
                                                   ":u": str(now_ms())})
                    payload = {"type": "chat", "sessionId": sid, "userId": cl["userId"],
                               "username": cl["username"], "message": message,
                               "mode": mode, "agentMode": agent_mode,
                               "userRole": cl["role"], "modelId": body.get("modelId"),
                               "editFrom": int(edit_from), "attachments": atts}
                else:
                    # PESAN LANJUTAN di sesi yang sama: tambahkan pesan user
                    # ke record (runtime dedupe sehingga tidak dobel)
                    msgs = rec.get("messages", [])
                    um = {"role": "user", "text": message, "ts": now_ms()}
                    if atts:
                        um["atts"] = [{"name": a["name"], "kind": "upload", "size": a["size"]} for a in atts]
                    msgs.append(um)
                    sessions_tbl.update_item(Key={"sessionId": sid},
                        UpdateExpression="SET #s = :st, #mo = :mo, #m = :m, updatedAt = :u",
                        ExpressionAttributeNames={"#s": "status", "#mo": "mode", "#m": "messages"},
                        ExpressionAttributeValues={":st": "processing", ":mo": mode,
                                                   ":m": msgs, ":u": str(now_ms())})
                    payload = {"type": "chat", "sessionId": sid, "userId": cl["userId"],
                               "username": cl["username"], "message": message,
                               "mode": mode, "agentMode": agent_mode,
                               "userRole": cl["role"], "modelId": body.get("modelId"),
                               "attachments": atts}
            else:
                sid = f"chat-{uuid.uuid4().hex}"
                um = {"role": "user", "text": message, "ts": now_ms()}
                if atts:
                    um["atts"] = [{"name": a["name"], "kind": "upload", "size": a["size"]} for a in atts]
                sessions_tbl.put_item(Item={
                    "sessionId": sid, "userId": cl["userId"], "username": cl["username"],
                    "status": "processing", "mode": mode,
                    "modelId": body.get("modelId", "") or "",
                    "title": message[:80],
                    "messages": [um],
                    "createdAt": str(now_ms()), "updatedAt": str(now_ms()),
                    "expiresAt": now_ms() // 1000 + 30 * 86400,
                })
                payload = {"type": "chat", "sessionId": sid, "userId": cl["userId"],
                           "username": cl["username"], "message": message,
                           "mode": mode, "agentMode": agent_mode,
                           "userRole": cl["role"], "modelId": body.get("modelId"), "attachments": atts}
            lam.invoke(FunctionName=context.function_name,
                       InvocationType="Event",
                       Payload=json.dumps({"_async": "chat", "runtimePayload": payload,
                                           "user": cl}).encode())
            return resp(202, {"sessionId": sid, "status": "processing"})

        if path == "/chat/confirm" and method == "POST":
            body = json.loads(event.get("body") or "{}")
            sid = body.get("sessionId", "")
            rec = sessions_tbl.get_item(Key={"sessionId": sid}).get("Item")
            if not rec or rec.get("userId") != cl["userId"]:
                return resp(403, {"error": "bukan sesi Anda"})
            out = invoke_runtime({"type": "confirm", "sessionId": sid,
                                  "userId": cl["userId"], "username": cl["username"],
                                  "confirmToken": body.get("confirmToken"),
                                  "typed1": body.get("typed1", ""),
                                  "typed2": body.get("typed2", "")})
            return resp(200, out)

        if path == "/chat/status" and method == "GET":
            sid = qs.get("sessionId", "")
            rec = sessions_tbl.get_item(Key={"sessionId": sid}).get("Item")
            if not rec or rec.get("userId") != cl["userId"]:
                return resp(403, {"error": "bukan sesi Anda"})
            pending = None
            try:
                scan = boto3.client("dynamodb", region_name=REGION, config=cfg).scan(
                    TableName=CONF_TABLE,
                    FilterExpression="#s = :p AND sessionId = :sid",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={":p": {"S": "pending"}, ":sid": {"S": sid}})
                for item in scan.get("Items", []):
                    if int(item.get("expiresAt", {}).get("N", "0")) > time.time():
                        op = json.loads(item.get("operation", {}).get("S", "{}"))
                        pending = {"confirmToken": item["confirmToken"]["S"],
                                   "challenge": item["challenge"]["S"],
                                   "operation": op}
                        break
            except Exception:
                pass
            auto_route = None
            try:
                if rec.get("autoRoute"):
                    auto_route = json.loads(rec["autoRoute"]) if isinstance(rec["autoRoute"], str) \
                        else rec["autoRoute"]
            except Exception:
                pass
            todos = None
            try:
                if rec.get("todos"):
                    todos = json.loads(rec["todos"]) if isinstance(rec["todos"], str) else rec["todos"]
            except Exception:
                pass
            clarify = None
            try:
                for m in reversed(rec.get("messages", [])):
                    if m.get("role") == "assistant":
                        c = m.get("clarify")
                        if c and isinstance(c, dict) and c.get("question"):
                            clarify = {"question": c.get("question", ""),
                                       "options": c.get("options", [])}
                        break
            except Exception:
                pass
            return resp(200, {"sessionId": sid, "status": rec.get("status"),
                              "mode": rec.get("mode"), "modelId": rec.get("modelId"),
                              "autoRoute": auto_route,
                              "clarify": clarify,
                              "todos": todos,
                              "title": rec.get("title"),
                              "messages": sanitize_messages(rec.get("messages", [])),
                              "pendingConfirmation": pending})

        if path == "/chat/trace" and method == "GET":
            sid = qs.get("sessionId", "")
            after = int(qs.get("after", "0") or 0)
            rec = sessions_tbl.get_item(Key={"sessionId": sid}).get("Item")
            if not rec or rec.get("userId") != cl["userId"]:
                return resp(403, {"error": "bukan sesi Anda"})
            events = []
            try:
                streams = wlogs.describe_log_streams(
                    logGroupName=TRACE_LOG_GROUP,
                    logStreamNamePrefix=sid, limit=5).get("logStreams", [])
                for st_ in streams:
                    kw = {"logGroupName": TRACE_LOG_GROUP, "logStreamName": st_["logStreamName"],
                          "limit": 120, "startFromHead": True}
                    if after:
                        kw["startTime"] = after + 1
                    evs = wlogs.get_log_events(**kw).get("events", [])
                    for e in evs:
                        try:
                            d = json.loads(e["message"])
                            events.append({"ts": str(d.get("ts", e["timestamp"])),
                                           "type": d.get("type", "info"),
                                           "content": d.get("content", ""),
                                           "model": d.get("model", "")})
                        except Exception:
                            events.append({"ts": str(e["timestamp"]), "type": "info",
                                           "content": e["message"][:400], "model": ""})
            except Exception:
                pass
            events.sort(key=lambda x: int(x["ts"]))
            return resp(200, {"events": events[:200]})

        if path == "/chat/sessions" and method == "GET":
            r = sessions_tbl.query(IndexName="user-index",
                                   KeyConditionExpression="userId = :u",
                                   ExpressionAttributeValues={":u": cl["userId"]},
                                   ScanIndexForward=False, Limit=25)
            out = [{"sessionId": i["sessionId"], "title": i.get("title", ""),
                    "status": i.get("status"), "mode": i.get("mode"),
                    "createdAt": i.get("createdAt"), "updatedAt": i.get("updatedAt")}
                   for i in r.get("Items", [])]
            return resp(200, {"sessions": out})

        if path == "/chat/sessions" and method == "DELETE":
            sid = qs.get("sessionId", "")
            rec = sessions_tbl.get_item(Key={"sessionId": sid}).get("Item")
            if not rec or rec.get("userId") != cl["userId"]:
                return resp(403, {"error": "bukan sesi Anda"})
            sessions_tbl.delete_item(Key={"sessionId": sid})
            return resp(200, {"deleted": True, "sessionId": sid})

        # ---------------- models ----------------
        if path == "/models" and method == "GET":
            return resp(200, get_models())

        # ---------------- KB ----------------
        if path == "/kb/docs" and method == "GET":
            r = s3.list_objects_v2(Bucket=KB_BUCKET, Prefix="docs/", MaxKeys=100)
            docs = [{"key": o["Key"], "size": o["Size"], "name": o["Key"].split("/")[-1],
                     "updated": str(o["LastModified"])} for o in r.get("Contents", [])]
            return resp(200, {"docs": docs})

        if path == "/kb/presign" and method == "POST":
            body = json.loads(event.get("body") or "{}")
            name = body.get("name", "")
            ctype = body.get("contentType", "application/octet-stream")
            ext_ok = (".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".csv", ".json", ".md", ".txt")
            if not name.lower().endswith(ext_ok):
                return resp(400, {"error": "format harus PDF/XLSX/PNG/JPG/CSV/JSON/MD/TXT"})
            if ".." in name or name.startswith("/"):
                return resp(400, {"error": "nama file tidak valid"})
            key = f"docs/{uuid.uuid4().hex[:8]}-{name}"
            url = s3v4.generate_presigned_url(
                "put_object", Params={
                    "Bucket": KB_BUCKET, "Key": key, "ContentType": ctype,
                    "ServerSideEncryption": "aws:kms", "SSEKMSKeyId": KMS_KEY_ID},
                ExpiresIn=600)
            # SigV4: header yang di-signed WAJIB dikirim client saat PUT
            return resp(200, {"uploadUrl": url, "key": key, "headers": {
                "Content-Type": ctype,
                "x-amz-server-side-encryption": "aws:kms",
                "x-amz-server-side-encryption-aws-kms-key-id": KMS_KEY_ID}})

        if path == "/kb/docs" and method == "DELETE":
            key = qs.get("key", "")
            if not key.startswith("docs/"):
                return resp(400, {"error": "key harus di bawah docs/"})
            s3.delete_object(Bucket=KB_BUCKET, Key=key)
            return resp(200, {"deleted": key})

        if path == "/kb/sync" and method == "POST":
            ba = boto3.client("bedrock-agent", region_name=REGION, config=cfg)
            ds = ba.list_data_sources(knowledgeBaseId=KB_ID)["dataSourceSummaries"]
            job = ba.start_ingestion_job(knowledgeBaseId=KB_ID,
                                         dataSourceId=ds[0]["dataSourceId"],
                                         description="manual sync from UI")
            return resp(200, {"jobId": job["ingestionJob"]["ingestionJobId"],
                              "status": job["ingestionJob"]["status"]})

        # ---------------- uploads lampiran chat (v3.4) ----------------
        if path == "/uploads/presign" and method == "POST":
            body = json.loads(event.get("body") or "{}")
            name = (body.get("name") or "file").strip()
            ctype = body.get("contentType", "application/octet-stream")
            size = int(body.get("size", 0) or 0)
            if ".." in name or name.startswith("/") or "\\" in name:
                return resp(400, {"error": "nama file tidak valid"})
            if len(name) > 160:
                return resp(400, {"error": "nama file terlalu panjang"})
            if size > 200 * 1024 * 1024:
                return resp(400, {"error": "ukuran maksimal 200 MB per file"})
            key = f"uploads/{cl['userId']}/{uuid.uuid4().hex[:10]}-{name}"
            url = s3v4.generate_presigned_url(
                "put_object", Params={
                    "Bucket": ART_BUCKET, "Key": key, "ContentType": ctype,
                    "ServerSideEncryption": "aws:kms", "SSEKMSKeyId": KMS_KEY_ID},
                ExpiresIn=900)
            # SigV4: header yang di-signed WAJIB dikirim client saat PUT
            return resp(200, {"uploadUrl": url, "key": key, "headers": {
                "Content-Type": ctype,
                "x-amz-server-side-encryption": "aws:kms",
                "x-amz-server-side-encryption-aws-kms-key-id": KMS_KEY_ID}})

        # ---------------- translate EN -> ID (v3.4) ----------------
        if path == "/translate" and method == "POST":
            body = json.loads(event.get("body") or "{}")
            text = str(body.get("text", "")).strip()
            if not text:
                return resp(400, {"error": "teks kosong"})
            if len(text) > 12000:
                return resp(400, {"error": "teks terlalu panjang (max 12000)"})
            # runtimeSessionId AgentCore butuh >= 33 char
            tsession = body.get("sessionId") or f"translate-{uuid.uuid4().hex}"
            if len(tsession) < 33:
                tsession = f"translate-{tsession}-{uuid.uuid4().hex}"[:128]
            out = invoke_runtime({"type": "translate", "text": text,
                                  "sessionId": tsession})
            return resp(200, out)

        # ---------------- dokumentasi editable (v3.4, superadmin) ----------------
        DOCS_PREFIX = "site/docs/"
        if path == "/docs/content" and method == "GET":
            key = qs.get("key", "")
            if not key.startswith(DOCS_PREFIX) or ".." in key:
                return resp(400, {"error": "key tidak valid"})
            try:
                obj = s3.get_object(Bucket=ART_BUCKET, Key=key)
                return resp(200, {"key": key, "content": obj["Body"].read().decode("utf-8", "ignore"),
                                  "updated": str(obj.get("LastModified", ""))})
            except Exception:
                return resp(404, {"error": "dokumen tidak ditemukan"})

        if path == "/docs/content" and method == "POST":
            if not is_superadmin(cl):
                return resp(403, {"error": "khusus superadmin"})
            body = json.loads(event.get("body") or "{}")
            key = body.get("key", "")
            content = body.get("content", "")
            if not key.startswith(DOCS_PREFIX) or ".." in key or not key.endswith(".md"):
                return resp(400, {"error": "key harus .md di bawah site/docs/"})
            if len(content) > 200_000:
                return resp(400, {"error": "konten terlalu besar (max 200k char)"})
            s3.put_object(Bucket=ART_BUCKET, Key=key, Body=content.encode(),
                          ServerSideEncryption="aws:kms", SSEKMSKeyId=KMS_KEY_ID,
                          ContentType="text/markdown; charset=utf-8")
            return resp(200, {"saved": True, "key": key})

        if path == "/docs/list" and method == "GET":
            r = s3.list_objects_v2(Bucket=ART_BUCKET, Prefix=DOCS_PREFIX, MaxKeys=50)
            docs = [{"key": o["Key"], "name": o["Key"].split("/")[-1], "size": o["Size"],
                     "updated": str(o["LastModified"])} for o in r.get("Contents", [])]
            return resp(200, {"docs": docs})

        # ---------------- superadmin ----------------
        if path == "/admin/users" and method == "GET":
            if not is_superadmin(cl):
                return resp(403, {"error": "khusus superadmin"})
            users = []
            kw = {"UserPoolId": USER_POOL_ID, "Limit": 60}
            while True:
                r = cog.list_users(**kw)
                for u in r.get("Users", []):
                    attrs = {a["Name"]: a["Value"] for a in u.get("Attributes", [])}
                    users.append({"username": u.get("Username", ""),
                                  "email": attrs.get("email", ""),
                                  "status": u.get("UserStatus", ""),
                                  "enabled": u.get("Enabled", False),
                                  "created": str(u.get("UserCreateDate", "")),
                                  "role": attrs.get("custom:role", "user")})
                tok = r.get("PaginationToken")
                if not tok or len(users) >= 200:
                    break
                kw["PaginationToken"] = tok
            return resp(200, {"users": users})

        if path == "/admin/users" and method == "POST":
            if not is_superadmin(cl):
                return resp(403, {"error": "khusus superadmin"})
            body = json.loads(event.get("body") or "{}")
            email = (body.get("email") or "").strip().lower()
            role = body.get("role", "user")
            if role not in ("user", "superadmin"):
                return resp(400, {"error": "role harus user|superadmin"})
            import re as _re
            if not _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                return resp(400, {"error": "email tidak valid"})
            username = email.split("@")[0] + "-" + uuid.uuid4().hex[:4]
            r = cog.admin_create_user(
                UserPoolId=USER_POOL_ID, Username=username,
                UserAttributes=[{"Name": "email", "Value": email},
                                {"Name": "email_verified", "Value": "true"}],
                DesiredDeliveryMediums=["EMAIL"],
                # MessageAction default = SEND: Cognito mengirim email undangan
                # (temp password) via sender default no-reply@verificationemail.com
            )
            if role == "superadmin":
                try:
                    cog.admin_add_user_to_group(UserPoolId=USER_POOL_ID,
                                                GroupName="superadmin", Username=username)
                except Exception:
                    pass
            return resp(200, {"username": username, "email": email, "role": role,
                              "inviteSent": True,
                              "note": "Email undangan berisi password sementara dikirim otomatis oleh Cognito."})

        if path == "/admin/users/status" and method == "POST":
            if not is_superadmin(cl):
                return resp(403, {"error": "khusus superadmin"})
            body = json.loads(event.get("body") or "{}")
            username = body.get("username", "")
            enabled = bool(body.get("enabled"))
            if enabled:
                cog.admin_enable_user(UserPoolId=USER_POOL_ID, Username=username)
            else:
                cog.admin_disable_user(UserPoolId=USER_POOL_ID, Username=username)
            return resp(200, {"updated": True, "username": username, "enabled": enabled})

        if path == "/admin/users/set-password" and method == "POST":
            if not is_superadmin(cl):
                return resp(403, {"error": "khusus superadmin"})
            body = json.loads(event.get("body") or "{}")
            username = body.get("username", "")
            password = body.get("password", "")
            if len(password) < 12:
                return resp(400, {"error": "password minimal 12 karakter"})
            cog.admin_set_user_password(UserPoolId=USER_POOL_ID, Username=username,
                                        Password=password, Permanent=True)
            return resp(200, {"updated": True, "username": username,
                              "note": "Password permanen diset. User bisa langsung login (lanjut MFA TOTP)."})

        if path == "/admin/users/resend-invite" and method == "POST":
            if not is_superadmin(cl):
                return resp(403, {"error": "khusus superadmin"})
            body = json.loads(event.get("body") or "{}")
            username = body.get("username", "")
            try:
                cog.admin_create_user(
                    UserPoolId=USER_POOL_ID, Username=username,
                    MessageAction="RESEND",
                    DesiredDeliveryMediums=["EMAIL"])
                return resp(200, {"resent": True, "username": username})
            except Exception as e:
                return resp(400, {"error": f"resend gagal: {str(e)[:200]}"})

        if path == "/admin/users" and method == "DELETE":
            if not is_superadmin(cl):
                return resp(403, {"error": "khusus superadmin"})
            username = qs.get("username", "")
            if username == cl["username"]:
                return resp(400, {"error": "tidak bisa menghapus diri sendiri"})
            cog.admin_delete_user(UserPoolId=USER_POOL_ID, Username=username)
            return resp(200, {"deleted": True, "username": username})

        if path == "/admin/signout" and method == "POST":
            cog.admin_user_global_sign_out(UserPoolId=USER_POOL_ID, Username=cl["username"])
            return resp(200, {"signedOut": True})

        return resp(404, {"error": f"route {method} {path} tidak ada"})
    except Exception as e:
        return resp(500, {"error": str(e)[:300]})


def async_handler(event, context):
    """Entry untuk self-invoke async (proses chat di latar belakang)."""
    if event.get("_async") == "chat":
        rp = event["runtimePayload"]
        sid = rp["sessionId"]
        try:
            out = invoke_runtime(rp)
            rec = sessions_tbl.get_item(Key={"sessionId": sid}).get("Item")
            if rec:
                msgs = rec.get("messages", [])
                has_reply = bool(msgs) and msgs[-1].get("role") == "assistant"
                new_status = "done" if (out.get("status") == "done" or has_reply) else "error"
                if not has_reply and out.get("response"):
                    am = {"role": "assistant", "text": out["response"], "ts": now_ms(),
                          "model": out.get("model", "")}
                    arts = out.get("attachments") or []
                    if arts:
                        am["atts"] = arts
                    msgs = msgs + [am]
                elif has_reply and (out.get("attachments") or []) and "atts" not in msgs[-1]:
                    msgs[-1]["atts"] = out["attachments"]
                sessions_tbl.update_item(
                    Key={"sessionId": sid},
                    UpdateExpression="SET #s = :st, #m = :m, updatedAt = :u, modelId = :mo",
                    ExpressionAttributeNames={"#s": "status", "#m": "messages"},
                    ExpressionAttributeValues={
                        ":st": new_status, ":m": msgs, ":u": str(now_ms()),
                        ":mo": out.get("model", rec.get("modelId", ""))})
        except Exception as e:
            sessions_tbl.update_item(
                Key={"sessionId": sid},
                UpdateExpression="SET #s = :st, err = :e, updatedAt = :u",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":st": "error", ":e": str(e)[:500], ":u": str(now_ms())})
        return {"ok": True}
    return handler(event, context)


lambda_handler = async_handler
