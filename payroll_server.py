import os
import json
import glob
from flask import Flask, request, jsonify
from flask_cors import CORS

# --- Document Loaders ---
from langchain_community.document_loaders import (
    TextLoader,
    Docx2txtLoader
)
from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_text_splitters import RecursiveCharacterTextSplitter

# --- Vector Store & Embeddings ---
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

# --- LLM ---
# לעבור ל-RunPod: שנה את base_url בלבד
from langchain_community.llms import Ollama

# --- LangChain Core ---
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

# ============================================================
# הגדרות — שנה כאן בלבד
# ============================================================

# תיקיית קבצי הידע
KNOWLEDGE_DIR = "knowledge"

# תיקיית ה-Vector DB
DB_DIR = "payroll_db"

# מודל LLM
# מקומי: Ollama(model="qwen2.5:3b", temperature=0)
# RunPod: לשנות את base_url בלבד — שאר הקוד זהה
LLM_MODEL  = "qwen2.5:3b"
LLM_BASE_URL = "http://localhost:11434"  # ← שורה זו בלבד משתנה ל-RunPod

# ============================================================

app = Flask(__name__)
CORS(app)

print("מתחבר למנועי הבינה המלאכותית...")

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

llm = Ollama(
    model=LLM_MODEL,
    base_url=LLM_BASE_URL,
    temperature=0
)

# ============================================================
# בניית מאגר הידע
# ============================================================

def load_md_file(filepath):
    """קריאת קובץ MD עם חיתוך לפי כותרות"""
    headers_to_split_on = [
        ("#",   "פרק"),
        ("##",  "סעיף"),
        ("###", "תת_סעיף"),
    ]
    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False
    )
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    chunks = splitter.split_text(content)
    
    # הוספת מקור לכל chunk
    for chunk in chunks:
        chunk.metadata["source"] = os.path.basename(filepath)
    
    return chunks


def load_docx_file(filepath):
    """קריאת קובץ Word עם חיתוך לפי גודל"""
    loader = Docx2txtLoader(filepath)
    documents = loader.load()
    
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        separators=["\n\n", "\n", ".", " "]
    )
    chunks = splitter.split_documents(documents)
    
    for chunk in chunks:
        chunk.metadata["source"] = os.path.basename(filepath)
    
    return chunks


def setup_database():
    """בניית מאגר הידע מכל הקבצים"""
    
    # אם המאגר קיים — טען אותו
    if os.path.exists(DB_DIR):
        print("✅ מאגר הידע קיים. המערכת מוכנה!")
        return Chroma(persist_directory=DB_DIR, embedding_function=embeddings)
    
    print("📚 בונה מאגר ידע חדש מהקבצים...")
    all_chunks = []
    
    # --- קבצי MD (תקשי"ר + ידע נוסף) ---
    md_files = glob.glob(os.path.join(KNOWLEDGE_DIR, "*.md"))
    for filepath in md_files:
        print(f"  📄 קורא: {os.path.basename(filepath)}")
        try:
            chunks = load_md_file(filepath)
            all_chunks.extend(chunks)
            print(f"     ✓ {len(chunks)} קטעים")
        except Exception as e:
            print(f"     ❌ שגיאה: {e}")
    
    # --- קבצי Word (הוראות תכ"ם) ---
    takam_dir = os.path.join(KNOWLEDGE_DIR, "takam")
    if os.path.exists(takam_dir):
        docx_files = glob.glob(os.path.join(takam_dir, "*.docx"))
        for filepath in docx_files:
            print(f"  📄 קורא: {os.path.basename(filepath)}")
            try:
                chunks = load_docx_file(filepath)
                all_chunks.extend(chunks)
                print(f"     ✓ {len(chunks)} קטעים")
            except Exception as e:
                print(f"     ❌ שגיאה: {e}")
    
    if not all_chunks:
        print("⚠️  לא נמצאו קבצים בתיקיית knowledge/")
        print("    וודאי שהמבנה הוא:")
        print("    knowledge/")
        print("    ├── takshir.md")
        print("    ├── yeda_nosaf.md")
        print("    └── takam/")
        print("        ├── havraa.docx")
        print("        └── ...")
        raise FileNotFoundError("לא נמצאו קבצי ידע")
    
    print(f"\n✨ סה\"כ {len(all_chunks)} קטעים — בונה אינדקס...")
    db = Chroma.from_documents(all_chunks, embeddings, persist_directory=DB_DIR)
    print("✅ המאגר מוכן!")
    return db


