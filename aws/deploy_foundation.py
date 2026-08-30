#!/usr/bin/env python3
"""MAA AWS Agent - Task 2: AWS Foundation
KMS key, S3 buckets (KMS + TLS-only + versioning), DynamoDB tables (TTL),
IAM roles (orchestrator Lambda + agent execution 5-min + KB service role).
Idempotent: safe to re-run."""
import json
import sys
import time

import boto3

sys.path.insert(0, "/home/z/my-project/aws")
from lib_common import ACCOUNT_ID, REGION, log, load_state, save_state, try_call, update_state

st = load_state()
iam = boto3.client("iam")
kms = boto3.client("kms")
s3 = boto3.client("s3")
ddb = boto3.client("dynamodb")

ACCT = ACCOUNT_ID
KB_BUCKET = f"maa-agent-kb-docs-{ACCT}"
ART_BUCKET = f"maa-agent-artifacts-{ACCT}"
SESS_TABLE = "maa-agent-sessions"
TRACE_TABLE = "maa-agent-traces"
CONF_TABLE = "maa-agent-confirmations"
ORCH_ROLE = "maa-agent-orchestrator-role"
EXEC_ROLE = "maa-agent-execution-role"
KB_ROLE = "maa-agent-kb-role"
INST_ROLE = "maa-demo-instance-role"

# ---------------------------------------------------------------- KMS
log("=== KMS ===")
if st.get("kms_key_id"):
    key_id = st["kms_key_id"]
else:
    key = kms.create_key(
        Description="MAA AWS Agent - master key (AES-256 at rest)",
        Tags=[{"TagKey": "Project", "TagValue": "maa-agent"}],
    )
    key_id = key["KeyMetadata"]["KeyId"]
    st["kms_key_id"] = key_id
try:
    kms.create_alias(AliasName="alias/maa-agent-key", TargetKeyId=key_id)
    log(f"  alias created -> {key_id}")
except Exception as e:
    if "already exists" in str(e).lower() or "EntityAlreadyExists" in str(e):
        log("  alias exists")
    else:
        log(f"  alias warn: {str(e)[:120]}")
log(f"  KMS key: {key_id}")
st["kms_arn"] = kms.describe_key(KeyId=key_id)["KeyMetadata"]["Arn"]
save_state(st)

# ---------------------------------------------------------------- S3
log("=== S3 buckets ===")


def ensure_bucket(name, versioned=False, cors=False, tls_kms_policy=False):
    try:
        s3.head_bucket(Bucket=name)
        log(f"  = {name} exists")
    except Exception:
        if REGION == "us-east-1":
            s3.create_bucket(Bucket=name)
        else:
            s3.create_bucket(Bucket=name, CreateBucketConfiguration={"LocationConstraint": REGION})
        log(f"  + {name} created")
    if versioned:
        s3.put_bucket_versioning(Bucket=name, VersioningConfiguration={"Status": "Enabled"})
    s3.put_public_access_block(
        Bucket=name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True,
            "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
        },
    )
    s3.put_bucket_encryption(
        Bucket=name,
        ServerSideEncryptionConfiguration={
            "Rules": [{"ApplyServerSideEncryptionByDefault": {
                "SSEAlgorithm": "aws:kms", "KMSMasterKeyID": st["kms_key_id"]},
                "BucketKeyEnabled": True}]
        },
    )
    if cors:
        s3.put_bucket_cors(Bucket=name, CORSConfiguration={
            "CORSRules": [{
                "AllowedOrigins": ["*"],
                "AllowedMethods": ["PUT", "GET", "DELETE", "HEAD"],
                "AllowedHeaders": ["*"],
                "ExposeHeaders": ["ETag", "x-amz-request-id"],
                "MaxAgeSeconds": 3000,
            }]})
    if tls_kms_policy:
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "DenyInsecureTransport",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:*",
                    "Resource": [f"arn:aws:s3:::{name}", f"arn:aws:s3:::{name}/*"],
                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                },
                {
                    "Sid": "DenyUnEncryptedUploads",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:PutObject",
                    "Resource": f"arn:aws:s3:::{name}/*",
                    "Condition": {
                        "StringNotEquals": {"s3:x-amz-server-side-encryption": "aws:kms"},
                    },
                },
            ],
        }
        try:
            s3.put_bucket_policy(Bucket=name, Policy=json.dumps(policy))
        except Exception as e:
            log(f"  policy warn {name}: {str(e)[:150]}")
    log(f"  {name}: encryption=KMS versioned={versioned} cors={cors} tls-policy={tls_kms_policy}")


