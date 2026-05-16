from pathlib import Path
from document_processor import DocumentProcessor
from answer_generator import AnswerGenerator

FILES = ["SRB 2025.pdf"]
# Ensure indexing directory is relative to this file's location
BASE_DIR = Path(__file__).parent
INDEX_DIR = str(BASE_DIR / "index")

class CollegeAssistant:
    """
    Combines DocumentProcessor (retrieval) and AnswerGenerator (generation)
    into a single cohesive system ready for API consumption.
    """
    def __init__(self, files: list = FILES, index_dir: str = INDEX_DIR, top_k: int = 5):
        self.files = files
        self.top_k = top_k
        self.processor = DocumentProcessor(index_dir=index_dir)
        self.generator = AnswerGenerator()

    def setup(self):
        """
        Loads the knowledge base from disk if it exists.
        Otherwise builds it from the provided files and saves it.
        """
        print("[INFO] Nexus College Assistant Booting Up...")
        
        # Check if we need to build or reload
        loaded = self.processor.load()
        if not loaded:
            # Recursively find all documents in the Database folder
            db_path = BASE_DIR / "Database"
            if not db_path.exists():
                print(f"[WARN] Database folder not found at {db_path}. Using base directory.")
                db_path = BASE_DIR

            print(f"[INFO] Scanning for latest documents in: {db_path}")
            all_files = list(db_path.rglob("*"))
            
            # Filter for supported extensions
            supported_exts = {".pdf", ".docx", ".xlsx", ".txt", ".md"}
            valid_files = [f for f in all_files if f.suffix.lower() in supported_exts]

            # SMART FILTER: Prioritize latest year (2025/2026) and skip Study Materials
            filtered_files = []
            for f in valid_files:
                filename = f.name.lower()
                rel_path = str(f.relative_to(db_path)).lower()
                
                # USER DIRECTIVE: Skip Study Materials and Textbooks
                # We skip any path that contains "study material", "textbook", or "handout" 
                # (unless it's the "STUDENT HANDOUT" root folder)
                if "study material" in rel_path or "textbook" in rel_path:
                    continue
                
                # Exclude older years (2016 to 2024)
                if any(str(year) in filename for year in range(2016, 2025)):
                    # Special Case: Allow if it also mentions 2025 or 2026 (e.g. 2024-25)
                    if "2025" in filename or "2026" in filename:
                        filtered_files.append(str(f))
                    else:
                        continue
                else:
                    filtered_files.append(str(f))

            if not filtered_files:
                raise ValueError("No valid indexing files found in Database (after filtering).")
            
            print(f"[INFO] Found {len(filtered_files)} relevant documents. Starting indexing...")
            print("[NOTE] This will download AI models and re-index EVERYTHING. Please wait...")
            
            self.processor.build(filtered_files)
            self.processor.save()

        print("[INFO] Loading local Embedding Model (SentenceTransformer)...")
        _ = self.processor.model  # Trigger lazy load
        print("[INFO] Embedding Model loaded successfully.")

        print("[INFO] Connecting to Cloud Gemini API...")
        # Verification of Gemini connection is implicit in AnswerGenerator init
        
        print("\n" + "="*50)
        print("[READY] NEXUS AI IS FULLY OPERATIONAL")
        print("[READY] You can now ask questions and get full AI answers.")
        print("="*50 + "\n")

    def ask(self, question: str, history: list = None, user=None) -> dict:
        if not question.strip():
            return {"question": question, "answer": "Please ask a question.", "sources": [], "chunks": []}

        question_lower = question.lower()
        import json
        import re
        from pathlib import Path
        
        user_id = user.id if user else None

        # Feature 1: Faculty Seating
        seating_keywords = ["seating", "sit", "cabin", "office", "faculty"]
        if any(w in question_lower for w in seating_keywords) and ("faculty" in question_lower or "sit" in question_lower or "seating" in question_lower or "where" in question_lower):
            try:
                with open(BASE_DIR / "data" / "faculty_sitting.json", "r", encoding="utf-8") as f:
                    data = f.read()
                chunks = [{"text": data, "heading": "Faculty Seating Info", "source": "faculty_sitting.json", "score": 1.0, "h1": ""}]
            except Exception as e:
                chunks = self.processor.retrieve(question, top_k=self.top_k, user_id=user_id)
                
        # Feature 2: BTI Div C Timetable
        elif re.search(r'\bbti\b', question_lower) and re.search(r'\bc\b', question_lower) and ("timetable" in question_lower or "schedule" in question_lower):
            try:
                with open(BASE_DIR / "data" / "timetable_pdf.json", "r", encoding="utf-8") as f:
                    data = f.read()
                chunks = [{"text": data, "heading": "BTI Div C Timetable", "source": "timetable_pdf.json", "score": 1.0, "h1": ""}]
            except Exception:
                chunks = self.processor.retrieve(question, top_k=self.top_k, user_id=user_id)

        # Feature 3: Artika Singh Timetable
        elif "artika singh" in question_lower and ("timetable" in question_lower or "schedule" in question_lower):
            try:
                with open(BASE_DIR / "data" / "timetable_xlsx.json", "r", encoding="utf-8") as f:
                    data = f.read()
                chunks = [{"text": data, "heading": "Artika Singh Timetable", "source": "timetable_xlsx.json", "score": 1.0, "h1": ""}]
            except Exception:
                chunks = self.processor.retrieve(question, top_k=self.top_k, user_id=user_id)

        # Default fallback (including uploaded timetables)
        else:
            chunks = self.processor.retrieve(question, top_k=self.top_k, user_id=user_id)
            
            # Custom strict timetable prompt
            if "timetable" in question_lower or "schedule" in question_lower:
                top_score = chunks[0].get("score", 0) if chunks else 0
                # Reduce threshold drastically so uploaded docs easily pass, but missing ones get the upload prompt
                if top_score < 0.15:
                    return {
                        "question": question,
                        "answer": "I don't have enough context to answer this. Please upload the timetable document, and I will be able to read it and answer your questions.",
                        "sources": [],
                        "chunks": []
                    }

        # Step 2: generate answer
        result = self.generator.generate(question, chunks, history=history)

        return {
            "question": question,
            "answer": result["answer"],
            "sources": result["sources"],
            "chunks": chunks,
        }
