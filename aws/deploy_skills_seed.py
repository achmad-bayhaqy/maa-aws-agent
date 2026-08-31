#!/usr/bin/env python3
"""MAA AWS Agent — seed Skills Library + KB katalog (v3.5, feedback #8).

Mengunggah seluruh skills_seed/<slug>/SKILL.md ke s3://{ART_BUCKET}/skills/
(dibaca agent via skills_list/skills_use — "ingatan" permanen), lalu menaruh
katalog ringkas ke KB docs/ agar bisa dicari via kb_search (RAG).

Idempotent: upload hanya bila konten berubah (md5 vs S3 ETag). Aman dipanggil
berulang; butuh state.json (art_bucket, kb_bucket, kms_key_id) dari bootstrap.
"""
import hashlib
import json
import os
import sys

import boto3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_common import load_state, log, REGION  # noqa: E402

SEED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills_seed")
SKILL_PREFIX = "skills/"


def main():
    st = load_state()
    art = st.get("art_bucket")
    if not art:
        log("X art_bucket belum ada di state.json — jalankan bootstrap/foundation dulu")
        sys.exit(1)
    s3 = boto3.client("s3", region_name=REGION)
    kms = st.get("kms_key_id")

    files = []
    for root, _dirs, fnames in os.walk(SEED_DIR):
        for fn in sorted(fnames):
            if fn.endswith(".md"):
                files.append(os.path.join(root, fn))
    log(f"menemukan {len(files)} file seed")

    up = 0
    skip = 0
    for path in files:
        rel = os.path.relpath(path, SEED_DIR).replace(os.sep, "/")
        if rel == "_catalog.md":
            continue  # katalog khusus KB
        slug = rel.split("/")[0]
        key = f"{SKILL_PREFIX}{slug}/SKILL.md"
        body = open(path, "rb").read()
        if not body.strip():
            continue
        # idempotensi via md5 (SSE-KMS membuat ETag != md5, jadi bandingkan
        # metadata x-amz-meta-maamd5)
        md5 = hashlib.md5(body).hexdigest()
        try:
            cur = s3.head_object(Bucket=art, Key=key)
            if cur.get("Metadata", {}).get("maamd5") == md5:
                skip += 1
                continue
        except Exception:
            pass
        s3.put_object(Bucket=art, Key=key, Body=body, ServerSideEncryption="aws:kms",
                      SSEKMSKeyId=kms, ContentType="text/markdown; charset=utf-8",
                      Metadata={"maamd5": md5, "source": "seed"})
        up += 1
    log(f"skills library: {up} baru, {skip} sudah sinkron -> s3://{art}/skills/")

    # --- katalog ke KB (RAG: agent bisa kb_search "apa saja skill yang ada") ---
    kb = st.get("kb_bucket")
    cat_path = os.path.join(SEED_DIR, "_catalog.md")
    if kb and os.path.exists(cat_path):
        body = open(cat_path, "rb").read()
        key = "docs/agent/katalog-skill-library.md"
        md5 = hashlib.md5(body).hexdigest()
        try:
            cur = s3.head_object(Bucket=kb, Key=key)
            if cur.get("Metadata", {}).get("maamd5") == md5:
                log("katalog KB sudah sinkron")
                return
        except Exception:
            pass
        s3.put_object(Bucket=kb, Key=key, Body=body, ServerSideEncryption="aws:kms",
                      SSEKMSKeyId=kms, ContentType="text/markdown; charset=utf-8",
                      Metadata={"maamd5": md5})
        log(f"katalog skill -> s3://{kb}/{key} (jalankan KB sync utk re-index)")
        try:
            ba = boto3.client("bedrock-agent", region_name=REGION)
            ds = ba.list_data_sources(knowledgeBaseId=st["kb_id"])["dataSourceSummaries"]
            job = ba.start_ingestion_job(knowledgeBaseId=st["kb_id"],
                                         dataSourceId=ds[0]["dataSourceId"],
                                         description="seed: katalog skill library")
            log(f"KB ingestion: {job['ingestionJob']['ingestionJobId']} ({job['ingestionJob']['status']})")
        except Exception as e:
            log(f"KB ingestion tertunda: {str(e)[:120]}")


if __name__ == "__main__":
    main()