ensure_bucket(KB_BUCKET, versioned=True, cors=True, tls_kms_policy=True)
ensure_bucket(ART_BUCKET, versioned=False, cors=False, tls_kms_policy=True)
st["kb_bucket"] = KB_BUCKET
st["art_bucket"] = ART_BUCKET
save_state(st)

# ---------------------------------------------------------------- DynamoDB
log("=== DynamoDB ===")


def ensure_table(name, pk, sk=None, gsi=None, ttl_attr=None):
    try:
        t = ddb.describe_table(TableName=name)
        log(f"  = {name} exists")
        return t["Table"]["TableStatus"]
    except ddb.exceptions.ResourceNotFoundException:
        attrs = [{"AttributeName": pk, "AttributeType": "S"}]
        if sk:
            attrs.append({"AttributeName": sk, "AttributeType": "S"})
        kwargs = {
            "TableName": name,
            "AttributeDefinitions": attrs,
            "KeySchema": [{"AttributeName": pk, "KeyType": "HASH"}]
            + ([{"AttributeName": sk, "KeyType": "RANGE"}] if sk else []),
            "BillingMode": "PAY_PER_REQUEST",
            "Tags": [{"Key": "Project", "Value": "maa-agent"}],
        }
        if gsi:
            gattrs = [{"AttributeName": gsi["pk"], "AttributeType": "S"},
                      {"AttributeName": gsi["sk"], "AttributeType": "S"}]
            known = {a["AttributeName"] for a in attrs}
            for g in gattrs:
                if g["AttributeName"] not in known:
                    attrs.append(g)
            kwargs["GlobalSecondaryIndexes"] = [{
                "IndexName": gsi["name"],
                "KeySchema": [{"AttributeName": gsi["pk"], "KeyType": "HASH"},
                              {"AttributeName": gsi["sk"], "KeyType": "RANGE"}],
                "Projection": {"ProjectionType": "ALL"},
            }]
        ddb.create_table(**kwargs)
        w = ddb.get_waiter("table_exists")
        w.wait(TableName=name)
        log(f"  + {name} created")
    if ttl_attr:
        try:
            ddb.update_time_to_live(TableName=name, TimeToLiveSpecification={
                "Enabled": True, "AttributeName": ttl_attr})
            log(f"  TTL enabled on {name}.{ttl_attr}")
        except Exception as e:
            log(f"  TTL warn: {str(e)[:120]}")
    return "ACTIVE"


st["sessions_table"] = SESS_TABLE
st["traces_table"] = TRACE_TABLE
st["confirm_table"] = CONF_TABLE
save_state(st)
ensure_table(SESS_TABLE, "sessionId", gsi={"name": "user-index", "pk": "userId", "sk": "createdAt"},
             ttl_attr="expiresAt")
ensure_table(TRACE_TABLE, "sessionId", sk="itemKey", ttl_attr="expiresAt")
ensure_table(CONF_TABLE, "confirmToken", ttl_attr="expiresAt")

# ---------------------------------------------------------------- IAM
log("=== IAM roles ===")


def ensure_role(name, trust, description):
    try:
        r = iam.get_role(RoleName=name)
        log(f"  = {name} exists")
        return r["Role"]["Arn"]
    except iam.exceptions.NoSuchEntityException:
        # New-role propagation lag can make cross-role trust policies fail with
        # 'Invalid principal' - retry with backoff.
        for attempt in range(6):
            try:
                r = iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust),
                                    Description=description, Tags=[{"Key": "Project", "Value": "maa-agent"}])
                time.sleep(3)
                log(f"  + {name} created")
                return r["Role"]["Arn"]
            except iam.exceptions.MalformedPolicyDocumentException as e:
                if "Invalid principal" in str(e) and attempt < 5:
                    log(f"  ~ {name}: principal propagation lag, retry {attempt+1}/5 (10s)")
                    time.sleep(10)
                    continue
                raise
        raise


