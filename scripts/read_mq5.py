
import os
import shutil

file_path = r"d:\Internal\signals-bot\mql5\SimpleDataServer.mq5"
temp_path = r"d:\Internal\signals-bot\mql5\SimpleDataServer_utf8.mq5"

def convert_to_utf8():
    encodings = ['utf-16', 'utf-8', 'cp1252']
    success = False
    content = ""
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                content = f.read()
                # Basic check to see if it looks like code
                if "void OnStart" in content or "int OnInit" in content:
                    print(f"--- Successfully read with {enc} ---")
                    success = True
                    break
        except Exception:
            pass
            
    if success:
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Converted to {temp_path}")
    else:
        print("Failed to read file.")

if __name__ == "__main__":
    convert_to_utf8()
