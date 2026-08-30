#!/usr/bin/env python3
import botocore.session

sess = botocore.session.get_session()
dat = sess.get_service_model("bedrock-agentcore")
ib = dat.operation_model("InvokeBrowser").input_shape
act = ib.members["action"]  # union shape
keys = sorted(getattr(act, "members", {}).keys())
if not keys and getattr(act, "member", None) is not None:
    keys = sorted(act.member.members.keys())
print("InvokeBrowser.action members:", keys)
for k in ("navigate", "extractContent", "waitForNavigation", "scrollIntoView"):
    if k in (act.members or {}):
        sub = act.members[k].member if hasattr(act.members[k], "member") else act.members[k]
        print(f"  {k}:", list(sub.members.keys()))
r = dat.operation_model("RetrieveMemoryRecords").input_shape
print("RetrieveMemoryRecords members:", list(r.members.keys()))
sc = r.members.get("searchCriteria")
scm = getattr(sc, "member", None)
if scm is not None:
    print("searchCriteria:", list(scm.members.keys()))
    for kk in ("textQuery", "topK"):
        if kk in (scm.members or {}):
            print("   ", kk, scm.members[kk])
