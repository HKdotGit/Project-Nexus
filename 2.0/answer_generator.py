"""
answer_generator.py
===================
Uses Google Gemini to generate answers natively.
Now heading-aware:
  - Prompt tells the model which section the answer comes from
  - Model uses heading as context to give more precise answers
"""

import os
import re
from dotenv import load_dotenv
from google import genai

class AnswerGenerator:

    def __init__(self, model_name: str = "gemini-3-flash-preview", **kwargs):
        load_dotenv()
        self.model_name = model_name
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyDKYtgw2Xvf2ix-aeVwrvXuXGLYO1jMPYE")
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    # -- PROMPT --
    def build_prompt(self, question: str, chunks: list, history: list = None) -> str:
        """
        Build a heading-aware prompt with optional conversation history.
        """
        sorted_chunks = sorted(
            chunks, key=lambda c: c.get("score", 0), reverse=True
        )

        # Filter by score confidence (re-ranked scores)
        # Anything below 0.35 is likely irrelevant after our boosting
        CONFIDENCE_THRESHOLD = 0.15
        filtered_chunks = [c for c in sorted_chunks if c.get("score", 0) >= CONFIDENCE_THRESHOLD]
        
        if not filtered_chunks and sorted_chunks:
            # If nothing is above threshold but we have candidates, 
            # we might be looking at a very specific name match that didn't reach threshold
            # or the model should just be told we aren't sure.
            pass

        # Group chunks by heading
        sections = {}
        seen_texts = set()
        unique_count = 0
        
        for chunk in filtered_chunks:
            text  = chunk["text"].strip()
            if not text or text in seen_texts:
                continue
                
            seen_texts.add(text)
            unique_count += 1
            if unique_count > 10:
                break
                
            heading = chunk.get("heading") or chunk.get("h1") or "General"
            if heading not in sections:
                sections[heading] = []
            sections[heading].append(text)

        # Build structured context block
        context_parts = []
        for heading, texts in sections.items():
            source = "Unknown Source"
            for c in sorted_chunks:
                h = c.get("heading") or c.get("h1") or "General"
                if h == heading:
                    source = c.get("source", "Unknown Source")
                    break
            
            context_parts.append(f"[Section: {heading}] [Source: {source}]")
            context_parts.append(" ".join(texts))
            context_parts.append("")

        context = "\n".join(context_parts)

        # Format history
        history_str = ""
        if history:
            history_str = "\n".join([f"{m['role'].capitalize()}: {m['content']}" for m in history[-6:]]) # Last 6 messages

        prompt = f"""You are a helpful college AI assistant named Nexus.

INSTRUCTIONS:
1. Be conversational and natural. Avoid repeating your introduction.
2. Use the provided context AND conversation history.
3. If the answer involves a specific faculty member,  provide their seating/office details precisely as shown in the context.
4. If the student asks for a form (e.g. Leave Application), state the exact filename (e.g. Student Leave Application.pdf) so the system can provide a download link.
5. If you are unsure or the context is sparse, admit it and suggest the college office.
6. For timetables, look for Markdown tables in the context and explain the schedule clearly.

Conversation History:
{history_str}

Context from Knowledge Base:
{context}

Current Question: {question}

Answer:"""

        return prompt

    # -- GENERATION --
    def generate(self, question: str, chunks: list, history: list = None) -> dict:
        # 1. ALWAYS check for greetings first, before checking chunks or scores
        greeting_keywords = ["hello", "hi", "hey", "who are you", "how are you"]
        is_greeting = any(k == question.lower().strip().strip('?!.') for k in greeting_keywords) or \
                     (len(question.split()) <= 3 and any(k in question.lower() for k in greeting_keywords))
        
        if is_greeting:
            prompt = f"You are Nexus, a college AI. Reply to this greeting naturally and briefly: {question}"
            try:
                response = self.client.models.generate_content(model=self.model_name, contents=prompt)
                return {"answer": response.text.strip(), "sources": [], "headings": [], "prompt": prompt}
            except:
                return {"answer": "Hello! I am Nexus, your college assistant. How can I help you today?", "sources": [], "headings": [], "prompt": ""}

        if not chunks:
            return {
                "answer" : "I don't have that information in my database. Please contact the college office directly.",
                "sources": [],
                "prompt" : "",
            }
        
        # 2. Check confidence for non-greeting queries
        top_score = chunks[0].get("score", 0)
        if top_score < 0.15:
             return {
                "answer" : "I found some information that might be related, but I'm not confident enough to give you a specific answer about that. Please contact the college office for the most accurate info.",
                "sources": [chunks[0].get("source", "Unknown")],
                "prompt" : "",
            }

        prompt  = self.build_prompt(question, chunks, history=history)
        sources = list({c.get("source", "unknown") for c in chunks})

        # Collect section headings used in the answer
        headings = list({
            c.get("heading") or c.get("h1", "")
            for c in chunks
            if c.get("heading") or c.get("h1")
        })

        import time
        for attempt in range(3):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt
                )
                answer = response.text.strip()
                if answer.lower().startswith("answer:"):
                    answer = answer[7:].strip()
                return {
                    "answer"  : answer,
                    "sources" : sources,
                    "headings": headings,
                    "prompt"  : prompt,
                }
            except Exception as e:
                print(f"  [WARN] Attempt {attempt+1} failed: {e}")
                if "429" in str(e):
                    time.sleep(5)
                    continue
                break

        return {
            "answer"  : self._fallback_extract(chunks),
            "sources" : sources,
            "headings": headings,
            "prompt"  : prompt,
        }

    # -- FALLBACK --
    def _fallback_extract(self, chunks: list) -> str:
        best    = sorted(chunks, key=lambda c: c.get("score", 0), reverse=True)[0]
        heading = best.get("heading", "")
        text    = best["text"].strip()
        words   = text.split()
        if len(words) > 150:
            text = " ".join(words[:150]) + "..."
        prefix = f"[AI SERVICE UNAVAILABLE - Showing Doc Extract]\n\n[{heading}]\n\n" if heading else "[AI SERVICE UNAVAILABLE]\n\n"
        return f"{prefix}{text}"

    # -- DEBUG --
    def format_sources(self, chunks: list) -> str:
        lines = []
        for i, chunk in enumerate(chunks, 1):
            score   = chunk.get("score", 0)
            heading = chunk.get("heading", "no heading")
            preview = chunk["text"][:60].replace("\n", " ")
            lines.append(
                f"  [{i}] {heading}  (score: {score:.3f})\n"
                f"       \"{preview}...\""
            )
        return "\n".join(lines)
