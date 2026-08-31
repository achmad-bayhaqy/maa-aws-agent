#!/usr/bin/env python3
"""MAA AWS Agent — AgentCore Runtime role (the brain's execution identity).
Trust: bedrock-agentcore.amazonaws.com. Broad enough for orchestration:
Bedrock invoke, DDB trace/session, S3 vectors + KB, STS 5-min execution role."""
import json
import sys

import boto3

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from lib_common import ACCOUNT_ID, REGION, log, load_state, save_state

st = load_state()
iam = boto3.client("iam")

ROLE = "maa-agent-runtime-role"

trust = {"Version": "2012-10-17", "Statement": [
    {"Effect": "Allow", "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
     "Action": "sts:AssumeRole"},
]}

try:
    r = iam.get_role(RoleName=ROLE)
    arn = r["Role"]["Arn"]
    log(f"= {ROLE} exists")
except iam.exceptions.NoSuchEntityException:
    r = iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(trust),
                        Description="MAA AWS Agent - AgentCore Runtime execution role",
                        Tags=[{"Key": "Project", "Value": "maa-agent"}])
    arn = r["Role"]["Arn"]
    log(f"+ {ROLE} created")

SESS = st["sessions_table"]
TRAC = st["traces_table"]
CONF = st["confirm_table"]
KB_BUCKET = st["kb_bucket"]
ART_BUCKET = st["art_bucket"]
EXEC_ARN = st["exec_role_arn"]

policy = {
    "Version": "2012-10-17",
    "Statement": [
        {"Sid": "Bedrock", "Effect": "Allow",
         "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream",
                    "bedrock:ApplyGuardrail", "bedrock:ListFoundationModels"],
         "Resource": "*"},
        {"Sid": "KbRetrieve", "Effect": "Allow", "Action": ["bedrock-agent-runtime:Retrieve"],
         "Resource": f"arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:knowledge-base/*"},
        {"Sid": "S3Vectors", "Effect": "Allow",
         "Action": ["s3vectors:GetIndex", "s3vectors:QueryVectors", "s3vectors:ListVectors",
                    "s3vectors:GetVectors"],
         "Resource": f"arn:aws:s3vectors:{REGION}:{ACCOUNT_ID}:bucket/maa-agent-vectors-{ACCOUNT_ID}*"},
        {"Sid": "Tables", "Effect": "Allow",
         "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:BatchWriteItem"],
         "Resource": [f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/{SESS}",
                      f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/{SESS}/index/*",
                      f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/{TRAC}",
                      f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/{CONF}"]},
        {"Sid": "KbDocsRead", "Effect": "Allow",
         "Action": ["s3:ListBucket", "s3:GetObject", "s3:GetBucketLocation"],
         "Resource": [f"arn:aws:s3:::{KB_BUCKET}", f"arn:aws:s3:::{KB_BUCKET}/*"]},
        {"Sid": "Artifacts", "Effect": "Allow",
         "Action": ["s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:GetBucketLocation"],
         "Resource": [f"arn:aws:s3:::{ART_BUCKET}", f"arn:aws:s3:::{ART_BUCKET}/*"]},
        {"Sid": "KmsUse", "Effect": "Allow",
         "Action": ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"],
         "Resource": st["kms_arn"]},
        {"Sid": "AssumeExec", "Effect": "Allow", "Action": ["sts:AssumeRole"],
         "Resource": EXEC_ARN,
         "Condition": {"StringEquals": {"sts:ExternalId": "maa-agent-exec"}}},
        {"Sid": "ModelsList", "Effect": "Allow",
         "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents",
                    "logs:DescribeLogStreams"],
         "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT_ID}:*"},
    ],
}
iam.put_role_policy(RoleName=ROLE, PolicyName="maa-agent-runtime-policy",
                    PolicyDocument=json.dumps(policy))
log(f"  inline policy set")

st["runtime_role_arn"] = arn
save_state(st)
print(json.dumps({"runtime_role_arn": arn}, indent=2))