db = setup_database()
retriever = db.as_retriever(search_kwargs={"k": 4})

# ============================================================
# פרומפטים
# ============================================================

# פרומפט לשאלות כלליות (ללא נתוני עובד)
GENERAL_TEMPLATE = """אתה מומחה שכר בכיר במגזר הציבורי בישראל. אתה מכיר לעומק את תקשי"ר, הוראות תכ"ם והסכמים קיבוציים.

ענה על השאלה בהתבסס על המידע המצורף. אם המידע אינו מספיק — אמור זאת בכנות.

כללים:
1. ענה בעברית מקצועית ותקנית.
2. ציין את המקור (תקשי"ר / תכ"ם / הוראה) כשרלוונטי.
3. אם המידע חסר במסמכים — כתוב: "המידע אינו קיים במסמכים שברשותי".
4. אל תמציא מספרים או כללים שאינם במסמכים.

מידע רלוונטי:
{context}

שאלה: {question}

תשובה:"""

# פרומפט לשאלות עם נתוני עובד ספציפי
EMPLOYEE_TEMPLATE = """אתה חשב שכר בכיר במגזר הציבורי בישראל. קיבלת נתונים כספיים של עובד ספציפי ושאלה לגביו.

תפקידך: לנתח את הנתונים, להשתמש בידע המקצועי, ולתת הסבר מקצועי ומדויק.

כללים:
1. ענה בעברית מקצועית.
2. התייחס לנתוני העובד הספציפיים שסופקו.
3. הסבר חישובים צעד אחר צעד כשרלוונטי.
4. ציין אם משהו נראה חריג או שגוי.
5. אל תמציא נתונים שאינם בקלט.

ידע מקצועי רלוונטי (תקשי"ר / תכ"ם):
{context}

נתוני העובד:
{employee_data}

שאלה: {question}

תשובת חשב שכר:"""

general_prompt  = ChatPromptTemplate.from_template(GENERAL_TEMPLATE)
employee_prompt = ChatPromptTemplate.from_template(EMPLOYEE_TEMPLATE)

def format_docs(docs):
    return "\n\n".join(
        f"[{doc.metadata.get('source', '')}]\n{doc.page_content}"
        for doc in docs
    )

# ============================================================
# עזר: פורמט נתוני עובד לטקסט קריא
# ============================================================

def format_employee_data(employee_data: dict) -> str:
    """הופך את employeeData מה-JavaScript לטקסט קריא לפרומפט"""
    
    lines = []
    lines.append(f"תעודת זהות: {employee_data.get('zehut', 'לא ידוע')}")
    lines.append(f"מספר עובד:  {employee_data.get('misparOved', 'לא ידוע')}")
    lines.append(f"משרד:       {employee_data.get('misrad', 'לא ידוע')}")
    lines.append("")
    lines.append("רכיבי שכר:")
    lines.append("-" * 40)
    
    elements = employee_data.get("elements", {})
    
    for semel, rows in elements.items():
        if not rows:
            continue
        
        # שם הסמל מהשורה הראשונה
        shem = rows[0].get("shemSemel", "") if rows else ""
        label = f"סמל {semel}"
        if shem:
            label += f" — {shem}"
        
        lines.append(f"\n{label}:")
        
        for row in rows:
            parts = []
            
            schum = row.get("schum", 0)
            if schum:
                parts.append(f"סכום: {schum:,.2f} ₪")
            
            kamut = row.get("kamut", 0)
            if kamut:
                parts.append(f"כמות: {kamut}")
            
            achuz = row.get("achuz", 0)
            if achuz:
                parts.append(f"אחוז: {achuz}%")
            
            tarif = row.get("tarif", 0)
            if tarif:
                parts.append(f"תעריף: {tarif:,.4f}")
            
            taarich = row.get("taarichSachar", "")
            if taarich:
                parts.append(f"תאריך שכר: {taarich}")
            
            # שדות ערך נוספים (field9-field28)
            extra = []
            for i in range(9, 29):
                val = row.get(f"field{i}", 0)
                if val and val != 0:
                    extra.append(f"ע{i-4}={val}")
            if extra:
                parts.append(f"נתוני עזר: {', '.join(extra)}")
            
            if parts:
                lines.append("  • " + " | ".join(parts))
    
    return "\n".join(lines)

