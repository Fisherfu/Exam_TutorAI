import subprocess
import sys
import time

print("--- DIAGNOSTIC START ---")
print(f"Python: {sys.executable}")

# Try running streamlit hello first as a baseline
cmd = [sys.executable, "-m", "streamlit", "run", "app.py"]
print(f"Executing: {' '.join(cmd)}")

try:
    # Run and stream output
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        encoding='utf-8',
        errors='replace' # Handle potential encoding errors
    )
    
    print("Process started with PID:", process.pid)
    
    # Wait a bit to see if it crashes immediately
    time.sleep(3)
    
    if process.poll() is not None:
        print("Process exited prematurely!")
        stdout, stderr = process.communicate()
        print("STDOUT:\n", stdout)
        print("STDERR:\n", stderr)
    else:
        print("Process is still running (Good Sign). Terminating for check...")
        process.terminate()
        stdout, stderr = process.communicate()
        print("STDOUT (First 3s):\n", stdout)
        print("STDERR (First 3s):\n", stderr)

except Exception as e:
    print(f"Diagnostic Error: {e}")

print("--- DIAGNOSTIC END ---")
