import os
import subprocess
import sys
import uvicorn
from app.config import get_settings


def _free_port(port: int) -> None:
    if sys.platform != "win32":
        return
    try:
        output = subprocess.check_output(["netstat", "-ano"], text=True)
        for line in output.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                pid = int(parts[-1])
                if pid == os.getpid():
                    continue
                try:
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                    print(f"  Freed port {port} (killed old PID {pid})")
                except Exception:
                    pass
    except Exception:
        pass


if __name__ == "__main__":
    settings = get_settings()
    _free_port(settings.app_port)
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.app_port, reload=False)
