#!/usr/bin/env python3
import botocore.session

sess = botocore.session.get_session()
dat = sess.get_service_model("bedrock-agentcore")
ctl = sess.get_service_model("bedrock-agentcore-control")


def dump(sh, d=0, seen=None, md=4):
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
    if t == "map":
        return {"map": {"k": dump(sh.key, d + 1, seen, md), "v": dump(sh.value, d + 1, seen, md)}}
    return t + (f" enum={sh.enum}" if getattr(sh, "enum", None) else "")


import json

for svc, op in [(dat, "Evaluate"), (dat, "UpdateBrowserStream"), (ctl, "CreateOnlineEvaluationConfig"), (ctl, "CreateHarness")]:
    try:
        om = svc.operation_model(op)
        print("###", op, "IN:", json.dumps(dump(om.input_shape), default=str)[:1400], "\n")
    except Exception as e:
        print("###", op, "ERR", str(e)[:150], "\n")
