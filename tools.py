"""
tools.py
--------
חיפוש סמנטי ב-ChromaDB לפי סדר עדיפויות:
  1. תקשי"ר
  2. תכ"ם
  3. MD
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

CHROMA_DIR = Path(os.getenv("CHROMA_DIR", "./chroma_db"))

_collection = None

def _get_collection():
    global _collection
    if _collection is not None:
        return _collection

    from chromadb import PersistentClient
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    embed_fn = SentenceTransformerEmbeddingFunction(
        model_name="intfloat/multilingual-e5-base"
    )
    client = PersistentClient(path=str(CHROMA_DIR))

    try:
        _collection = client.get_collection(
            name="salary_knowledge",
            embedding_function=embed_fn,
        )
        print(f"✅ ChromaDB נטען: {_collection.count()} קטעים")
    except Exception as e:
        print(f"❌ שגיאה בטעינת ChromaDB: {e}")
        _collection = None

    return _collection


def _search_by_type(query: str, source_type: str, n_results: int = 3) -> list:
    """חיפוש לפי סוג מקור ספציפי."""
    collection = _get_collection()
    if collection is None:
        return []

    try:
        results = collection.query(
            query_texts = [query],
            n_results   = n_results,
            where       = {"type": source_type},
        )
        docs = results.get("documents", [[]])[0]
        return [d for d in docs if d and d.strip()]
    except Exception as e:
        print(f"⚠️  שגיאה בחיפוש {source_type}: {e}")
        return []


def search_salary_regulations(query: str, n_results: int = 5) -> str:
    """
    מחפש לפי סדר עדיפויות:
    1. תקשי"ר
    2. תכ"ם
    3. MD

    מחזיר את הממצאים עם ציון המקור.
    """
    all_results = []

    # --- עדיפות 1: תקשי"ר ---
    takshir_results = _search_by_type(query, "takshir", n_results=3)
    if takshir_results:
        all_results.append("📘 מתקשי\"ר:")
        for r in takshir_results:
            all_results.append(r)
        print(f"  ✅ נמצא בתקשי\"ר: {len(takshir_results)} קטעים")

    # --- עדיפות 2: תכ"ם ---
    takam_results = _search_by_type(query, "takam", n_results=2)
    if takam_results:
        all_results.append("\n📗 מהוראות תכ\"ם:")
        for r in takam_results:
            all_results.append(r)
        print(f"  ✅ נמצא בתכ\"ם: {len(takam_results)} קטעים")

    # --- עדיפות 3: MD (רק אם לא נמצא כלום) ---
    if not takshir_results and not takam_results:
        md_results = _search_by_type(query, "md", n_results=3)
        if md_results:
            all_results.append("\n📄 מקובץ הלוגיקה:")
            for r in md_results:
                all_results.append(r)
            print(f"  ✅ נמצא ב-MD: {len(md_results)} קטעים")

    if not all_results:
        return "לא נמצא מידע רלוונטי."

    return "\n\n".join(all_results)
