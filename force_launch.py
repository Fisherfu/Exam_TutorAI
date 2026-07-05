import subprocess
import sys
import os

# Reconfigure stdout/stderr to UTF-8 to avoid UnicodeEncodeError on Windows cp950 consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def check_streamlit(python_path):
    """Check if streamlit is installed in the given python environment"""
    try:
        subprocess.check_call(
            [python_path, "-c", "import streamlit"], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        return True
    except:
        return False

# 1. Inspect Current Environment
current_python = sys.executable
print(f"[*] Checking environment: {current_python}")

if check_streamlit(current_python):
    target_python = current_python
else:
    print("[x] Streamlit not found in current environment.")
    # 2. Try to find Anaconda Python (Known Good)
    anaconda_python = r"C:\Users\USER\anaconda3\python.exe"
    print(f"[?] Searching for Anaconda: {anaconda_python}")
    
    if os.path.exists(anaconda_python) and check_streamlit(anaconda_python):
        print("[+] Found valid Anaconda Python! Switching engine...")
        target_python = anaconda_python
    else:
        print("\n[-] Could not find a Python environment with Streamlit installed.")
        print("Please run: pip install streamlit")
        input("Press Enter to exit...")
        sys.exit(1)

# 3. Launch with the Valid Python
print(f"[+] Launching with: {target_python}")
cmd = [target_python, "-m", "streamlit", "run", "app.py", "--server.headless=true"]

try:
    print("--------------------------------------------------")
    print("Starting Streamlit Server (Press Ctrl+C to stop)")
    print("--------------------------------------------------")
    
    # Run as subprocess
    p = subprocess.Popen(cmd)
    p.wait()

except KeyboardInterrupt:
    p.terminate()
except Exception as e:
    print(f"Launch Error: {e}")
    input("Press Enter...")
