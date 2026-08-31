#!/usr/bin/env python3
"""MAA AWS Agent - Deploy v4.0 Scheduler (idempotent).

Tugas Terjadwal (ala ChatGPT Tasks):
  1. Tabel DynamoDB `maa-agent-schedules` (PK id) utk simpan jadwal.
  2. EventBridge Scheduler `maa-agent-schedule-tick` rate(1 minute) ->
     invoke Lambda edge dengan payload {"_async":"schedule"} (worker tick).
  3. Resource-based permission: scheduler.amazonaws.com boleh invoke edge.
  4. SCHEDULES_TABLE diset di env edge Lambda + state.json.

Jalankan:  python3 aws/deploy_scheduler.py   (setelah edge_apigw)
"""
import json
import os
import time

import boto3
from botocore.config import Config

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "state.json")
REGION = "us-east-1"
TABLE = "maa-agent-schedules"
SCHED_NAME = "maa-agent-schedule-tick"
EDGE_FN = "maa-agent-edge"


def log(m):
    print(f"[scheduler] {m}", flush=True)


st = json.load(open(STATE_PATH))
cfg = Config(retries={"max_attempts": 3, "mode": "standard"})
ddb = boto3.client("dynamodb", region_name=REGION, config=cfg)
lam = boto3.client("lambda", region_name=REGION, config=cfg)
sch = boto3.client("scheduler", region_name=REGION, config=cfg)

# 1. tabel schedules
try:
    ddb.describe_table(TableName=TABLE)
    log(f"tabel {TABLE} sudah ada")
except ddb.exceptions.ResourceNotFoundException:
    ddb.create_table(TableName=TABLE,
                     KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                     AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
                     BillingMode="PAY_PER_REQUEST",
                     Tags=[{"Key": "MAA", "Value": "true"}, {"Key": "Project", "Value": "MAA"},
                           {"Key": "ManagedBy", "Value": "maa-aws-agent"}])
    ddb.get_waiter("table_exists").wait(TableName=TABLE)
    log(f"tabel {TABLE} dibuat")
st["schedules_table"] = TABLE

# 2. izin scheduler invoke edge
fn_arn = lam.get_function(FunctionName=EDGE_FN)["Configuration"]["FunctionArn"]
stmt_id = "AllowSchedulerInvokeEdge"
try:
    pol = json.loads(lam.get_policy(FunctionName=EDGE_FN)["Policy"])
    have = any(s.get("Sid") == stmt_id for s in pol.get("Statement", []))
    if not have:
        raise Exception("no-stmt")
    log("permission scheduler->edge sudah ada")
except Exception:
    try:
        lam.add_permission(FunctionName=EDGE_FN, StatementId=stmt_id,
                           Action="lambda:InvokeFunction",
                           Principal="scheduler.amazonaws.com",
                           SourceArn=f"arn:aws:scheduler:{REGION}:{st['account_id']}:schedule/{SCHED_NAME}")
        log("permission scheduler->edge ditambahkan")
    except Exception as e:
        log(f"~ add_permission (mungkin duplikat): {str(e)[:120]}")

# 3. EventBridge Scheduler rate(1 minute) — pakai role khusus scheduler
iam = boto3.client("iam", config=cfg)
sched_role = "maa-scheduler-role"
TRUST = json.dumps({
    "Version": "2012-10-17",
    "Statement": [{"Effect": "Allow", "Principal": {"Service": "scheduler.amazonaws.com"},
                   "Action": "sts:AssumeRole"}],
})
try:
    iam.create_role(RoleName=sched_role, AssumeRolePolicyDocument=TRUST,
                    Description="EventBridge Scheduler -> invoke maa-agent-edge tick",
                    Tags=[{"Key": "MAA", "Value": "true"}, {"Key": "Project", "Value": "MAA"},
                          {"Key": "ManagedBy", "Value": "maa-aws-agent"}])
    log(f"role {sched_role} dibuat")
except Exception as e:
    if "already" not in str(e).lower() and "EntityAlreadyExists" not in str(e):
        log(f"role warn: {str(e)[:120]}")
    else:
        log(f"= role {sched_role} sudah ada")
# pastikan trust terkini + permission invoke edge
try:
    iam.update_assume_role_policy(RoleName=sched_role, PolicyDocument=TRUST)
except Exception as e:
    log(f"~ trust update: {str(e)[:100]}")
sched_arn = f"arn:aws:iam::{st['account_id']}:role/{sched_role}"
try:
    iam.put_role_policy(RoleName=sched_role, PolicyName="maa-scheduler-invoke",
                        PolicyDocument=json.dumps({
                            "Version": "2012-10-17",
                            "Statement": [{"Effect": "Allow", "Action": ["lambda:InvokeFunction"],
                                           "Resource": [fn_arn, f"{fn_arn}:*"]}]}))
    log("role policy invoke edge diset")
except Exception as e:
    log(f"~ role policy: {str(e)[:100]}")
time.sleep(6)  # propagasi IAM

target_arn = fn_arn
payload = json.dumps({"_async": "schedule"})
try:
    sch.get_schedule(Name=SCHED_NAME)
    sch.update_schedule(Name=SCHED_NAME,
                        ScheduleExpression="rate(1 minute)",
                        FlexibleTimeWindow={"Mode": "OFF"},
                        Target={"Arn": target_arn, "RoleArn": sched_arn,
                                "RetryPolicy": {"MaximumRetryAttempts": 0,
                                                "MaximumEventAgeInSeconds": 120},
                                "Input": payload})
    log(f"schedule {SCHED_NAME} di-update")
except sch.exceptions.ResourceNotFoundException:
    sch.create_schedule(Name=SCHED_NAME,
                        ScheduleExpression="rate(1 minute)",
                        FlexibleTimeWindow={"Mode": "OFF"},
                        Target={"Arn": target_arn, "RoleArn": sched_arn,
                                "RetryPolicy": {"MaximumRetryAttempts": 0,
                                                "MaximumEventAgeInSeconds": 120},
                                "Input": payload})
    log(f"schedule {SCHED_NAME} dibuat")

# tag role scheduler
try:
    iam.tag_role(RoleName=sched_role, Tags=[{"Key": "MAA", "Value": "true"},
                                            {"Key": "Project", "Value": "MAA"},
                                            {"Key": "ManagedBy", "Value": "maa-aws-agent"}])
except Exception:
    pass

# 4. env edge SCHEDULES_TABLE (idempotent)
try:
    while lam.get_function_configuration(FunctionName=EDGE_FN)["LastUpdateStatus"] == "InProgress":
        time.sleep(3)
    cur = lam.get_function_configuration(FunctionName=EDGE_FN)["Environment"]["Variables"]
    if cur.get("SCHEDULES_TABLE") != TABLE:
        cur["SCHEDULES_TABLE"] = TABLE
        for attempt in range(10):
            try:
                lam.update_function_configuration(FunctionName=EDGE_FN,
                                                  Environment={"Variables": cur})
                break
            except lam.exceptions.ResourceConflictException:
                time.sleep(5)
        log("env edge SCHEDULES_TABLE diset")
    else:
        log("env edge SCHEDULES_TABLE sudah benar")
except Exception as e:
    log(f"~ env edge: {str(e)[:150]}")

json.dump(st, open(STATE_PATH, "w"), indent=2, default=str)
log("SELESAI: scheduler aktif (tick tiap menit, hasil tugas terkirim ke sesi)")
