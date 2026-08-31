#!/usr/bin/env python3
"""MAA AWS Agent — BOOTSTRAP akun baru (satu perintah, idempotent).

Deploy penuh ke AWS account kosong dengan prefix `maa-agent` + tag MAA pada
semua resource (permintaan user: "nama depannya dan tagnya 'MAA'").

Rantai (semua script idempotent, aman di-re-run):
  1  foundation      KMS, S3 (KB+ART), DynamoDB, IAM roles inti
  2  cognito         User Pool TOTP MFA wajib + grup superadmin + user admin
  3  bedrock         Guardrail + S3 Vectors KB + dokumen seed + ingestion
  4  runtime_role    IAM role AgentCore Runtime (the brain)
  5  agentcore       Memory + Gateway + Policy Engine + Code Interpreter
                     (INTERNET — scraping Python aktif) + Evaluator + 88 model
  6  edge_apigw      Edge Lambda v3.5 + API REST + Cognito authorizer + WAF
  7  v343            PublicAccessBlock + policy publik gen/decks/apps +
                     rebuild runtime v3.5 (KB CRUD tools, skills library) +
                     re-point edge
  8  skills_seed     100+ skill (Anthropic + AWS resmi) -> Skills Library S3
                     + katalog ke KB (feedback #8: "ingatan" agent)
  9  amplify         build frontend + hosting (skip: --skip-frontend)
  10 tag_audit       pastikan SEMUA resource bertag MAA (S3/DDB/IAM/Lambda/
                     Cognito/KMS/API GW)

Pemakaian:
  source scripts/awsenv.sh
  python3 aws/bootstrap_maa.py [--skip-frontend] [--only 5,7] [--list]

State tersimpan di aws/state.json (akun dipantau: ganti akun -> state lama
diarsipkan otomatis ke state-<akun-lama>.json).
"""
import json
import os
import subprocess
import sys
import time

import boto3

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")
REGION = "us-east-1"

STEPS = [
    ("1",  "foundation",   "deploy_foundation.py",   "KMS + S3 + DynamoDB + IAM inti"),
    ("2",  "cognito",      "deploy_cognito.py",      "User Pool TOTP MFA + admin user"),
    ("3",  "bedrock",      "deploy_bedrock.py",      "Guardrail + S3 Vectors KB + seed"),
    ("4",  "runtime_role", "deploy_runtime_role.py", "IAM role AgentCore Runtime"),
    ("5",  "agentcore",    "deploy_v3_agentcore.py", "Memory+Gateway+CI INTERNET+Evaluator"),
    ("6",  "edge_apigw",   "deploy_edge_apigw_waf.py", "Edge Lambda + API GW + WAF"),
    ("7",  "v343",         "deploy_v343.py",         "URL publik artefak + rebuild runtime"),
    ("8",  "skills_seed",  "deploy_skills_seed.py",  "100+ skill -> Skills Library + KB"),
    ("9",  "amplify",      "deploy_amplify.py",      "Frontend build + hosting"),
]


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def account():
    return boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]


def guard_state():
    """Jika state.json milik akun lain, arsipkan lalu mulai state segar."""
    st = {}
    if os.path.exists(STATE):
        try:
            st = json.load(open(STATE))
        except Exception:
            st = {}
    cur = account()
    if st.get("account_id") and st["account_id"] != cur:
        old = os.path.join(HERE, f"state-{st['account_id']}.json")
        os.replace(STATE, old)
        log(f"!! state akun lama ({st['account_id']}) diarsipkan -> {os.path.basename(old)}")
        st = {}
    if not st.get("account_id"):
        st["account_id"] = cur
        json.dump(st, open(STATE, "w"), indent=2, default=str)
    log(f"akun target: {cur} | region: {REGION} | prefix: maa-agent | tag: MAA=true")
    return st


def ensure_frontend_deps():
    """Amplify step butuh node_modules — install bila belum ada (idempotent)."""
    root = os.path.dirname(HERE)
    if not os.path.isdir(os.path.join(root, "node_modules")):
        log("bun install (frontend deps)...")
        subprocess.run(["bun", "install", "--frozen-lockfile"], cwd=root, check=True)


def run_step(script):
    if script == "deploy_amplify.py":
        ensure_frontend_deps()
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    p = subprocess.run([sys.executable, os.path.join(HERE, script)],
                       cwd=HERE, env=env)
    return p.returncode == 0


