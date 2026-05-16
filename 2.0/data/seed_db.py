import json
from database import SessionLocal, Timetable, FacultySeating

def seed():
    db = SessionLocal()
    
    print("Clearing old data...")
    db.query(Timetable).delete()
    db.query(FacultySeating).delete()
    db.commit()

    print("Seeding Faculty Seating...")
    try:
        with open('faculty_sitting.json', 'r', encoding='utf-8') as f:
            fac_data = json.load(f)
            for category, rows in fac_data.items():
                for row in rows:
                    db.add(FacultySeating(category=category, row_data=row))
    except Exception as e:
        print("Error loading faculty seating:", e)
                
    print("Seeding Excel Timetable...")
    try:
        with open('timetable_xlsx.json', 'r', encoding='utf-8') as f:
            tt_data = json.load(f)
            for sheet, rows in tt_data.items():
                for row in rows:
                    db.add(Timetable(sheet_name=sheet, row_data=row))
    except Exception as e:
        print("Error loading Excel timetable:", e)
                
    print("Seeding PDF Timetable...")
    try:
        with open('timetable_pdf.json', 'r', encoding='utf-8') as f:
            pdf_pages = json.load(f)
            for page in pdf_pages:
                db.add(Timetable(
                    sheet_name=f"PDF_Page_{page['page_number']}", 
                    row_data={"text": page['text']}
                ))
    except Exception as e:
        print("Error loading PDF timetable:", e)
            
    db.commit()
    db.close()
    print("Database seeded successfully. Data from timetable and faculty seating are now in nexus.db")

if __name__ == "__main__":
    seed()
