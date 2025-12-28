import os
import pyzipper
from io import BytesIO
from docx import Document
import streamlit as st
from dotenv import load_dotenv

# Load environment variables (for local dev)
env_path = os.path.join(os.getcwd(), '.env')
print(f"[Debug] Loading env from: {env_path}, Exists: {os.path.exists(env_path)}")
load_dotenv(dotenv_path=env_path)

def get_material_password():
    """Retrieve password from environment or Streamlit secrets."""
    # Priority 1: Streamlit Secrets (Cloud)
    try:
        if "MATERIALS_PASSWORD" in st.secrets:
            return st.secrets["MATERIALS_PASSWORD"].encode()
    except FileNotFoundError:
        pass # Secrets file not found, use env vars
    except Exception:
        pass # Other streamlit errors

    # Priority 2: Environment Variable (Local)
    return os.getenv("MATERIALS_PASSWORD", "").encode()

def load_materials():
    """
    Loads course materials from an encrypted ZIP file.
    Returns: dict {topic_name: text_content}
    """
    materials = {}
    zip_path = "materials.zip"
    
    password = get_material_password()
    
    if not os.path.exists(zip_path):
        st.error(f"❌ Error: {zip_path} not found!")
        return materials

    
    
    if not password:
        print("[Error] No password loaded! Check .env or secrets.")
    else:
        print("[Info] Password loaded successfully.")

    try:
        with pyzipper.AESZipFile(zip_path, 'r') as zf:
            if password:
                zf.setpassword(password)
            
            # List all docx files
            docx_files = [name for name in zf.namelist() if name.endswith('.docx')]
            
            for filename in docx_files:
                # Extract week number (e.g., W1_2025.docx -> Week 1)
                week_num = filename.split('_')[0].replace('W', '').replace('-', '')
                topic_name = f"Week {week_num}" if week_num.isdigit() else filename
                
                # Read file content
                file_data = zf.read(filename)
                doc = Document(BytesIO(file_data))
                
                # Extract text
                text_content = '\n'.join([para.text for para in doc.paragraphs if para.text.strip()])
                materials[topic_name] = text_content
                
        return materials
    
    except RuntimeError as e:
        msg = f"[Error] Decryption failed! Wrong password or corrupted file: {e}"
        print(msg)
        # st.error(msg) # Streamlit error might be fine in app, but print is safer for console
        return materials
    except Exception as e:
        msg = f"[Error] Loading materials failed: {e}"
        print(msg)
        return materials


if __name__ == "__main__":
    # Test run
    data = load_materials()
    print(f"Total topics loaded: {len(data)}")
    for key in data:
        print(f"- {key}: {len(data[key])} chars")
