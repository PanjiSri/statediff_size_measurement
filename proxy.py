import subprocess
import os
import json
from flask import Flask, request, Response
import requests
import logging

BACKEND_URL = "http://localhost:8080"

PROXY_PORT = 8081

GET_DIFF_COMMAND = ["sudo", "./fuse_rust/target/release/get_diff"]

app = Flask(__name__)

@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy_request(path):
    # 1. Forward the request to the app
    try:
        request_body_bytes = request.get_data()

        backend_response = requests.request(
            method=request.method,
            url=f"{BACKEND_URL}/{path}",
            headers={key: value for (key, value) in request.headers if key != 'Host'},
            data=request_body_bytes,
            allow_redirects=False
        )
    except requests.exceptions.ConnectionError as e:
        print(f"[PROXY] ERROR: Could not connect to backend at {BACKEND_URL}.")
        return "Proxy could not connect to the backend service.", 502

    # 2. Execute get_diff command immediately after the backend response is received
    try:
        process = subprocess.run(
            GET_DIFF_COMMAND,
            capture_output=True,
            check=False,
            cwd=os.getcwd()
        )

        # 3. Measure and log the statediff size
        statediff_size = len(process.stdout)

        if process.returncode != 0:
            stderr_output = process.stderr.decode('utf-8', errors='ignore').strip()
            print(f"[PROXY] WARNING: 'get_diff' command failed with code {process.returncode}. Stderr: {stderr_output}")

        request_body_str = request_body_bytes.decode('utf-8', errors='ignore')

        log_data = {
            "method": request.method,
            "path": f"/{path}",
            "body_size": len(request_body_bytes),
            "body": request_body_str,
            "backend_status": backend_response.status_code,
            "statediff_size": statediff_size,
        }
        
        print(f"[PROXY_LOG] {json.dumps(log_data)}")

    except FileNotFoundError:
        print(f"[PROXY] ERROR: Command '{' '.join(GET_DIFF_COMMAND)}' not found.")
    except Exception as e:
        print(f"[PROXY] ERROR: An unexpected error occurred while running get_diff: {e}")


    # 4. Return the original response from the backend to the client
    excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
    headers = [
        (name, value) for (name, value) in backend_response.raw.headers.items()
        if name.lower() not in excluded_headers
    ]

    return Response(backend_response.content, backend_response.status_code, headers)

@app.route('/')
def root_proxy():
    return proxy_request('')

if __name__ == '__main__':
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    print(f"--- Starting Proxy Server ---")
    print(f"Listening on http://0.0.0.0:{PROXY_PORT}")
    print(f"Forwarding requests to: {BACKEND_URL}")
    print(f"---------------------------")
    app.run(host='0.0.0.0', port=PROXY_PORT)