#!/usr/bin/env python3
"""Frontend-only deploy: build static export + Amplify deploy.
Dipakai terpisah dari deploy backend. Jalankan: python3 aws/deploy_frontend.py
"""
import io
import json
import os
import shutil
import subprocess
import time
import urllib.request
import zipfile

import boto3
from botocore.config import Config

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
with open(os.path.join(HERE, "state.json")) as f:
    st = json.load(f)
REGION = st.get("region", "us-east-1")
cfg = Config(retries={"max_attempts": 3, "mode": "standard"}, read_timeout=300)


def log(m):
    print(f"[frontend] {m}", flush=True)


BUILD = os.path.join(HERE, "amplify-build")
if os.path.exists(BUILD):
    shutil.rmtree(BUILD)
os.makedirs(BUILD)
shutil.copytree(os.path.join(ROOT, "src"), os.path.join(BUILD, "src"),
                ignore=shutil.ignore_patterns("api"))
shutil.copytree(os.path.join(ROOT, "public"), os.path.join(BUILD, "public"),
                dirs_exist_ok=True)
for f in ["package.json", "tsconfig.json", "postcss.config.mjs", "bun.lock",
          "components.json", "eslint.config.mjs"]:
    p = os.path.join(ROOT, f)
    if os.path.exists(p):
        shutil.copy2(p, BUILD)
try:
    os.symlink(os.path.join(ROOT, "node_modules"), os.path.join(BUILD, "node_modules"))
except Exception:
    pass
with open(os.path.join(BUILD, "next.config.mjs"), "w") as f:
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
with open(os.path.join(BUILD, ".env.production"), "w") as f:
    f.write(f"""NEXT_PUBLIC_REGION={REGION}
NEXT_PUBLIC_COGNITO_POOL_ID={st['user_pool_id']}
NEXT_PUBLIC_COGNITO_CLIENT_ID={st['app_client_id']}
NEXT_PUBLIC_API_URL={st['api_url']}
""")

log("next build (static export)...")
r = subprocess.run(["bunx", "next", "build"], cwd=BUILD,
                   capture_output=True, text=True, timeout=900)
out = (r.stdout or "") + (r.stderr or "")
if r.returncode != 0 or not os.path.exists(os.path.join(BUILD, "out", "index.html")):
    log("BUILD FAIL:")
    print(out[-3000:])
    raise SystemExit(1)

zbuf = io.BytesIO()
with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
    for base, _, files in os.walk(os.path.join(BUILD, "out")):
        for fn in files:
            full = os.path.join(base, fn)
            z.write(full, os.path.relpath(full, os.path.join(BUILD, "out")))

amp = boto3.client("amplify", region_name=REGION, config=cfg)
app_id = st["amplify_app_id"]
for j in amp.list_jobs(appId=app_id, branchName="main", maxResults=10)["jobSummaries"]:
    if j["status"] in ("PENDING", "RUNNING", "WAITING_TO_APPROVE"):
        try:
            amp.stop_job(appId=app_id, branchName="main", jobId=j["jobId"])
            time.sleep(3)
        except Exception:
            pass
job = amp.create_deployment(appId=app_id, branchName="main")
upload_url = job.get("zipUploadUrl") or list(job.get("fileUploadUrls", {}).values())[0]
req = urllib.request.Request(upload_url, data=zbuf.getvalue(), method="PUT",
                             headers={"Content-Type": "application/zip"})
urllib.request.urlopen(req)
amp.start_deployment(appId=app_id, branchName="main", jobId=job["jobId"])
for i in range(50):
    j = amp.get_job(appId=app_id, branchName="main", jobId=job["jobId"])["job"]["summary"]
    if j["status"] in ("SUCCEED", "FAIL", "CANCELLED"):
        if j["status"] != "SUCCEED":
            print(json.dumps(j, default=str)[:500])
            raise SystemExit(1)
        break
    time.sleep(6)
log(f"amplify deploy OK: {st.get('amplify_url', '')}")
