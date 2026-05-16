import os
import shutil
import json
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Optional
from sqlalchemy.orm import Session

from google import genai
from dotenv import load_dotenv

from assistant import CollegeAssistant
from database import engine, get_db
from models import User, ChatSession, ChatMessage
from auth import (
    hash_password, verify_password,
    create_access_token,
    get_current_user, require_user
)
import models

# ── Bootstrap ─────────────────────────────────────────────────────────────────
load_dotenv()
models.Base.metadata.create_all(bind=engine)   # Creates nexus.db + tables on first run

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyDKYtgw2Xvf2ix-aeVwrvXuXGLYO1jMPYE")
client = genai.Client(api_key=GEMINI_API_KEY)

assistant = CollegeAssistant()
print("[START] Setting up global Assistant...")
assistant.setup()

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Nexus RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static file mounts
Path("static/avatars").mkdir(parents=True, exist_ok=True)
Path("Database").mkdir(parents=True, exist_ok=True)
app.mount("/static",         StaticFiles(directory="static"),   name="static")
app.mount("/files/database", StaticFiles(directory="Database"), name="database")
app.mount("/files/root",     StaticFiles(directory="."),        name="root")


# ── Pages ─────────────────────────────────────────────────────────────────────
@app.get("/")
async def serve_ui():
    return FileResponse("templates/index.html")

@app.get("/login")
async def serve_login():
    return FileResponse("templates/login.html")


# ── Auth endpoints ────────────────────────────────────────────────────────────
@app.post("/auth/register")
async def register(
    username: str = Form(...),
    email:    str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return {
        "token": token,
        "user": {
            "id":       user.id,
            "username": user.username,
            "email":    user.email,
            "avatar":   user.avatar_path
        }
    }


@app.post("/auth/login")
async def login(
    email:    str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user.id)
    return {
        "token": token,
        "user": {
            "id":       user.id,
            "username": user.username,
            "email":    user.email,
            "avatar":   user.avatar_path
        }
    }


@app.get("/auth/me")
async def me(user: User = Depends(require_user)):
    return {
        "id":       user.id,
        "username": user.username,
        "email":    user.email,
        "avatar":   user.avatar_path
    }


# ── Avatar upload ─────────────────────────────────────────────────────────────
@app.post("/user/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: User       = Depends(require_user),
    db:   Session    = Depends(get_db)
):
    ext = Path(file.filename).suffix.lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
        raise HTTPException(status_code=400, detail="Only image files allowed")

    avatar_filename = f"{user.id}{ext}"
    save_path = Path("static/avatars") / avatar_filename

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    user.avatar_path = f"/static/avatars/{avatar_filename}"
    db.commit()
    return {"avatar": user.avatar_path}


# ── Chat history endpoints ────────────────────────────────────────────────────
@app.get("/history")
async def list_sessions(
    user: User    = Depends(require_user),
    db:   Session = Depends(get_db)
):
    """Returns all chat sessions for the logged-in user, newest first."""
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user.id)
        .order_by(ChatSession.created_at.desc())
        .all()
    )
    return [
        {
            "id":         s.id,
            "tab_name":   s.tab_name,
            "title":      s.title or "New Chat",
            "created_at": s.created_at.isoformat()
        }
        for s in sessions
    ]


@app.get("/history/{session_id}")
async def get_session(
    session_id: int,
    user: User    = Depends(require_user),
    db:   Session = Depends(get_db)
):
    """Returns all messages for a specific session."""
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "id":       session.id,
        "tab_name": session.tab_name,
        "title":    session.title or "New Chat",
        "messages": [
            {"role": m.role, "content": m.content, "timestamp": m.timestamp.isoformat()}
            for m in session.messages
        ]
    }


@app.post("/history/session")
async def create_session(
    tab_name: str = Form(default="FAQs"),
    user: User    = Depends(require_user),
    db:   Session = Depends(get_db)
):
    """Creates a new empty chat session for the user."""
    session = ChatSession(user_id=user.id, tab_name=tab_name)
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"session_id": session.id}


