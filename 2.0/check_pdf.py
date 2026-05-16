import PyPDF2

with open("SRB 2025.pdf", "rb") as f:
    reader = PyPDF2.PdfReader(f)
    print(f"Total pages: {len(reader.pages)}")
    print("\nFirst page text:")
    print(reader.pages[3].extract_text()[:2000])