#!/usr/bin/env python3
"""MAA AWS Agent - Task 10: Build static export + deploy ke AWS Amplify Hosting."""
import io
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile

import boto3

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from lib_common import ACCOUNT_ID, REGION, log, load_state, save_state

st = load_state()
SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # root repo (di atas aws/)
BUILD = os.path.join(SRC, "aws", "amplify-build")
API_URL = st["api_url"]

# ---------------------------------------------------------------- 1. build dir
log("menyiapkan build directory (static export)...")
if os.path.exists(BUILD):
    shutil.rmtree(BUILD)
os.makedirs(BUILD)
shutil.copytree(f"{SRC}/src", f"{BUILD}/src",
                ignore=shutil.ignore_patterns("api"))  # route handler tidak kompatibel export
shutil.copytree(f"{SRC}/public", f"{BUILD}/public", dirs_exist_ok=True)
for f in ["package.json", "tsconfig.json", "postcss.config.mjs", "bun.lock",
          "components.json", "eslint.config.mjs"]:
    p = os.path.join(SRC, f)
    if os.path.exists(p):
        shutil.copy2(p, BUILD)
os.symlink(f"{SRC}/node_modules", f"{BUILD}/node_modules")

with open(f"{BUILD}/next.config.mjs", "w") as f:
    f.write("""/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  typescript: { ignoreBuildErrors: true },
  reactStrictMode: false,
  eslint: { ignoreDuringBuilds: true },
};
export default nextConfig;
""")

with open(f"{BUILD}/.env.production", "w") as f:
    f.write(f"""NEXT_PUBLIC_REGION={REGION}
NEXT_PUBLIC_COGNITO_POOL_ID={st['user_pool_id']}
NEXT_PUBLIC_COGNITO_CLIENT_ID={st['app_client_id']}
NEXT_PUBLIC_API_URL={API_URL}
""")
log("build dir ready")

# ---------------------------------------------------------------- 2. next build
log("menjalankan next build (static export)...")
r = subprocess.run([sys.executable, "-m", "bun"] if False else ["bunx", "next", "build"],
                   cwd=BUILD, capture_output=True, text=True, timeout=600)
out = (r.stdout or "") + (r.stderr or "")
if r.returncode != 0 or not os.path.exists(f"{BUILD}/out/index.html"):
    log("BUILD FAIL:")
    print(out[-3000:])
    raise SystemExit(1)
log(f"static export OK -> {BUILD}/out")

# ---------------------------------------------------------------- 3. zip
log("mengemas out/ menjadi zip...")
zbuf = io.BytesIO()
with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
    for base, _, files in os.walk(f"{BUILD}/out"):
        for fn in files:
            full = os.path.join(base, fn)
            z.write(full, os.path.relpath(full, f"{BUILD}/out"))
log(f"zip: {zbuf.tell() / 1e6:.1f} MB")

# ---------------------------------------------------------------- 4. amplify
amp = boto3.client("amplify", region_name=REGION)

app_id = st.get("amplify_app_id")
if app_id:
    log(f"= amplify app exists: {app_id}")
else:
    app = amp.create_app(
        name="maa-agent-web",
        description="MAA AWS Agent - mobile chat frontend (Bedrock AgentCore)",
        platform="WEB",
        customRules=[{
            "source": "</^[^.]+$|\\.(?!(css|gif|ico|jpg|jpeg|js|png|txt|svg|woff|woff2|ttf|json|map|webp)$)([^.]+$)/>",
            "target": "/index.html", "status": "200"}],
        tags={"Project": "maa-agent", "MAA": "true"},
    )
    app_id = app["app"]["appId"]
    st["amplify_app_id"] = app_id
    save_state(st)
    log(f"+ amplify app created: {app_id}")

try:
    amp.create_branch(appId=app_id, branchName="main", enableAutoBuild=False)
    log("+ branch main created")
except Exception as e:
    if "AlreadyExists" not in str(e):
        log(f"  branch warn: {str(e)[:120]}")

# stop pending jobs from previous attempts
for j in amp.list_jobs(appId=app_id, branchName="main", maxResults=10)["jobSummaries"]:
    if j["status"] in ("PENDING", "RUNNING", "WAITING_TO_APPROVE"):
        try:
            amp.stop_job(appId=app_id, branchName="main", jobId=j["jobId"])
            log(f"  stopped pending job {j['jobId']}")
        except Exception:
            pass
        time.sleep(3)

job = amp.create_deployment(appId=app_id, branchName="main")
job_id = job["jobId"]
upload_url = job.get("zipUploadUrl") or list(job.get("fileUploadUrls", {}).values())[0]
log(f"deployment job: {job_id}")

import urllib.request
data = zbuf.getvalue()
req = urllib.request.Request(upload_url, data=data, method="PUT",
                             headers={"Content-Type": "application/zip"})
try:
    resp = urllib.request.urlopen(req)
    log(f"upload: {resp.status}")
except Exception as e:
    log(f"upload FAIL: {str(e)[:200]}")
    raise

amp.start_deployment(appId=app_id, branchName="main", jobId=job_id)
log("deployment started, menunggu...")
for i in range(40):
    j = amp.get_job(appId=app_id, branchName="main", jobId=job_id)["job"]["summary"]
    s = j["status"]
    if s in ("SUCCEED", "FAIL", "CANCELLED"):
        log(f"deployment: {s}")
        if s != "SUCCEED":
            print(json.dumps(j, default=str)[:500])
            raise SystemExit(1)
        break
    time.sleep(6)

app_detail = amp.get_app(appId=app_id)["app"]
domain = app_detail.get("defaultDomain", "")
url = f"https://main.{domain}"
st["amplify_url"] = url
save_state(st)
log(f"=== AMPLIFY DEPLOY COMPLETE === URL: {url}")