def tag_audit():
    """Sweep terakhir: semua resource inti diberi tag MAA=true (idempotent)."""
    st = json.load(open(STATE))
    TAGS = [{"Key": "MAA", "Value": "true"}, {"Key": "Project", "Value": "MAA"},
            {"Key": "ManagedBy", "Value": "maa-aws-agent"}]
    tg = lambda d: {"Tags": TAGS, **d}  # noqa: E731
    ok = warn = 0

    def t(label, fn):
        nonlocal ok, warn
        try:
            fn()
            ok += 1
        except Exception as e:
            warn += 1
            log(f"  ~ tag {label}: {str(e)[:100]}")

    s3 = boto3.client("s3", region_name=REGION)
    for b in filter(None, [st.get("kb_bucket"), st.get("art_bucket"), st.get("vector_bucket")]):
        t(f"s3:{b}", lambda b=b: s3.put_bucket_tagging(Bucket=b, TagSet=TAGS))

    ddb = boto3.client("dynamodb", region_name=REGION)
    for tab in filter(None, [st.get("sessions_table"), st.get("traces_table"), st.get("confirm_table")]):
        try:
            arn = ddb.describe_table(TableName=tab)["Table"]["TableArn"]
            t(f"ddb:{tab}", lambda a=arn: ddb.tag_resource(ResourceArn=a, Tags=TAGS))
        except Exception as e:
            log(f"  ~ ddb arn {tab}: {str(e)[:90]}")

    iam = boto3.client("iam")
    for r in filter(None, [st.get("orch_role"), st.get("exec_role"), st.get("kb_role"),
                           st.get("runtime_role"), "maa-agent-edge-role"]):
        t(f"iam:{r}", lambda r=r: iam.tag_role(RoleName=r, Tags=[{"Key": x["Key"], "Value": x["Value"]} for x in TAGS]))

    lam = boto3.client("lambda", region_name=REGION)
    try:
        fns = lam.list_functions(MaxItems=100)["Functions"]
        for f in fns:
            if f["FunctionName"].startswith("maa-"):
                t(f"lambda:{f['FunctionName']}", lambda a=f["FunctionArn"]: lam.tag_resource(ResourceArn=a, Tags=TAGS))
    except Exception as e:
        log(f"  ~ lambda sweep: {str(e)[:90]}")

    cog = boto3.client("cognito-idp", region_name=REGION)
    if st.get("user_pool_arn"):
        t("cognito:userpool", lambda a=st["user_pool_arn"]: cog.tag_resource(ResourceArn=a, Tags=TAGS))

    kms = boto3.client("kms", region_name=REGION)
    if st.get("kms_key_id"):
        t("kms:key", lambda k=st["kms_key_id"]: kms.tag_resource(KeyId=k, Tags=[{"TagKey": x["Key"], "TagValue": x["Value"]} for x in TAGS]))

    apigw = boto3.client("apigateway", region_name=REGION)
    if st.get("api_id"):
        t("apigw", lambda a=st["api_id"]: apigw.tag_resource(ResourceArn=f"arn:aws:apigateway:{REGION}::/restapis/{a}", Tags={"MAA": "true", "Project": "MAA", "ManagedBy": "maa-aws-agent"}))

    log(f"tag audit: {ok} resource bertag MAA ({warn} warn)")


def summary():
    st = json.load(open(STATE))
    print("\n" + "=" * 64)
    print("  MAA AWS AGENT — DEPLOY SELESAI")
    print("=" * 64)
    print(f"  Akun      : {st.get('account_id')} ({REGION})")
    print(f"  Frontend  : {st.get('amplify_url', '(belum)')}")
    print(f"  API       : {st.get('api_url', '(belum)')}")
    print(f"  Runtime   : {st.get('agent_runtime_id', '(belum)')}")
    print(f"  Login     : lihat aws/maa-user-credentials.json (username+password)")
    print(f"  Skills    : 100+ skill -> s3://{st.get('art_bucket', '?')}/skills/")
    print("  Tag       : MAA=true di semua resource (audit jalan)")
    print("=" * 64 + "\n")


def main():
    args = sys.argv[1:]
    if "--list" in args:
        for sid, name, script, desc in STEPS:
            print(f"  {sid:2s} {name:12s} {desc}")
        print("  10 tag_audit   sweep tag MAA semua resource")
        return

    st = guard_state()
    only = None
    if "--only" in args:
        only = [x.strip() for x in args[args.index("--only") + 1].split(",")]
    skip_front = "--skip-frontend" in args

    todo = []
    for sid, name, script, desc in STEPS:
        if skip_front and name == "amplify":
            continue
        if only and sid not in only:
            continue
        todo.append((sid, name, script, desc))

    log(f"eksekusi {len(todo)} langkah: {[x[1] for x in todo]}")
    failed = []
    for sid, name, script, desc in todo:
        log(f"--- [{sid}/{len(todo)}] {name}: {desc} ---")
        if not run_step(script):
            log(f"X langkah {name} GAGAL — berhenti (re-run perintah yang sama utk lanjut)")
            failed.append(name)
            break

    if not failed:
        log("--- [tag audit] sweep tag MAA ---")
        tag_audit()
        summary()
    else:
        print(f"\nSEBAGIAN GAGAL: {failed}. Perbaiki lalu jalankan ulang bootstrap (idempotent).")
        sys.exit(1)


if __name__ == "__main__":
    main()
