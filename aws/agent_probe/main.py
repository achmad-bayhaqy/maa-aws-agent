import json
import platform
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

INFO = {}


def collect():
    if INFO:
        return INFO
    INFO["python"] = platform.python_version()
    INFO["machine"] = platform.machine()
    try:
        import boto3
        INFO["boto3"] = boto3.__version__
    except Exception as e:
        INFO["boto3"] = f"MISSING: {type(e).__name__}"
    try:
        import botocore
        INFO["botocore"] = botocore.__version__
    except Exception as e:
        INFO["botocore"] = f"MISSING: {type(e).__name__}"
    try:
        import bedrock_agentcore
        INFO["bedrock_agentcore"] = getattr(bedrock_agentcore, "__version__", "present")
    except Exception as e:
        INFO["bedrock_agentcore"] = f"MISSING: {type(e).__name__}"
    try:
        import fastapi
        INFO["fastapi"] = fastapi.__version__
    except Exception as e:
        INFO["fastapi"] = f"MISSING: {type(e).__name__}"
    return INFO


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"status": "Healthy"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        body = json.dumps(collect()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), H).serve_forever()
