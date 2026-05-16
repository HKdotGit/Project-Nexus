# College RAG Assistant
A fully local, no-API question answering system for college data.
Uses Sentence Transformers for semantic retrieval + FLAN-T5 for natural language generation.

---

## File Structure
```
college_rag/
├── document_processor.py   # PDF/text loading, chunking, embedding, FAISS index
├── answer_generator.py     # FLAN-T5 prompt building and answer generation
├── assistant.py            # Ties everything together + interactive chat loop
├── requirements.txt
└── index/                  # Auto-created after first run (your saved index)
```

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirement.txt
```

### 2. Add your documents
Edit the `FILES` list at the top of `assistant.py`:
```python
FILES = [
    "college_data.pdf",
    "fees_structure.txt",
    "hostel_info.pdf",
]
```

### 3. Run
```bash
python assistant.py
```

**First run** — downloads FLAN-T5 (~250MB) and indexes your documents. Takes a few minutes.
**Every run after** — loads from cache instantly. No re-indexing.

---

## Example Session
```
You: What are the admission requirements?
Assistant: To apply for admission, students need to submit their 10th and 12th 
           marksheets, a transfer certificate, and two passport-size photographs.

You: What is the hostel fee?
Assistant: The hostel fee for a single room is ₹45,000 per year, which includes 
           accommodation and meals.
```

---

## Commands During Chat
| Command   | Effect                              |
|-----------|-------------------------------------|
| `sources` | Toggle showing which file answered  |
| `debug`   | Toggle showing raw retrieved chunks |
| `quit`    | Exit                                |

---

## Re-indexing
If you add or change documents, delete the index folder and re-run:
```bash
rm -rf index/
python assistant.py
```

---

## Model Size Options
Edit `FLAN_MODEL` in `assistant.py`:
| Model                    | Size   | Speed  | Quality  |
|--------------------------|--------|--------|----------|
| `google/flan-t5-small`   | ~80MB  | Fast   | Basic    |
| `google/flan-t5-base`    | ~250MB | Medium | Good ✅  |
| `google/flan-t5-large`   | ~800MB | Slow   | Best     |