# ============================================================
# Routes
# ============================================================

@app.route('/ask', methods=['POST'])
def ask_general():
    """שאלה כללית — ללא נתוני עובד ספציפי"""
    data = request.json
    user_query = data.get('question', '').strip()
    
    if not user_query:
        return jsonify({"error": "לא נשלחה שאלה"}), 400

    print(f"\n📩 שאלה כללית: {user_query}")

    # ברכות קצרות — ללא LLM
    greetings = ["שלום", "היי", "בוקר טוב", "הי", "מה נשמע", "תודה"]
    if any(user_query.startswith(g) for g in greetings) and len(user_query.split()) < 4:
        return jsonify({"answer": "שלום! אני עוזר השכר הווירטואלי. אפשר לשאול שאלות על תקשי\"ר, תכ\"ם, ורכיבי שכר."})

    try:
        docs = retriever.invoke(user_query)
        context = format_docs(docs)
        
        chain = general_prompt | llm | StrOutputParser()
        response = chain.invoke({"context": context, "question": user_query})
        
        print(f"✅ תשובה נשלחה ({len(response)} תווים)")
        return jsonify({"answer": response})
    
    except Exception as e:
        print(f"❌ שגיאה: {e}")
        return jsonify({"error": "התרחשה שגיאה בעת עיבוד התשובה."}), 500


@app.route('/ask_with_data', methods=['POST'])
def ask_with_employee_data():
    """שאלה עם נתוני עובד ספציפי — מ-HesberBeKlik"""
    data = request.json
    user_query    = data.get('question', '').strip()
    employee_data = data.get('employeeData', {})
    
    if not user_query:
        return jsonify({"error": "לא נשלחה שאלה"}), 400
    
    if not employee_data:
        # אין נתוני עובד — נפנה לשאלה כללית
        return ask_general()

    zehut = employee_data.get('zehut', 'לא ידוע')
    print(f"\n📩 שאלה על עובד {zehut}: {user_query}")

    try:
        # שלב 1: שליפת ידע מקצועי רלוונטי
        docs = retriever.invoke(user_query)
        context = format_docs(docs)
        
        # שלב 2: פורמט נתוני העובד
        employee_text = format_employee_data(employee_data)
        
        # שלב 3: LLM עם פרומפט מלא
        chain = employee_prompt | llm | StrOutputParser()
        response = chain.invoke({
            "context":       context,
            "employee_data": employee_text,
            "question":      user_query
        })
        
        print(f"✅ תשובה נשלחה ({len(response)} תווים)")
        return jsonify({"answer": response, "employee": zehut})
    
    except Exception as e:
        print(f"❌ שגיאה: {e}")
        return jsonify({"error": "התרחשה שגיאה בעת עיבוד התשובה."}), 500


@app.route('/reload_db', methods=['POST'])
def reload_database():
    """מחיקה ובנייה מחדש של מאגר הידע — לאחר עדכון קבצים"""
    global db, retriever
    
    import shutil
    if os.path.exists(DB_DIR):
        shutil.rmtree(DB_DIR)
        print("🗑️  מאגר ישן נמחק")
    
    try:
        db = setup_database()
        retriever = db.as_retriever(search_kwargs={"k": 4})
        return jsonify({"status": "המאגר נבנה מחדש בהצלחה"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 שרת שכר פועל!")
    print(f"   מודל: {LLM_MODEL}")
    print(f"   מאגר: {DB_DIR}")
    print(f"   ידע:  {KNOWLEDGE_DIR}/")
    print("="*50)
    print("\nRoutes זמינים:")
    print("  POST /ask            — שאלה כללית")
    print("  POST /ask_with_data  — שאלה עם נתוני עובד")
    print("  POST /reload_db      — בנייה מחדש של המאגר")
    print("="*50 + "\n")
    app.run(port=5001, debug=False)
