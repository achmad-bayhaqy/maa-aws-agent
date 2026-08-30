#!/usr/bin/env python3
import botocore.session
import json

sess = botocore.session.get_session()
dat = sess.get_service_model("bedrock-agentcore")


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


sbs = dat.operation_model("StartBrowserSession")
print("OUT:", json.dumps(dump(sbs.output_shape), default=str)[:1300])
gbs = dat.operation_model("GetBrowserSession")
print()
print("GetBrowserSession OUT:", json.dumps(dump(gbs.output_shape), default=str)[:1300])
ici = dat.operation_model("InvokeCodeInterpreter")
print()
print("InvokeCodeInterpreter OUT:", json.dumps(dump(ici.output_shape), default=str)[:900])
rc = dat.operation_model("RetrieveMemoryRecords").input_shape
sc = rc.members["searchCriteria"]
inner = getattr(sc, "member", None) or sc
print()
print("searchCriteria:", json.dumps(dump(inner), default=str)[:900])
ev = dat.operation_model("CreateEvent").input_shape
print()
print("extractionConfig:", json.dumps(dump(ev.members.get("extractionConfig")), default=str)[:400])
