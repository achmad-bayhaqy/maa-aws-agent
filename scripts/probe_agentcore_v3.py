#!/usr/bin/env python3
"""Probe botocore 1.43.83 untuk API AgentCore v3: Memory, Gateway, Identity, CodeInterpreter, Browser, Observability."""
import json

import botocore.session

sess = botocore.session.get_session()


def shape_of(svc, op):
    try:
        m = sess.get_service_model(svc)
        om = m.operation_model(op)
        sh = om.output_shape
        ins = om.input_shape
        out_keys = list(sh.members.keys()) if sh else []
        in_keys = list(ins.members.keys()) if ins else []
        # enum discovery
        enums = []
        for name, member in list((ins.members or {}).items()) if ins else []:
            e = getattr(member, "enum", None) or getattr(getattr(member, "member", None), "enum", None)
            if e:
                enums.append({"in": name, "enum": e})
        return {"in": in_keys, "out": out_keys, "enums": enums[:8]}
    except Exception as e:
        return {"error": str(e)[:120]}


ctl = "bedrock-agentcore-control"
dat = "bedrock-agentcore"

ops_ctl = [
    "CreateMemory", "GetMemory", "ListMemories", "DeleteMemory",
    "CreateGateway", "GetGateway", "ListGateways", "DeleteGateway",
    "CreateGatewayTarget", "GetGatewayTarget", "ListGatewayTargets", "DeleteGatewayTarget",
    "CreateWorkloadIdentity", "GetWorkloadIdentity", "ListWorkloadIdentities", "DeleteWorkloadIdentity",
    "CreatePolicy", "ListPolicies", "CreatePolicyEngine",
    "CreateEvaluator", "ListEvaluators", "StartEvaluation",
    "CreateAgentRuntime", "GetAgentRuntime",
]
ops_dat = [
    "CreateEvent", "GetEvent", "ListEvents", "DeleteEvent",
    "RetrieveMemoryRecords", "ListMemoryRecords",
    "CreateCodeInterpreter", "StartCodeInterpreterSession", "InvokeCodeInterpreter",
    "StopCodeInterpreterSession", "DeleteCodeInterpreter", "ListCodeInterpreters",
    "StartBrowserSession", "StopBrowserSession", "ListBrowserSessions",
    "InvokeAgentRuntime", "GetAgentRuntimeEndpoint",
]

print("=== bedrock-agentcore-control ===")
for op in ops_ctl:
    print(op, json.dumps(shape_of(ctl, op), default=str)[:700])

print("=== bedrock-agentcore (data plane) ===")
for op in ops_dat:
    print(op, json.dumps(shape_of(dat, op), default=str)[:700])

# detail enum penting
try:
    m = sess.get_service_model(ctl)
    gw = m.operation_model("CreateGateway").input_shape
    print("CreateGateway.authorizerType enum:", gw.members.get("authorizerType").enum if gw.members.get("authorizerType") else None)
    print("CreateGateway members:", list(gw.members.keys()))
    gt = m.operation_model("CreateGatewayTarget").input_shape
    print("CreateGatewayTarget members:", list(gt.members.keys()))
    for k, v in gt.members.items():
        if hasattr(v, "members"):
            print("  target.", k, "->", list(v.members.keys()))
    mm = m.operation_model("CreateMemory").input_shape
    print("CreateMemory members:", list(mm.members.keys()))
    for k, v in mm.members.items():
        if hasattr(v, "members"):
            print("  memory.", k, "->", list(v.members.keys()))
        if getattr(v, "enum", None):
            print("  memory.", k, "enum", v.enum)
except Exception as e:
    print("detail err", e)

try:
    m2 = sess.get_service_model(dat)
    ice = m2.operation_model("InvokeCodeInterpreter").input_shape
    print("InvokeCodeInterpreter members:", list(ice.members.keys()))
    for k, v in ice.members.items():
        if getattr(v, "enum", None):
            print("  ", k, "enum", v.enum)
    sbs = m2.operation_model("StartBrowserSession").input_shape
    print("StartBrowserSession members:", list(sbs.members.keys()))
    iar = m2.operation_model("InvokeAgentRuntime").input_shape
    print("InvokeAgentRuntime members:", list(iar.members.keys()))
except Exception as e:
    print("detail2 err", e)