# Orchestrator role (Lambda) - created first so execution role can trust it
orch_trust = {"Version": "2012-10-17", "Statement": [
    {"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
orch_arn = ensure_role(ORCH_ROLE, orch_trust, "MAA AWS Agent orchestrator Lambda")

exec_trust = {"Version": "2012-10-17", "Statement": [
    {"Effect": "Allow", "Principal": {"AWS": [orch_arn, f"arn:aws:iam::{ACCT}:role/WSParticipantRole"]},
     "Action": "sts:AssumeRole",
     "Condition": {"StringEquals": {"sts:ExternalId": "maa-agent-exec"}}}]}
exec_arn = ensure_role(EXEC_ROLE, exec_trust, "MAA AWS Agent 5-minute execution session role")
kb_trust = {"Version": "2012-10-17", "Statement": [
    {"Effect": "Allow", "Principal": {"Service": "bedrock.amazonaws.com"}, "Action": "sts:AssumeRole",
     "Condition": {"StringEquals": {"aws:SourceAccount": ACCT}}}]}
kb_arn = ensure_role(KB_ROLE, kb_trust, "MAA AWS Agent Knowledge Base service role")
inst_trust = {"Version": "2012-10-17", "Statement": [
    {"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
ensure_role(INST_ROLE, inst_trust, "MAA demo EC2 instance profile (SSM core)")
try:
    iam.attach_role_policy(RoleName=INST_ROLE, PolicyArn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore")
    log(f"  {INST_ROLE}: AmazonSSMManagedInstanceCore attached")
except Exception:
    pass
try:
    ip = f"maa-demo-instance-profile"
    try:
        iam.get_instance_profile(InstanceProfileName=ip)
    except iam.exceptions.NoSuchEntityException:
        iam.create_instance_profile(InstanceProfileName=ip)
        time.sleep(2)
        iam.add_role_to_instance_profile(InstanceProfileName=ip, RoleName=INST_ROLE)
    log(f"  instance profile ready: {ip}")
except Exception as e:
    log(f"  instance profile warn: {str(e)[:150]}")
st.update(orch_role_arn=orch_arn, exec_role_arn=exec_arn, kb_role_arn=kb_arn)
save_state(st)

# ---- Orchestrator inline policy
orch_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {"Sid": "BedrockInvoke", "Effect": "Allow",
         "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream",
                    "bedrock:ApplyGuardrail", "bedrock:ListFoundationModels",
                    "bedrock:GetGuardrail", "bedrock:ListGuardrails"],
         "Resource": "*"},
        {"Sid": "KbRetrieve", "Effect": "Allow", "Action": ["bedrock-agent-runtime:Retrieve"],
         "Resource": f"arn:aws:bedrock:{REGION}:{ACCT}:knowledge-base/*"},
        {"Sid": "S3VectorsQuery", "Effect": "Allow",
         "Action": ["s3vectors:GetIndex", "s3vectors:QueryVectors", "s3vectors:ListVectors",
                    "s3vectors:GetVectors"],
         "Resource": f"arn:aws:s3vectors:{REGION}:{ACCT}:bucket/maa-agent-vectors*"},
        {"Sid": "Tables", "Effect": "Allow",
         "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan", "dynamodb:BatchWriteItem"],
         "Resource": [f"arn:aws:dynamodb:{REGION}:{ACCT}:table/{SESS_TABLE}",
                      f"arn:aws:dynamodb:{REGION}:{ACCT}:table/{SESS_TABLE}/index/*",
                      f"arn:aws:dynamodb:{REGION}:{ACCT}:table/{TRACE_TABLE}",
                      f"arn:aws:dynamodb:{REGION}:{ACCT}:table/{CONF_TABLE}"]},
        {"Sid": "KbDocs", "Effect": "Allow",
         "Action": ["s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
                    "s3:GetBucketLocation"],
         "Resource": [f"arn:aws:s3:::{KB_BUCKET}", f"arn:aws:s3:::{KB_BUCKET}/*"]},
        {"Sid": "Artifacts", "Effect": "Allow",
         "Action": ["s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:GetBucketLocation"],
         "Resource": [f"arn:aws:s3:::{ART_BUCKET}", f"arn:aws:s3:::{ART_BUCKET}/*"]},
        {"Sid": "KmsUse", "Effect": "Allow",
         "Action": ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"],
         "Resource": st["kms_arn"]},
        {"Sid": "CognitoAdmin", "Effect": "Allow",
         "Action": ["cognito-idp:AdminGetUser", "cognito-idp:AdminUserGlobalSignOut",
                    "cognito-idp:ListUsers", "cognito-idp:AdminUpdateUserAttributes"],
         "Resource": f"arn:aws:cognito-idp:{REGION}:{ACCT}:userpool/*"},
        {"Sid": "SelfInvoke", "Effect": "Allow",
         "Action": ["lambda:InvokeFunction", "lambda:GetFunction"],
         "Resource": f"arn:aws:lambda:{REGION}:{ACCT}:function:maa-agent-orchestrator*"},
        {"Sid": "AssumeExec", "Effect": "Allow", "Action": ["sts:AssumeRole"],
         "Resource": exec_arn,
         "Condition": {"StringEquals": {"sts:ExternalId": "maa-agent-exec"}}},
        {"Sid": "Logs", "Effect": "Allow",
         "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents",
                    "logs:DescribeLogStreams"],
         "Resource": f"arn:aws:logs:{REGION}:{ACCT}:*"},
    ],
}
iam.put_role_policy(RoleName=ORCH_ROLE, PolicyName="maa-agent-orchestrator-policy",
                    PolicyDocument=json.dumps(orch_policy))
log(f"  {ORCH_ROLE}: inline policy set")

# ---- Execution role policy (5-min privileged agent)
S3_CORE_DENY = [f"arn:aws:s3:::{KB_BUCKET}", f"arn:aws:s3:::{KB_BUCKET}/*",
                f"arn:aws:s3:::{ART_BUCKET}", f"arn:aws:s3:::{ART_BUCKET}/*"]
exec_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {"Sid": "Ec2", "Effect": "Allow",
         "Action": ["ec2:Describe*", "ec2:Get*", "ec2:CreateVpc", "ec2:CreateSubnet",
                    "ec2:CreateSecurityGroup", "ec2:CreateTags", "ec2:DeleteTags",
                    "ec2:CreateInternetGateway", "ec2:AttachInternetGateway",
                    "ec2:DetachInternetGateway", "ec2:DeleteInternetGateway",
                    "ec2:CreateRouteTable", "ec2:AssociateRouteTable",
                    "ec2:DisassociateRouteTable", "ec2:DeleteRouteTable",
                    "ec2:CreateRoute", "ec2:ReplaceRoute", "ec2:DeleteRoute",
                    "ec2:RunInstances", "ec2:StartInstances", "ec2:StopInstances",
                    "ec2:RebootInstances", "ec2:TerminateInstances",
                    "ec2:ModifyInstanceAttribute", "ec2:DeleteSecurityGroup",
                    "ec2:AuthorizeSecurityGroupIngress", "ec2:AuthorizeSecurityGroupEgress",
                    "ec2:RevokeSecurityGroupIngress", "ec2:RevokeSecurityGroupEgress",
                    "ec2:AllocateAddress", "ec2:ReleaseAddress", "ec2:AssociateAddress",
                    "ec2:CreateKeyPair", "ec2:DeleteKeyPair", "ec2:CreateSnapshot",
                    "ec2:DeleteSnapshot", "ec2:CreateImage", "ec2:DeregisterImage",
                    "ec2:GetConsoleOutput", "ec2:MonitorInstances", "ec2:UnmonitorInstances",
                    "ec2:DeleteVpc", "ec2:DeleteSubnet"],
         "Resource": "*",
         "Condition": {"Bool": {"aws:ViaAWSService": "false"}}},
        {"Sid": "Ec2RunTagRequired", "Effect": "Deny",
         "Action": "ec2:RunInstances",
         "Resource": "arn:aws:ec2:*:*:instance/*",
         "Condition": {"Null": {"aws:RequestTag/Project": "true"}}},
        {"Sid": "S3AgentOps", "Effect": "Allow",
         "Action": ["s3:ListAllMyBuckets", "s3:ListBucket", "s3:GetBucketLocation",
                    "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
                    "s3:GetBucketVersioning", "s3:GetEncryptionConfiguration", "s3:ListBucketVersions"],
         "Resource": "*"},
        {"Sid": "S3CoreProtect", "Effect": "Deny",
         "Action": ["s3:PutBucketPolicy", "s3:DeleteBucketPolicy", "s3:DeleteBucket"],
         "Resource": S3_CORE_DENY},
        {"Sid": "Rds", "Effect": "Allow",
         "Action": ["rds:Describe*", "rds:List*", "rds:CreateDBInstance", "rds:CreateDBCluster",
                    "rds:CreateDBSubnetGroup", "rds:DeleteDBInstance", "rds:DeleteDBCluster",
                    "rds:ModifyDBInstance", "rds:StopDBInstance", "rds:StartDBInstance",
                    "rds:AddTagsToResource", "rds:DeleteDBSubnetGroup", "rds:RebootDBInstance"],
         "Resource": "*"},
        {"Sid": "DdbAgent", "Effect": "Allow",
         "Action": ["dynamodb:ListTables", "dynamodb:DescribeTable", "dynamodb:GetItem",
                    "dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan",
                    "dynamodb:UpdateItem", "dynamodb:UpdateTable", "dynamodb:CreateTable",
                    "dynamodb:DeleteTable", "dynamodb:DescribeContinuousBackups"],
         "Resource": "*"},
        {"Sid": "LambdaAgent", "Effect": "Allow",
         "Action": ["lambda:List*", "lambda:Get*", "lambda:CreateFunction",
                    "lambda:DeleteFunction", "lambda:UpdateFunctionConfiguration",
                    "lambda:InvokeFunction", "lambda:TagResource", "lambda:UntagResource",
                    "lambda:AddPermission", "lambda:RemovePermission"],
         "Resource": "*"},
        {"Sid": "LambdaBrainProtect", "Effect": "Deny",
         "Action": ["lambda:UpdateFunctionCode", "lambda:DeleteFunction",
                    "lambda:UpdateFunctionConfiguration"],
         "Resource": f"arn:aws:lambda:{REGION}:{ACCT}:function:maa-agent-orchestrator"},
        {"Sid": "CloudWatch", "Effect": "Allow",
         "Action": ["cloudwatch:GetMetricData", "cloudwatch:GetMetricStatistics",
                    "cloudwatch:ListMetrics", "cloudwatch:DescribeAlarms",
                    "cloudwatch:PutMetricData", "logs:GetLogEvents", "logs:FilterLogEvents",
                    "logs:DescribeLogGroups", "logs:DescribeLogStreams", "logs:StartQuery",
                    "logs:GetQueryResults"],
         "Resource": "*"},
        {"Sid": "CostExplorer", "Effect": "Allow",
         "Action": ["ce:GetCostAndUsage", "ce:GetDimensionValues", "ce:GetCostForecast",
                    "ce:GetUsageReport", "budgets:ViewBudget"],
         "Resource": "*"},
        {"Sid": "Route53", "Effect": "Allow",
         "Action": ["route53:CreateHostedZone", "route53:DeleteHostedZone",
                    "route53:ListHostedZones", "route53:GetHostedZone",
                    "route53:ChangeResourceRecordSets", "route53:ListResourceRecordSets"],
         "Resource": "*"},
        {"Sid": "ElastiCache", "Effect": "Allow",
         "Action": ["elasticache:CreateCacheCluster", "elasticache:DeleteCacheCluster",
                    "elasticache:DescribeCacheClusters", "elasticache:RebootCacheCluster",
                    "elasticache:AddTagsToResource", "elasticache:CreateCacheSubnetGroup",
                    "elasticache:DeleteCacheSubnetGroup"],
         "Resource": "*"},
        {"Sid": "CfnIac", "Effect": "Allow",
         "Action": ["cloudformation:CreateStack", "cloudformation:DeleteStack",
                    "cloudformation:UpdateStack", "cloudformation:DescribeStacks",
                    "cloudformation:ValidateTemplate", "cloudformation:ListStacks",
                    "cloudformation:DescribeStackEvents", "cloudformation:GetTemplate",
                    "cloudformation:CreateChangeSet", "cloudformation:ExecuteChangeSet"],
         "Resource": "*"},
        {"Sid": "StsSelf", "Effect": "Allow", "Action": ["sts:GetCallerIdentity"], "Resource": "*"},
        # ---- Zero-trust explicit denies (PRD: the agent must not be able to escalate privileges)
        {"Sid": "NoIamTouch", "Effect": "Deny",
         "Action": ["iam:*", "organizations:*", "account:*", "cognito-idp:*", "cognito-identity:*",
                    "wafv2:*", "sso:*", "support:*"],
         "Resource": "*"},
        {"Sid": "NoKmsDestructive", "Effect": "Deny",
         "Action": ["kms:ScheduleKeyDeletion", "kms:DisableKey", "kms:PutKeyPolicy",
                    "kms:DeleteAlias", "kms:CreateKey"],
         "Resource": "*"},
        {"Sid": "NoAuditTamper", "Effect": "Deny",
         "Action": ["cloudtrail:StopLogging", "cloudtrail:DeleteTrail",
                    "cloudtrail:UpdateTrail", "logs:DeleteLogGroup"],
         "Resource": "*"},
        {"Sid": "NoBedrockInfraChange", "Effect": "Deny",
         "Action": ["bedrock:CreateAgent", "bedrock:CreateKnowledgeBase",
                    "bedrock:DeleteKnowledgeBase", "bedrock:DeleteGuardrail",
                    "bedrock:CreateGuardrail"],
         "Resource": "*"},
    ],
}
iam.put_role_policy(RoleName=EXEC_ROLE, PolicyName="maa-agent-execution-policy",
                    PolicyDocument=json.dumps(exec_policy))
