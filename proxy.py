import subprocess
import os
import json
import csv
import threading
from flask import Flask, request, Response
import requests
import logging

BACKEND_URL = "http://localhost:8080"
PROXY_PORT = 8081
GET_DIFF_COMMAND = ["sudo", "./fuse_rust/target/release/get_diff"]
RESULTS_DIR = "results_plus_compression"

app = Flask(__name__)

csv_lock = threading.Lock()

def write_to_csv(filename, data_dict):
    if not os.path.exists(RESULTS_DIR):
        os.makedirs(RESULTS_DIR)
        
    filepath = os.path.join(RESULTS_DIR, filename)
    
    fieldnames = ['method', 'path', 'backend_status', 'body_size', 'statediff_size', 'body']

    with csv_lock:
        file_exists = os.path.isfile(filepath)
        
        with open(filepath, mode='a', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            if not file_exists:
                writer.writeheader()
            
            writer.writerow(data_dict)

@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy_request(path):
    # 1. Get Filename from K6 Header
    target_filename = request.headers.get('X-Log-Filename', 'default_proxy_log.csv')

    # 2. Forward to Backend
    try:
        request_body_bytes = request.get_data()
        
        # Remove custom header so the backend doesn't see it
        forward_headers = {k: v for k, v in request.headers.items() 
                           if k not in ['Host', 'X-Log-Filename']}

        backend_response = requests.request(
            method=request.method,
            url=f"{BACKEND_URL}/{path}",
            headers=forward_headers,
            data=request_body_bytes,
            allow_redirects=False
        )
    except requests.exceptions.ConnectionError:
        print(f"[PROXY] ERROR: Could not connect to backend at {BACKEND_URL}.")
        return "Proxy Error", 502

    # 3. Run get_diff (Statediff measurement)
    statediff_size = 0
    try:
        process = subprocess.run(
            GET_DIFF_COMMAND,
            capture_output=True,
            check=False,
            cwd=os.getcwd()
        )
        statediff_size = len(process.stdout)
        
        if process.returncode != 0:
            stderr = process.stderr.decode('utf-8', errors='ignore').strip()
            print(f"[PROXY] WARNING: get_diff failed (code {process.returncode}): {stderr}")
            
    except Exception as e:
        print(f"[PROXY] ERROR: Exception running get_diff: {e}")

    # 4. Log to CSV
    try:
        request_body_str = request_body_bytes.decode('utf-8', errors='ignore')
        
        log_entry = {
            "method": request.method,
            "path": f"/{path}",
            "backend_status": backend_response.status_code,
            "body_size": len(request_body_bytes),
            "statediff_size": statediff_size,
            "body": request_body_str
        }
        
        write_to_csv(target_filename, log_entry)
        print(f"[PROXY] Logged {request.method} /{path} to {target_filename}")
        
    except Exception as e:
        print(f"[PROXY] ERROR: Failed to write to CSV: {e}")

    # 5. Return Response
    excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
    headers = [
        (k, v) for k, v in backend_response.raw.headers.items()
        if k.lower() not in excluded_headers
    ]

    return Response(backend_response.content, backend_response.status_code, headers)

@app.route('/')
def root_proxy():
    return proxy_request('')

if __name__ == '__main__':
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    print(f"--- Proxy Server Running on port {PROXY_PORT} ---")
    print(f"--- Saving CSVs to ./{RESULTS_DIR}/ ---")
    app.run(host='0.0.0.0', port=PROXY_PORT)
