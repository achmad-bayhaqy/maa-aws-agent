#!/usr/bin/env python3
import botocore.session
import json

sess = botocore.session.get_session()
ctl = sess.get_service_model("bedrock-agentcore-control")


def dump(sh, d=0, seen=None, md=5):
    if sh is None or d > md:
        return "..."
    seen = seen or set()
    sid = (sh.name, id(sh))
    if sid in seen:
        return "<rec>"
    seen = seen | {sid}
    t = sh.type_name
    if t == "structure":
        return {"structure": {k: dump(v, d + 1, seen, md) for k, v in (sh.members or {}).items()}}
    if t == "list":
        return {"list": dump(sh.member, d + 1, seen, md)}
    return t + (f" enum={sh.enum}" if getattr(sh, "enum", None) else "")


cg = ctl.operation_model("CreateGateway").input_shape
print("CreateGateway.policyEngineConfiguration:", json.dumps(dump(cg.members.get("policyEngineConfiguration")), default=str))
print()
print("CreateGateway.authorizerConfiguration:", json.dumps(dump(cg.members.get("authorizerConfiguration")), default=str)[:500])
print()
print("CreateGateway.protocolConfiguration:", json.dumps(dump(cg.members.get("protocolConfiguration")), default=str))
print()
ug = ctl.operation_model("UpdateGateway").input_shape
print("UpdateGateway IN keys:", list(ug.members.keys()))
print("UpdateGateway.policyEngineConfiguration:", json.dumps(dump(ug.members.get("policyEngineConfiguration")), default=str))
cm = ctl.operation_model("CreateMemory").input_shape
sem = cm.members["memoryStrategies"].member.members["semanticMemoryStrategy"]
print()
print("semantic.namespaces:", json.dumps(dump(sem.members.get("namespaces")), default=str))
print("semantic.namespaceTemplates:", json.dumps(dump(sem.members.get("namespaceTemplates")), default=str))
cp = ctl.operation_model("CreatePolicy").input_shape
print()
print("CreatePolicy.definition:", json.dumps(dump(cp.members.get("definition")), default=str)[:400])
print("CreatePolicy target:", [k for k in cp.members.keys()])
