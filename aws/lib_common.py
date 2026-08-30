#!/usr/bin/env python3
"""MAA AWS Agent - lib: shared helpers for deploy scripts."""
import json
import os
import time

import boto3

STATE_PATH = "/home/z/my-project/aws/state.json"
REGION = "us-east-1"
PREFIX = "maa-agent"

_session = boto3.Session(region_name=REGION)
sts = _session.client("sts")
ACCOUNT_ID = sts.get_caller_identity()["Account"]


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, default=str)
    return state


def update_state(**kv):
    st = load_state()
    st.update(kv)
    save_state(st)
    return st


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def try_call(fn, label, retries=3, delay=5, raise_on_fail=False, **kwargs):
    """Idempotent-friendly AWS call with retry on throttling."""
    for i in range(retries):
        try:
            return fn(**kwargs)
        except Exception as e:
            code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
            msg = str(e)
            if "AlreadyExists" in msg or "EntityAlreadyExists" in msg or "ResourceAlreadyExists" in msg or "Duplicate" in msg:
                log(f"  = {label} already exists, skipping")
                return None
            if code in ("ThrottlingException", "TooManyRequestsException", "Throttling", "LimitExceededException") and i < retries - 1:
                log(f"  ~ {label} throttled, retry {i+1}/{retries} in {delay}s")
                time.sleep(delay)
                continue
            if raise_on_fail:
                raise
            log(f"  X {label} FAILED: {msg[:200]}")
            return None
    return None
