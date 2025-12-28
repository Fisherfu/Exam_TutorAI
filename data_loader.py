import os
from docx import Document

MATERIALS_DIR = "materials"

def load_materials():
    """
    Reads all .docx files from the 'materials' directory.
    Returns a dictionary: { "Filename_without_ext": "Full text content..." }
    """
    materials = {}
    base_path = os.path.dirname(os.path.abspath(__file__))
    materials_path = os.path.join(base_path, MATERIALS_DIR)

    if not os.path.exists(materials_path):
        print(f"Warning: Materials directory not found at {materials_path}")
        return materials

    print(f"Loading materials from: {materials_path}")

    for filename in sorted(os.listdir(materials_path)):
        if filename.endswith(".docx") and not filename.startswith("~$"):
            file_path = os.path.join(materials_path, filename)
            try:
                doc = Document(file_path)
                full_text = []
                for para in doc.paragraphs:
                    if para.text.strip(): # Skip empty lines
                        full_text.append(para.text)
                
                # Use filename as key (e.g., "W1_2025")
                key = os.path.splitext(filename)[0]
                content = "\n".join(full_text)
                materials[key] = content
                print(f"Loaded: {key} ({len(content)} chars)")
            except Exception as e:
                print(f"Error reading {filename}: {e}")
    
    return materials

if __name__ == "__main__":
    # Test run
    data = load_materials()
    print(f"Total topics loaded: {len(data)}")
    for key in data:
        print(f"- {key}: {len(data[key])} chars")
