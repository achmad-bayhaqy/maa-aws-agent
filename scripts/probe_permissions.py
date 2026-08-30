#!/usr/bin/env python3
"""Probe AWS permissions available to WSParticipantRole for MAA AWS Agent build."""
import boto3
import json

REGION = "us-east-1"
ROLE_ARN = "arn:aws:iam::590183948811:role/WSParticipantRole"

# Actions grouped by purpose
ACTIONS = {
    "Auth (Cognito)": [
        "cognito-idp:CreateUserPool",
        "cognito-idp:CreateUserPoolClient",
        "cognito-idp:AdminCreateUser",
        "cognito-idp:AdminInitiateAuth",
        "cognito-idp:AdminRespondToAuthChallenge",
        "cognito-idp:AssociateSoftwareToken",
        "cognito-idp:VerifySoftwareToken",
        "cognito-idp:AdminSetUserPassword",
        "cognito-idp:AdminGetUser",
        "cognito-idp:AdminDeleteUser",
    ],
    "Bedrock": [
        "bedrock:InvokeModel",
        "bedrock:CreateGuardrail",
        "bedrock:CreateKnowledgeBase",
        "bedrock:CreateDataSource",
        "bedrock:CreateAgent",
        "bedrock:Retrieve",
        "bedrock:ListFoundationModels",
        "bedrock:ApplyGuardrail",
    ],
    "AgentCore": [
        "bedrock-agentcore:CreateAgentRuntime",
        "bedrock-agentcore:InvokeAgentRuntime",
    ],
    "Compute/Infra": [
        "ec2:CreateVpc",
        "ec2:CreateSubnet",
        "ec2:CreateSecurityGroup",
        "ec2:RunInstances",
        "ec2:CreateRouteTable",
        "ec2:CreateInternetGateway",
        "ec2:AllocateAddress",
        "ec2:CreateTags",
        "cloudformation:CreateStack",
        "cloudcontrol:CreateResource",
    ],
    "IAM (for roles)": [
        "iam:CreateRole",
        "iam:PutRolePolicy",
        "iam:AttachRolePolicy",
        "iam:PassRole",
        "iam:ListRoles",
    ],
    "Lambda/APIGW/DDB": [
        "lambda:CreateFunction",
        "lambda:AddPermission",
        "apigatewayv2:CreateApi",
        "apigatewayv2:CreateStage",
        "dynamodb:CreateTable",
        "dynamodb:PutItem",
    ],
    "Storage": [
        "s3:CreateBucket",
        "s3:PutObject",
        "s3:GetObject",
        "s3:PutBucketPolicy",
        "efs:CreateFileSystem",
    ],
    "Security/Network edge": [
        "wafv2:CreateWebACL",
        "wafv2:AssociateWebACL",
        "kms:CreateKey",
        "kms:DescribeKey",
        "cloudfront:CreateDistribution",
        "amplify:CreateApp",
        "amplify:CreateBranch",
    ],
    "FinOps": [
        "ce:GetCostAndUsage",
        "ce:GetDimensionValues",
        "costexplorer:GetCostAndUsage",
        "cloudwatch:GetMetricData",
        "cloudwatch:GetMetricStatistics",
        "budgets:ViewBudget",
    ],
    "STS": [
        "sts:AssumeRole",
        "sts:GetFederationToken",
        "sts:GetSessionToken",
    ],
    "Logs/Trail": [
        "logs:CreateLogGroup",
        "logs:FilterLogEvents",
        "cloudtrail:LookupEvents",
        "cloudtrail:CreateTrail",
    ],
    "OpenSearch (for native KB)": [
        "osis:CreateCollection",
        "aoss:CreateCollection",
        "aoss:CreateAccessPolicy",
    ],
}

iam = boto3.client("iam", region_name=REGION)

print(f"{'='*70}")
print(f"PERMISSION MATRIX for {ROLE_ARN.split(':')[5]}")
print(f"{'='*70}")

allowed_total = 0
denied_list = []

for category, actions in ACTIONS.items():
    print(f"\n--- {category} ---")
    for action in actions:
        try:
            resp = iam.simulate_principal_policy(
                PolicySourceArn=ROLE_ARN,
                ActionNames=[action],
                ResourceArns=["*"],
            )
            decision = resp["EvaluationResults"][0]["EvalDecision"]
        except Exception as e:
            decision = f"error:{type(e).__name__}"
        if decision == "allowed":
            allowed_total += 1
        else:
            denied_list.append(f"{action} ({decision})")
        # compact print
        mark = "OK " if decision == "allowed" else "XX "
        print(f"  {mark} {action:45s} {decision}")

print(f"\n{'='*70}")
print(f"TOTAL ALLOWED: {allowed_total}")
print(f"DENIED ({len(denied_list)}):")
for d in denied_list:
    print(f"  - {d}")