@app.delete("/history")
async def clear_history(
    user: User    = Depends(require_user),
    db:   Session = Depends(get_db)
):
    """Deletes all chat sessions for the logged-in user."""
    sessions = db.query(ChatSession).filter(ChatSession.user_id == user.id).all()
    session_ids = [s.id for s in sessions]
    if session_ids:
        db.query(ChatMessage).filter(ChatMessage.session_id.in_(session_ids)).delete(synchronize_session=False)
        db.query(ChatSession).filter(ChatSession.user_id == user.id).delete(synchronize_session=False)
        db.commit()
    return {"ok": True}


@app.post("/history/{session_id}/message")
async def save_message(
    session_id: int,
    role:    str = Form(...),
    content: str = Form(...),
    user: User    = Depends(require_user),
    db:   Session = Depends(get_db)
):
    """Saves a single message to a session. Also sets session title from first user message."""
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Auto-title from first user message
    if role == "user" and not session.title:
        session.title = content[:80]

    msg = ChatMessage(session_id=session_id, role=role, content=content)
    db.add(msg)
    db.commit()
    return {"ok": True}


# ── Chat endpoint (enhanced with optional auth + history saving) ───────────────
@app.post("/chat")
def chat_endpoint(
    query:      str           = Form(...),
    history:    Optional[str] = Form(None),
    session_id: Optional[int] = Form(None),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Receives chat question, returns answer + sources. Saves to DB if authenticated."""
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    history_list = []
    if history:
        try:
            history_list = json.loads(history)
        except Exception as e:
            print(f"[WARN] Failed to parse history: {e}")

    result = assistant.ask(query, history=history_list, user=current_user)

    sources_str = ""
    if result.get("chunks"):
        first_chunk = result["chunks"][0]
        source_name = first_chunk.get("source", "Unknown")
        heading     = first_chunk.get("heading")
        sources_str = f"Found in: {source_name}" + (f" > {heading}" if heading else "")

    # Save messages to DB if authenticated and session_id given
    if current_user and session_id:
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id
        ).first()
        if session:
            if not session.title:
                try:
                    title_res = assistant.client.models.generate_content(
                        model=assistant.model_name,
                        contents=f"Generate a very short 3-5 word title for this question. No quotes, no punctuation. Question: {query}"
                    )
                    session.title = title_res.text.strip()[:80]
                except:
                    words = query.strip().split()
                    session.title = " ".join(words[:5]) + ("..." if len(words) > 5 else "")
            db.add(ChatMessage(session_id=session_id, role="user",      content=query))
            db.add(ChatMessage(session_id=session_id, role="assistant", content=result["answer"]))
            db.commit()

    return {
        "answer":        result["answer"],
        "source_heading": sources_str
    }


# ── File upload endpoint ──────────────────────────────────────────────────────
import time

@app.post("/upload")
def upload_file(
    file: UploadFile = File(...),
    user: User = Depends(require_user)
):
    ext = Path(file.filename).suffix.lower()
    save_path = Path(file.filename)

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    if ext in [".pdf", ".png", ".jpg", ".jpeg", ".webp"]:
        print(f"[OCR] Processing document upload: {save_path}")
        try:
            image_file = client.files.upload(file=str(save_path))
            
            while image_file.state.name == "PROCESSING":
                print(f"[OCR] Waiting for Gemini to process {save_path.name}...")
                time.sleep(2)
                image_file = client.files.get(name=image_file.name)
                
            if image_file.state.name == "FAILED":
                raise Exception("Document processing failed on Gemini server.")

            response   = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[image_file, "Extract all text, schedules, timetables, and structured data perfectly from this document. Output only the text representation."],
            )
            extracted_text = response.text

            txt_filename = f"{save_path.stem}_ocr.txt"
            with open(txt_filename, "w", encoding="utf-8") as f:
                f.write(f"CONTENT FROM {save_path.name}:\n\n{extracted_text}")

            print(f"[OCR] Extracted document text to {txt_filename}. Adding to localized memory...")
            assistant.processor.add_new_file(txt_filename, user_id=user.id)
            return {"status": "success", "message": f"Successfully read {file.filename} and added to memory!"}
        except Exception as e:
            print(f"[OCR] Error processing {file.filename}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")

    else:
        assistant.processor.add_new_file(str(save_path), user_id=user.id)
        return {"status": "success", "message": f"Successfully learned from {file.filename}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=False)
