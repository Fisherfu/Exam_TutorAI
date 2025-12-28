import sys
print(f"Python Executable: {sys.executable}")
try:
    import streamlit as st
    print("Streamlit imported successfully!")
    print(f"Streamlit version: {st.__version__}")
except ImportError as e:
    print(f"Error importing streamlit: {e}")
except Exception as e:
    print(f"An error occurred: {e}")
