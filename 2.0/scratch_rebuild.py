import os
import shutil
from assistant import CollegeAssistant

def main():
    print("Deleting old index...")
    if os.path.exists("index"):
        shutil.rmtree("index")
        
    print("Running assistant setup to rebuild base index...")
    assistant = CollegeAssistant()
    assistant.setup()
    
    ocr_file = "Revised  Time Table BTI CE Sem VI Div D.pdf w.e.f. 12.01.2026_ocr.txt"
    if os.path.exists(ocr_file):
        print(f"Adding user file: {ocr_file}")
        assistant.processor.add_new_file(ocr_file, user_id=1)
        print("Done!")
    else:
        print(f"File {ocr_file} not found!")
        
if __name__ == "__main__":
    main()
