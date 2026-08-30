#!/usr/bin/env python3
"""Probe detail #2: shapes rekursif untuk Gateway target, Memory strategies, Browser ops."""
import json

import botocore.session

sess = botocore.session.get_session()
ctl = sess.get_service_model("bedrock-agentcore-control")
dat = sess.get_service_model("bedrock-agentcore")

print("ALL bedrock-agentcore ops:")
print(sorted(dat.operation_names))
print()

print("ALL bedrock-agentcore-control ops:")
print(sorted(ctl.operation_names))
print()


def dump_shape(sh, depth=0, seen=None, max_depth=6):
    if sh is None or depth > max_depth:
        return "..."
    seen = seen or set()
    sid = (sh.name, id(sh))
    if sid in seen:
        return "<recursion>"
    seen = seen | {sid}
    t = sh.type_name
    if t == "structure":
        out = {}
        for k, v in (sh.members or {}).items():
            out[k] = dump_shape(v, depth + 1, seen, max_depth)
        return {"structure": out}
    if t == "list":
        return {"list": dump_shape(sh.member, depth + 1, seen, max_depth)}
    if t == "map":
        return {"map": {"k": dump_shape(sh.key, depth + 1, seen, max_depth), "v": dump_shape(sh.value, depth + 1, seen, max_depth)}}
    return t + (f" enum={sh.enum}" if getattr(sh, "enum", None) else "")


for op in ["CreateGatewayTarget", "CreateMemory", "CreateGateway", "CreateCodeInterpreter", "CreatePolicy", "CreateEvaluator"]:
    try:
        om = ctl.operation_model(op)
        print(f"### ctl.{op} IN:\n", json.dumps(dump_shape(om.input_shape), indent=1, default=str)[:3500], "\n")
    except Exception as e:
        print(f"### ctl.{op} ERR {e}\n")

for op in ["CreateCodeInterpreter", "StartBrowserSession", "CreateEvent", "RetrieveMemoryRecords"]:
    try:
        om = dat.operation_model(op)
        print(f"### dat.{op} IN:\n", json.dumps(dump_shape(om.input_shape), indent=1, default=str)[:2500], "\n")
    except Exception as e:
        print(f"### dat.{op} ERR {e}\n")
