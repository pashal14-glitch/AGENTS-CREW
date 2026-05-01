"""
indexer.py
----------
טוען קבצי knowledge ל-ChromaDB עם תיוג מקור לכל קטע.

סדר עדיפויות:
  takshir  → takshir.md
  takam    → takam/*.docx
  md       → hesberbeclick_bot_prompt_v2.md

ecology.json לא נכנס לאינדקס — נשלף ישירות ב-agent.py

הרצה: python indexer.py
"""

import os
import hashlib
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR", "./knowledge"))
CHROMA_DIR    = Path(os.getenv("CHROMA_DIR",    "./chroma_db"))
PROMPT_FILE   = os.getenv("PROMPT_FILE", "hesberbeclick_bot_prompt_v2.md")


def read_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_docx(path: Path) -> str:
    try:
        from docx import Document
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        print(f"  ⚠️  שגיאה בקריאת {path.name}: {e}")
        return ""


def split_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list:
    chunks = []
    start  = 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += chunk_size - overlap
    return chunks


def load_all_documents() -> list:
    docs = []

    if not KNOWLEDGE_DIR.exists():
        print(f"❌ תיקיית knowledge לא נמצאה: {KNOWLEDGE_DIR}")
        return docs

    # --- 1. תקשי"ר ---
    takshir_path = KNOWLEDGE_DIR / "takshir.md"
    if takshir_path.exists():
        print(f"📄 תקשי\"ר: {takshir_path.name}")
        text   = read_markdown(takshir_path)
        chunks = split_text(text)
        for i, chunk in enumerate(chunks):
            docs.append({
                "id":   hashlib.md5(f"takshir_{i}".encode()).hexdigest(),
                "text": chunk,
                "metadata": {
                    "source": "takshir.md",
                    "type":   "takshir",
                    "chunk":  i,
                }
            })
        print(f"   ✅ {len(chunks)} קטעים")
    else:
        print("⚠️  takshir.md לא נמצא")

    # --- 2. הוראות תכ"ם ---
    takam_dir = KNOWLEDGE_DIR / "takam"
    if takam_dir.exists():
        docx_files = list(takam_dir.rglob("*.docx"))
        print(f"📁 תכ\"ם: {len(docx_files)} קבצים")
        for file_path in docx_files:
            print(f"   📄 {file_path.name}")
            text = read_docx(file_path)
            if not text.strip():
                continue
            chunks = split_text(text)
            for i, chunk in enumerate(chunks):
                docs.append({
                    "id":   hashlib.md5(f"takam_{file_path.name}_{i}".encode()).hexdigest(),
                    "text": chunk,
                    "metadata": {
                        "source": file_path.name,
                        "type":   "takam",
                        "chunk":  i,
                    }
                })
        print(f"   ✅ סה\"כ תכ\"ם נטען")
    else:
        print("⚠️  תיקיית takam לא נמצאה")

    # --- 3. MD של הפונקציות (עדיפות אחרונה) ---
    md_path = KNOWLEDGE_DIR / PROMPT_FILE
    if md_path.exists():
        print(f"📄 MD: {md_path.name}")
        text   = read_markdown(md_path)
        chunks = split_text(text)
        for i, chunk in enumerate(chunks):
            docs.append({
                "id":   hashlib.md5(f"md_{i}".encode()).hexdigest(),
                "text": chunk,
                "metadata": {
                    "source": md_path.name,
                    "type":   "md",
                    "chunk":  i,
                }
            })
        print(f"   ✅ {len(chunks)} קטעים")

    print(f"\n✅ סה\"כ {len(docs)} קטעים מוכנים")
    return docs


def build_index():
    from chromadb import PersistentClient
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    print("\n🔧 בונה אינדקס ChromaDB...")

    docs = load_all_documents()
    if not docs:
        print("❌ אין מסמכים")
        return

    embed_fn = SentenceTransformerEmbeddingFunction(
        model_name="intfloat/multilingual-e5-base"
    )

    client = PersistentClient(path=str(CHROMA_DIR))

    try:
        client.delete_collection("salary_knowledge")
        print("🗑️  קולקציה ישנה נמחקה")
    except Exception:
        pass

    collection = client.create_collection(
        name="salary_knowledge",
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"}
    )

    batch_size = 100
    for i in range(0, len(docs), batch_size):
        batch = docs[i:i + batch_size]
        collection.add(
            ids       = [d["id"]       for d in batch],
            documents = [d["text"]     for d in batch],
            metadatas = [d["metadata"] for d in batch],
        )
        print(f"  ✅ {i+1}–{min(i+batch_size, len(docs))}")

    print(f"\n🎉 אינדקס מוכן! {collection.count()} קטעים")


if __name__ == "__main__":
    build_index()
