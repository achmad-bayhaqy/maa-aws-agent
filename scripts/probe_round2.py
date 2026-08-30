#!/usr/bin/env python3
"""Probe round 2: API GW v1, S3 Vectors, Amplify deploy, Lambda URL, KB runtime."""
import boto3

REGION = "us-east-1"
ROLE_ARN = "arn:aws:iam::590183948811:role/WSParticipantRole"

ACTIONS = {
    "API Gateway v1 (REST)": [
        "apigateway:CreateRestApi",
        "apigateway:CreateResource",
        "apigateway:PutMethod",
        "apigateway:CreateDeployment",
        "apigateway:CreateStage",
        "apigateway:GET",
        "apigateway:DELETE",
    ],
    "Lambda URL & mgmt": [
        "lambda:CreateFunctionUrlConfig",
        "lambda:UpdateFunctionConfiguration",
        "lambda:UpdateFunctionCode",
        "lambda:GetFunction",
        "lambda:InvokeFunction",
        "lambda:DeleteFunction",
        "lambda:TagResource",
    ],
    "S3 Vectors (KB murah)": [
        "s3vectors:CreateVectorBucket",
        "s3vectors:CreateIndex",
        "s3vectors:PutVectors",
        "s3vectors:QueryVectors",
    ],
    "Bedrock KB runtime": [
        "bedrock-agent-runtime:Retrieve",
        "bedrock-agent-runtime:RetrieveAndGenerate",
        "bedrock:StartIngestionJob",
        "bedrock:AssociateAgentKnowledgeBase",
        "bedrock:GetKnowledgeBase",
        "bedrock:DeleteKnowledgeBase",
        "bedrock:CreateGuardrailVersion",
        "bedrock:DeleteGuardrail",
    ],
    "Amplify deploy": [
        "amplify:CreateDeployment",
        "amplify:StartDeployment",
        "amplify:UpdateApp",
        "amplify:GetApp",
        "amplify:ListApps",
        "amplify:DeleteApp",
        "amplify:CreateDomainAssociation",
    ],
    "Cognito app-layer": [
        "cognito-idp:SignUp",
        "cognito-idp:InitiateAuth",
        "cognito-idp:RespondToAuthChallenge",
        "cognito-idp:AdminUpdateUserAttributes",
        "cognito-idp:AdminListGroupsForUser",
        "cognito-idp:ListUsers",
    ],
    "IAM misc": [
        "iam:CreateInstanceProfile",
        "iam:AddRoleToInstanceProfile",
        "iam:GetRole",
        "iam:DeleteRole",
        "iam:CreateOpenIDConnectProvider",
        "iam:TagRole",
    ],
    "EC2 runtime ops (agent)": [
        "ec2:DescribeInstances",
        "ec2:DescribeImages",
        "ec2:DescribeVpcs",
        "ec2:StartInstances",
        "ec2:StopInstances",
        "ec2:TerminateInstances",
        "ec2:DeleteVpc",
        "ec2:ModifyInstanceAttribute",
        "ec2:DescribeInstanceStatus",
    ],
    "RDS/S3 agent ops": [
        "rds:CreateDBInstance",
        "rds:CreateDBCluster",
        "rds:DeleteDBInstance",
        "rds:DescribeDBInstances",
        "s3:DeleteBucket",
        "s3:ListAllMyBuckets",
        "s3:GetBucketPolicy",
    ],
    "Misc": [
        "route53:CreateHostedZone",
        "elasticache:CreateCacheCluster",
        "sts:DecodeAuthorizationMessage",
        "account:GetAlternateContact",
        "cloudwatch:PutMetricData",
        "application-autoscaling:DescribeScalableTargets",
    ],
}

iam = boto3.client("iam", region_name=REGION)

allowed_total = 0
denied_list = []
for category, actions in ACTIONS.items():
    print(f"\n--- {category} ---")
    for action in actions:
        try:
            resp = iam.simulate_principal_policy(
                PolicySourceArn=ROLE_ARN, ActionNames=[action], ResourceArns=["*"]
            )
            decision = resp["EvaluationResults"][0]["EvalDecision"]
        except Exception as e:
            decision = f"error:{type(e).__name__}"
        if decision == "allowed":
            allowed_total += 1
        else:
            denied_list.append(f"{action} ({decision})")
        mark = "OK " if decision == "allowed" else "XX "
        print(f"  {mark} {action:45s} {decision}")

print(f"\nTOTAL ALLOWED: {allowed_total}, DENIED: {len(denied_list)}")
for d in denied_list:
    print(f"  - {d}")
