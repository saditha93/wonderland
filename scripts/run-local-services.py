"""Start four health-only APIs without Docker; stop all with Ctrl-C."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ['attractions-service', 'booking-service', 'gate-ride-service', 'analytics-worker']
children = []

def stop(signum, frame):
    raise KeyboardInterrupt

signal.signal(signal.SIGTERM, stop)
try:
    for port, name in enumerate(SERVICES, 8001):
        children.append(subprocess.Popen([
            sys.executable, '-m', 'uvicorn', 'app.main:app', '--app-dir', str(ROOT/'services'/name),
            '--host', '127.0.0.1', '--port', str(port), '--no-access-log',
        ], cwd=ROOT, env={**os.environ, 'APP_ENVIRONMENT': 'local'}))
    while True:
        if any(child.poll() is not None for child in children):
            raise RuntimeError('A service exited; inspect output and check for occupied ports.')
        time.sleep(0.5)
except KeyboardInterrupt:
    pass
finally:
    for child in children:
        if child.poll() is None: child.terminate()
    for child in children:
        try: child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
