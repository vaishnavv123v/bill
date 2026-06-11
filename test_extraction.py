
import os
import sys

# Add project to path
sys.path.append(r'g:\snit projects\INTELLIGENT HEALTHCARE\healthcare_transparency')

try:
    from healthcare_app.ai_engine import ocr_extract_text, extract_data, extract_metadata
    
    test_file = r'g:\snit projects\INTELLIGENT HEALTHCARE\healthcare_transparency\media\bills\Provisional-Hospital-Bill.png'
    if os.path.exists(test_file):
        print(f"Testing with: {test_file}")
        text = ocr_extract_text(test_file)
        print("\n--- METADATA ---")
        meta = extract_metadata(text)
        print(meta)
        print("\n--- EXTRACTED ITEMS ---")
        items = extract_data(text)
        for item in items:
            print(item)
    else:
        print("Test file not found.")
except Exception as e:
    print(f"Error: {e}")
