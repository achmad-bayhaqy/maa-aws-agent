#!/usr/bin/env python3
"""Patch: tambah dynamodb:DeleteItem untuk role edge lambda (fitur hapus sesi)."""
import boto3
from lib_common import log, load_state  # noqa: E402

iam = boto3.client("iam")
st = load_state()
TABLE = st["sessions_table"]

role_name = "maa-agent-edge-role"
pol_name = "maa-agent-edge-policy"
pol = iam.get_role_policy(RoleName=role_name, PolicyName=pol_name)["PolicyDocument"]
doc = pol  # url-decoded dict

stmt_sessions = None
for s in doc["Statement"]:
    res = s.get("Resource", "")
    res_list = res if isinstance(res, list) else [res]
    if any(f"table/{TABLE}" in r for r in res_list):
        stmt_sessions = s
        break

if stmt_sessions:
    acts = stmt_sessions.setdefault("Action", [])
    if isinstance(acts, str):
        acts = [acts]
    if "dynamodb:DeleteItem" not in acts:
        acts.append("dynamodb:DeleteItem")
        stmt_sessions["Action"] = acts
        iam.put_role_policy(RoleName=role_name, PolicyName=pol_name,
                            PolicyDocument=__import__("json").dumps(doc))
        log("+ DeleteItem ditambahkan pada statement sessions")
    else:
        log("= DeleteItem sudah ada")
else:
    log("X statement sessions tidak ditemukan")

log("=== PATCH IAM COMPLETE ===")
