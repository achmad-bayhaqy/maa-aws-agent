#!/usr/bin/env python3
"""MAA AWS Agent - Diagnosis & perbaikan akses publik artefak (feedback M+N).

Masalah user: link gambar muncul di live trace tapi gambar tidak tampil di chat,
dicurigai Access Denied ke S3. Script ini:

  1. Mengecek Block Public Access (BPA) bucket artefak
  2. Mengecek bucket policy (Sid=PublicReadGeneratedArtifacts utk gen/*, decks/*, apps/*)
  3. Me-list objek terbaru di prefix publik + enkripsinya (SSE-KMS = TIDAK BISA anonim!)
  4. Menguji GET anonim (unsigned) pada objek terbaru -> inilah yang dilihat browser user
  5. --fix: perbaiki BPA + policy + re-encrypt objek SSE-KMS di prefix publik ke SSE-S3

Pakai:  source ../scripts/awsenv.sh && python3 aws/check_artifacts_access.py [--fix]
"""
import json
import sys

import boto3
import botocore
from botocore import UNSIGNED
from botocore.config import Config

REGION = "us-east-1"
ART = "maa-agent-artifacts-715841354009"
PUBLIC_PREFIXES = ("gen/", "decks/", "apps/")
STMT_SID = "PublicReadGeneratedArtifacts"

s3 = boto3.client("s3", region_name=REGION)
s3_anon = boto3.client("s3", region_name=REGION, config=Config(signature_version=UNSIGNED))
FIX = "--fix" in sys.argv


def log(m):
    print(m, flush=True)


def check_bpa():
    bpa = s3.get_public_access_block(Bucket=ART)["PublicAccessBlockConfiguration"]
    log(f"[BPA] {json.dumps(bpa)}")
    ok = (not bpa["BlockPublicPolicy"]) and (not bpa["RestrictPublicBuckets"])
    if not ok:
        log("  !! BlockPublicPolicy/RestrictPublicBuckets=True -> policy publik DIBLOKIR (akar Access Denied)")
        if FIX:
            s3.put_public_access_block(Bucket=ART, PublicAccessBlockConfiguration={
                "BlockPublicAcls": True, "IgnorePublicAcls": True,
                "BlockPublicPolicy": False, "RestrictPublicBuckets": False})
            log("  + FIXED: ACL tetap blokir, policy publik terbatas diizinkan")
    else:
        log("  OK: policy publik terbatas diizinkan")
    return ok


def check_policy():
    try:
        pol = json.loads(s3.get_bucket_policy(Bucket=ART)["Policy"])
    except s3.exceptions.NoSuchBucketPolicy:
        log("[POLICY] TIDAK ADA bucket policy sama sekali!")
        pol = {}
    stmt = next((s for s in pol.get("Statement", []) if s.get("Sid") == STMT_SID), None)
    if stmt:
        log(f"[POLICY] {STMT_SID}: {stmt['Effect']} {stmt['Action']} pada {len(stmt['Resource'])} resource")
        for r in stmt["Resource"]:
            log(f"    {r}")
        return True
    log(f"  !! Statement {STMT_SID} TIDAK ADA -> GET anonim = Access Denied")
    if FIX:
        stmt_new = {"Sid": STMT_SID, "Effect": "Allow", "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": [f"arn:aws:s3:::{ART}/{p}" for p in PUBLIC_PREFIXES]}
        pol.setdefault("Version", "2012-10-17")
        pol["Statement"] = [s for s in pol.get("Statement", []) if s.get("Sid") != STMT_SID] + [stmt_new]
        s3.put_bucket_policy(Bucket=ART, Policy=json.dumps(pol))
        log("  + FIXED: policy dipasang")
    return False


def list_and_check_objects():
    ok_all = True
    for pref in PUBLIC_PREFIXES:
        resp = s3.list_objects_v2(Bucket=ART, Prefix=pref, MaxKeys=5)
        objs = sorted(resp.get("Contents", []), key=lambda o: o["LastModified"], reverse=True)
        log(f"[{pref}] {resp.get('KeyCount', 0)} objek (5 terbaru):")
        for o in objs[:5]:
            head = s3.head_object(Bucket=ART, Key=o["Key"])
            sse = head.get("ServerSideEncryption", "-")
            url = f"https://{ART}.s3.{REGION}.amazonaws.com/{o['Key']}"
            anon = anon_get(url, o["Key"])
            flag = "OK " if anon == 200 else "FAIL"
            if anon != 200:
                ok_all = False
            log(f"  [{flag}] {o['Key'][:60]}  SSE={sse}  anonGET={anon}")
            if anon != 200 and sse == "aws:kms" and FIX:
                body = s3.get_object(Bucket=ART, Key=o["Key"])["Body"].read()
                s3.put_object(Bucket=ART, Key=o["Key"], Body=body,
                              ServerSideEncryption="AES256",
                              ContentType=head.get("ContentType", "application/octet-stream"))
                log(f"     + FIXED: re-encrypt SSE-KMS -> AES256")
    return ok_all


def anon_get(url, key):
    try:
        r = s3_anon.get_object(Bucket=ART, Key=key)
        r["Body"].read(16)
        return 200
    except botocore.exceptions.ClientError as e:
        return e.response["Error"].get("Code", "?")
    except Exception as e:
        return type(e).__name__[:20]


if __name__ == "__main__":
    log(f"=== Diagnosis akses publik artefak: {ART} (fix={FIX}) ===")
    check_bpa()
    check_policy()
    ok = list_and_check_objects()
    log("=== HASIL: " + ("SEMUA GET ANONIM OK — kalau browser masih gagal, masalahnya di frontend/CSP" if ok else "ADA YANG GAGAL — jalankan ulang dengan --fix bila belum") + " ===")
