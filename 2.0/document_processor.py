import re
import json
import pickle
import numpy as np
from pathlib import Path


class DocumentProcessor:

    def __init__(
        self,
        chunk_size: int       = 120,
        chunk_overlap: int    = 20,
        embed_model_name: str = "all-MiniLM-L6-v2",
        index_dir: str        = "index",
    ):
        self.chunk_size       = chunk_size
        self.chunk_overlap    = chunk_overlap
        self.embed_model_name = embed_model_name
        self.index_dir        = Path(index_dir)

        self.chunks     = []
        self.embeddings = None
        self.index      = None
        self._model     = None

    # -- lazy model loader --
    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            print(f"  [MODEL] Initializing AI model: '{self.embed_model_name}'...")
            print("  [MODEL] This may take a moment depending on your CPU/RAM...")
            self._model = SentenceTransformer(self.embed_model_name)
            print("  [MODEL] Initialization complete.")
        return self._model

    # -- DOCUMENT LOADING --
    def load_documents(self, paths: list) -> list:
        documents = []
        for path in paths:
            path = Path(path)
            if not path.exists():
                print(f"  [WARN] File not found: {path}")
                continue
            
            # Skip empty files
            if path.stat().st_size == 0:
                print(f"  [SKIP] Empty file: {path.name}")
                continue

            try:
                if path.suffix.lower() == ".pdf":
                    text = self._load_pdf(path)
                elif path.suffix.lower() == ".xlsx":
                    text = self._load_xlsx(path)
                elif path.suffix.lower() == ".docx":
                    text = self._load_docx(path)
                elif path.suffix.lower() in (".txt", ".md"):
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                else:
                    print(f"  [WARN] Unsupported format: {path}")
                    continue
            except Exception as e:
                print(f"  [ERROR] Could not load {path.name}: {e}")
                continue
            if text.strip():
                # Add folder name to help retrieval (e.g. "Important Forms")
                folder_name = path.parent.name
                documents.append((path.name, folder_name, text))
                print(f"  [OK] Loaded: {path.name}  ({len(text.split())} words)")
        return documents

    def _load_pdf(self, path: Path) -> str:
        try:
            import PyPDF2
        except ImportError:
            raise ImportError("Run: pip install PyPDF2")
        pages = []
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            print(f"     {len(reader.pages)} pages found")
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    pages.append(t)
        return "\n".join(pages)

    def _load_xlsx(self, path: Path) -> str:
        try:
            import openpyxl
        except ImportError:
            print("  [ERROR] openpyxl not installed. Skipping Excel file.")
            return ""
        
        try:
            # Use read_only=True for speed and stability
            wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
            text_parts = []
            for sheet in wb.worksheets:
                text_parts.append(f"Sheet: {sheet.title}")
                
                rows = sheet.iter_rows(values_only=True)
                
                # Use the first non-empty row as headers
                headers = []
                for row in rows:
                    row_data = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
                    if row_data:
                        headers = [str(cell).strip() for cell in row] # Keep all cells for indexing
                        break
                
                if not headers:
                    continue

                for row in rows:
                    # Filter out purely empty rows
                    row_cells = [str(cell).strip() for cell in row]
                    if any(row_cells) and not all(c == "None" for c in row_cells or not c):
                        items = []
                        for i, cell in enumerate(row_cells):
                            if cell and cell != "None":
                                label = headers[i] if (i < len(headers) and headers[i] and headers[i] != "None") else f"Col{i+1}"
                                items.append(f"{label}: {cell}")
                        
                        if items:
                            # Prepend helpful context to each row so it's searchable as a unit
                            row_text = f"Data Row in {sheet.title}: " + " | ".join(items)
                            text_parts.append(row_text)
            
            return "\n".join(text_parts)
        except Exception as e:
            print(f"  [ERROR] Failed to load Excel {path.name}: {e}")
            import traceback
            traceback.print_exc()
            return ""

    def _load_docx(self, path: Path) -> str:
        try:
            import docx
        except ImportError:
            print("  [ERROR] python-docx not installed. Skipping Word file.")
            return ""
        
        try:
            doc = docx.Document(path)
            text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
            return text
        except Exception as e:
            print(f"  [ERROR] Failed to load Word {path.name}: {e}")
            return ""

    # -- TEXT CLEANING --
    def clean_text(self, text: str) -> str:
        text = re.sub(r"[^\x20-\x7E\n]", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()

    # -- HEADING DETECTION --
    def _detect_heading(self, line: str) -> tuple:
        """
        Returns (level, heading_text) or (0, None) if not a heading.

        Level 1: "1. Introduction"  or  "CHAPTER 1"  or  "ATTENDANCE"
        Level 2: "1.1 Overview"     or  "1.1. Overview"
        Level 3: "1.1.1 Details"    or  "1.1.1. Details"
        """
        line = line.strip()
        if not line:
            return 0, None

        # Level 3: X.X.X heading
        if re.match(r"^\d+\.\d+\.\d+[\.\s]", line):
            return 3, line

        # Level 2: X.X heading
        if re.match(r"^\d+\.\d+[\.\s]", line):
            return 2, line

        # Level 1: X. heading (single number)
        if re.match(r"^\d+[\.\s]\s*[A-Z]", line):
            return 1, line

        # ALL CAPS heading (like "ATTENDANCE POLICY")
        if re.match(r"^[A-Z][A-Z\s]{4,}$", line) and len(line) < 80:
            return 1, line

        # Bold-style heading detection (Title Case, short line)
        words = line.split()
        if (len(words) <= 8
                and line[0].isupper()
                and not line.endswith(".")
                and len(line) < 60):
            # Check if most words are capitalized
            cap_words = sum(1 for w in words if w[0].isupper())
            if cap_words / len(words) >= 0.6:
                return 2, line

        return 0, None

    # -- HIERARCHICAL PARSING --
    def _parse_sections(self, text: str, source_name: str) -> list:
        """
        Parse the document into a hierarchy:
            Section (h1)
              |-- Subsection (h2)
                    |-- Sub-subsection (h3)
                          |-- content chunks

        Each chunk carries its full heading breadcrumb so retrieval
        can match on BOTH heading context and content.
        """
        lines    = text.split("\n")
        sections = []   # list of dicts

        current_h1 = ""
        current_h2 = ""
        current_h3 = ""
        current_folder = source_name[1] if isinstance(source_name, tuple) else ""
        source_name = source_name[0] if isinstance(source_name, tuple) else source_name
        buffer     = []

        def flush_buffer(h1, h2, h3, buf):
            """Save buffered lines as one or more chunks under current headings."""
            if not buf:
                return
            content = "\n".join(buf).strip()
            if len(content.split()) < 5:
                return

            # Build heading breadcrumb
            breadcrumb_parts = [p for p in [h1, h2, h3] if p]
            breadcrumb       = " > ".join(breadcrumb_parts)

            # Split content into sentence-aware sub-chunks
            sub_chunks = self._split_into_chunks(content)
            for sc in sub_chunks:
                # If the folder name is "Important Forms", prefix it to embed_text
                # so specific queries for "forms" or "application" trigger it.
                context_prefix = f"Category: {current_folder} > " if current_folder and current_folder != "." else ""
                
                embed_text = f"{context_prefix}{breadcrumb}\n{sc}" if breadcrumb else f"{context_prefix}{sc}"

                sections.append({
                    "heading"    : breadcrumb,
                    "folder"     : current_folder,
                    "h1"         : h1,
                    "h2"         : h2,
                    "h3"         : h3,
                    "text"       : sc,
                    "source"     : source_name,
                    "embed_text" : embed_text,
                })

        for line in lines:
            line     = line.strip()
            level, heading = self._detect_heading(line)

            if level == 1:
                flush_buffer(current_h1, current_h2, current_h3, buffer)
                current_h1 = heading
                current_h2 = ""
                current_h3 = ""
                buffer     = []

            elif level == 2:
                flush_buffer(current_h1, current_h2, current_h3, buffer)
                current_h2 = heading
                current_h3 = ""
                buffer     = []

            elif level == 3:
                flush_buffer(current_h1, current_h2, current_h3, buffer)
                current_h3 = heading
                buffer     = []

            else:
                if line:
                    buffer.append(line)

        # Flush anything remaining
        flush_buffer(current_h1, current_h2, current_h3, buffer)

        return sections

    # -- SENTENCE-AWARE CHUNKING --
    def _split_into_chunks(self, text: str) -> list:
        """Split a block of text into small focused chunks."""
        # Split on sentence boundaries
        sentences = re.split(r"(?<=[.!?])\s+", text)
        sentences = [s.strip() for s in sentences if len(s.split()) >= 3]

        chunks      = []
        current     = []
        current_len = 0

        for sent in sentences:
            wc = len(sent.split())
            if current_len + wc > self.chunk_size and current:
                chunks.append("\n".join(current))

                # overlap
                overlap, ol = [], 0
                for s in reversed(current):
                    w = len(s.split())
                    if ol + w <= self.chunk_overlap:
                        overlap.insert(0, s)
                        ol += w
                    else:
                        break
                current, current_len = overlap, ol

            current.append(sent)
            current_len += wc

        if current:
            chunks.append("\n".join(current))

        return [c for c in chunks if len(c.split()) >= 5]

    # -- EMBEDDING --
    def embed_chunks(self, chunks: list) -> np.ndarray:
        """
        Embed using embed_text (heading + content) so the vector
        captures BOTH the section context and the actual content.
        """
        texts = [c["embed_text"] for c in chunks]
        print(f"  Encoding {len(texts)} chunks...", end=" ", flush=True)
        embeddings = self.model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        print("[OK]")
        return embeddings.astype(np.float32)

    # -- FAISS INDEX --
    def build_index(self, embeddings: np.ndarray):
        try:
            import faiss
        except ImportError:
            raise ImportError("Run: pip install faiss-cpu")
        dim   = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)
        print(f"  FAISS index: {index.ntotal} vectors  dim={dim}")
        return index

    # -- MAIN BUILD --
    def build(self, file_paths: list):
        print("\n[FILES] Loading documents...")
        documents = self.load_documents(file_paths)
        if not documents:
            raise ValueError("No valid documents found.")

        print("\n[CHUNKS] Parsing sections and chunking...")
        all_chunks = []
        for name, folder, text in documents:
            cleaned = self.clean_text(text)
            chunks  = self._parse_sections(cleaned, source_name=(name, folder))
            all_chunks.extend(chunks)

            # Show heading structure found
            headings = list({c["h1"] for c in chunks if c["h1"]})
            print(f"\n  {name}  ->  {len(chunks)} chunks")
            print(f"  Sections detected:")
            for h in sorted(headings)[:15]:
                print(f"    * {h}")
            if len(headings) > 15:
                print(f"    ... and {len(headings)-15} more")

        print(f"\n  Total chunks: {len(all_chunks)}")

        print("\n[EMBED] Embedding chunks (heading + content)...")
        embeddings = self.embed_chunks(all_chunks)

        print("\n[INDEX] Building FAISS index...")
        self.index      = self.build_index(embeddings)
        self.chunks     = all_chunks
        self.embeddings = embeddings

        print("\n[OK] Knowledge base ready.\n")

    # -- RETRIEVAL --
    def retrieve(self, query: str, top_k: int = 5, user_id: int = None) -> list:
        """
        Retrieve top_k chunks.
        Also groups results by heading so the answer generator
        gets context from the RIGHT section first.
        """
        if self.index is None:
            raise RuntimeError("Index not built. Call build() or load() first.")

        # Embed query
        query_vec = self.model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True,
        ).astype(np.float32)

        # Search ALL chunks so we can accurately re-rank user documents
        k = len(self.chunks)
        scores, indices = self.index.search(query_vec, k)

        candidates = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            chunk          = dict(self.chunks[idx])
            
            chunk_user = chunk.get("user_id")
            if chunk_user is not None and chunk_user != user_id:
                continue

            chunk["score"] = float(score)
            chunk["_idx"] = idx
            candidates.append(chunk)

        # Re-rank: boost chunks whose heading OR text matches query keywords exactly
        # This is CRITICAL for names like "Bhavna" or "Mishra"
        query_words = set(re.findall(r"\b\w{3,}\b", query.lower()))
        for chunk in candidates:
            chunk_text_lower = chunk.get("text", "").lower() + " " + chunk.get("heading", "").lower()
            
            # Count exact word hits
            hits = 0
            for word in query_words:
                if word in chunk_text_lower:
                    hits += 1
            
            # Significant boost for hits
            if hits > 0:
                chunk["score"] += (hits * 0.15)
            
            # Extra boost for "Recent" or "Data Row" items
            if "recently_uploaded" in chunk.get("source", "").lower() or "_ocr" in chunk.get("source", "").lower():
                chunk["score"] += 0.25
            if "Data Row" in chunk.get("text", ""):
                chunk["score"] += 0.20 # Increased boost for structured data
            
            # Seating/Office specific boost
            seating_keywords = {"sit", "seating", "office", "room", "cabin", "cubicle", "location"}
            if any(k in query.lower() for k in seating_keywords):
                text_lower = chunk.get("text", "").lower()
                if any(k in text_lower for k in ["cabin", "cubicle", "room", "floor", "seating"]):
                    chunk["score"] += 0.15

        # Sort by boosted score
        candidates.sort(key=lambda x: x["score"], reverse=True)
        
        # Deduplicate to ensure diverse chunks and return top_k
        unique_candidates = []
        seen_texts = set()
        for chunk in candidates:
            text = chunk.get("text", "").strip()
            if text not in seen_texts:
                seen_texts.add(text)
                unique_candidates.append(chunk)
            if len(unique_candidates) >= top_k:
                break
                
        return unique_candidates

    # -- DYNAMIC ADDITION --
    def add_new_file(self, file_path: str, user_id: int = None):
        """Parse, chunk, embed, and append a new file into the existing FAISS index."""
        if self.index is None:
            if not self.load():
                print("No existing knowledge base found. Creating a new one.")
                self.build([file_path])
                self.save()
                return

        print(f"\n[INFO] Loading new document: {file_path}")
        documents = self.load_documents([file_path])
        if not documents:
            print("[ERROR] No valid text found in file.")
            return

        all_chunks = []
        for name, folder, text in documents:
            cleaned = self.clean_text(text)
            chunks  = self._parse_sections(cleaned, source_name=(name, folder))
            for chunk in chunks:
                chunk["user_id"] = user_id
            all_chunks.extend(chunks)

        if not all_chunks:
            print("[ERROR] No extractable chunks found.")
            return

        print(f"[INFO] Embedding {len(all_chunks)} new chunks...")
        new_embeddings = self.embed_chunks(all_chunks)

        print("\n[INFO] Merging into FAISS index...")
        self.index.add(new_embeddings)
        self.chunks.extend(all_chunks)
        
        if self.embeddings is not None:
            self.embeddings = np.vstack((self.embeddings, new_embeddings))

        self.save()
        print(f"[OK] Document successfully added to the knowledge base!\n")

    # -- SAVE / LOAD --
    def save(self):
        try:
            import faiss
        except ImportError:
            raise ImportError("Run: pip install faiss-cpu")

        self.index_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(self.index_dir / "vectors.index"))

        with open(self.index_dir / "chunks.pkl", "wb") as f:
            pickle.dump(self.chunks, f)

        meta = {
            "chunk_size"      : self.chunk_size,
            "chunk_overlap"   : self.chunk_overlap,
            "embed_model_name": self.embed_model_name,
            "total_chunks"    : len(self.chunks),
        }
        with open(self.index_dir / "meta.json", "w") as f:
            json.dump(meta, f, indent=2)

        print(f"[SAVED] Saved index to '{self.index_dir}/'")

    def load(self) -> bool:
        try:
            import faiss
        except ImportError:
            raise ImportError("Run: pip install faiss-cpu")

        index_path  = self.index_dir / "vectors.index"
        chunks_path = self.index_dir / "chunks.pkl"

        if not index_path.exists() or not chunks_path.exists():
            return False

        self.index = faiss.read_index(str(index_path))
        with open(chunks_path, "rb") as f:
            self.chunks = pickle.load(f)

        print(f"[OK] Loaded index from '{self.index_dir}/'  "
              f"({len(self.chunks)} chunks)")
        return True
