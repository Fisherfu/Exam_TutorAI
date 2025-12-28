import sys
from streamlit.web import cli as stcli

if __name__ == "__main__":
    sys.argv = ["streamlit", "run", "app.py"]
    print("Launching Streamlit via Python script...")
    sys.exit(stcli.main())