log(f"  {EXEC_ROLE}: inline policy set (zero-trust denies embedded)")

# ---- KB service role policy
kb_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {"Sid": "S3Read", "Effect": "Allow",
         "Action": ["s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation"],
         "Resource": [f"arn:aws:s3:::{KB_BUCKET}", f"arn:aws:s3:::{KB_BUCKET}/*"]},
        {"Sid": "EmbedModel", "Effect": "Allow",
         "Action": ["bedrock:InvokeModel"],
         "Resource": [f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0",
                      f"arn:aws:bedrock:{REGION}::foundation-model/amazon.nova-lite-v1:0"]},
        {"Sid": "S3Vectors", "Effect": "Allow",
         "Action": ["s3vectors:GetIndex", "s3vectors:QueryVectors", "s3vectors:PutVectors",
                    "s3vectors:DeleteVectors", "s3vectors:GetVectors", "s3vectors:ListVectors"],
         "Resource": f"arn:aws:s3vectors:{REGION}:{ACCT}:bucket/maa-agent-vectors-{ACCT}*"},
        {"Sid": "KmsKb", "Effect": "Allow",
         "Action": ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"],
         "Resource": st["kms_arn"]},
    ],
}
iam.put_role_policy(RoleName=KB_ROLE, PolicyName="maa-agent-kb-policy",
                    PolicyDocument=json.dumps(kb_policy))
log(f"  {KB_ROLE}: inline policy set")

# ---------------------------------------------------------------- state
st.update(
    region=REGION, account_id=ACCT,
    kb_bucket=KB_BUCKET, art_bucket=ART_BUCKET,
    sessions_table=SESS_TABLE, traces_table=TRACE_TABLE, confirm_table=CONF_TABLE,
    orch_role=ORCH_ROLE, exec_role=EXEC_ROLE, kb_role=KB_ROLE, inst_role=INST_ROLE,
    inst_profile="maa-demo-instance-profile",
)
save_state(st)
log("=== FOUNDATION DEPLOY COMPLETE ===")
print(json.dumps({k: st[k] for k in ["kms_key_id", "kb_bucket", "art_bucket", "orch_role_arn", "exec_role_arn", "kb_role_arn"]}, indent=2))
