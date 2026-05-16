import pandas as pd
import json
import fitz  # pymupdf
import os

def convert_excel_to_json(excel_path, json_path):
    print(f"Converting {excel_path} to {json_path}")
    try:
        # Read all sheets
        dfs = pd.read_excel(excel_path, sheet_name=None)
        all_data = {}
        for sheet, df in dfs.items():
            # Convert to dict, records format
            # Using fillna("") to avoid NaN in JSON
            all_data[sheet] = df.fillna("").to_dict(orient="records")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error converting {excel_path}: {e}")

def convert_pdf_to_json(pdf_path, json_path):
    print(f"Converting {pdf_path} to {json_path}")
    try:
        doc = fitz.open(pdf_path)
        pages = []
        for i, page in enumerate(doc):
            pages.append({
                "page_number": i + 1,
                "text": page.get_text()
            })
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(pages, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error converting {pdf_path}: {e}")

if __name__ == "__main__":
    convert_excel_to_json("Faculty and staff_Seating_list Dec 2025.xlsx", "faculty_sitting.json")
    convert_pdf_to_json("Div C - Timetable - 2025-2026.pdf", "timetable_pdf.json")
    convert_excel_to_json("Personal_TT_Even_Sem_2025-26.xlsx", "timetable_xlsx.json")
    print("Conversion complete.")
