"""
agent_tax.py
------------
סוכן מומחה מס הכנסה - ארכיטקטורה מבוססת מילון מתורגם ו-RAG (ללא לוגיקה קשיחה).
"""

import os
import json
import traceback
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR", "./knowledge"))

# שמות קבצי הידע (Knowledge Base) שמנהלים את הכל
TAX_PROMPT_FILE = "tax_prompt.md"
TAX_MAPPING_FILE_1 = "tax_input_output_symbols.json"
TAX_MAPPING_FILE_2 = "tax_output_symbols.json"
TAX_DATA_FILE_2 = "tax_data_2026.json" # אפשר לשנות לשנת 2025 במידת הצורך
TAX_DATA_FILE_1 = "tax_data_2025.json" # אפשר לשנות לשנת 2025 במידת הצורך
CHILDREN_POINTS_FILE = "children_points.json"

# -------------------------------------------------------
# פונקציות עזר לטעינת ידע
# -------------------------------------------------------
def load_text_file(filename: str, default: str = "") -> str:
    path = KNOWLEDGE_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    print(f"[LOAD] ⚠️ קובץ {filename} לא נמצא. משתמש בברירת מחדל.")
    return default

def load_json_file(filename: str) -> dict:
    path = KNOWLEDGE_DIR / filename
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    print(f"[LOAD] ⚠️ קובץ {filename} לא נמצא. מחזיר מילון ריק.")
    return {}

# -------------------------------------------------------
# מנוע התרגום (הלוגיקה היחידה של פייתון)
# -------------------------------------------------------
def translate_data_for_llm(raw_employee_data: dict, mapping_dict: dict) -> dict:
    """
    לוקח את התלוש הגולמי, מסנן וממפה אותו לשמות שדות בעברית לפי ה-JSON המילוני.
    בלי שום Hardcoding לסמלים ספציפיים.
    """
    print("[TRANSLATOR] מתחיל תרגום נתונים לעברית...")
    translated_data = {}
    elements = raw_employee_data.get("elements", {})
    
    for semel_id, rows in elements.items():
        # אם הסמל נמצא במילון שלנו
        if semel_id in mapping_dict:
            semel_info = mapping_dict[semel_id]
            heb_name = semel_info.get("name", f"סמל {semel_id}")
            fields_mapping = semel_info.get("fields", {})
            
            if not rows:
                continue
            
            # לוקחים את השורה האחרונה (החודש הנוכחי)
            latest_row = max(rows, key=lambda r: float(r.get("taarichSachar", 0) or 0))
            
            semel_translated_fields = {}
            for field_code, value in latest_row.items():
                # מתרגמים רק שדות שקיימים במילון ויש להם ערך ממשי
                if field_code in fields_mapping:
                    heb_field_name = fields_mapping[field_code]
                    try:
                        float_val = float(value)
                        if float_val != 0:  # סינון ערכי אפס
                            semel_translated_fields[heb_field_name] = float_val
                    except (ValueError, TypeError):
                        if value: # טקסט שאינו ריק
                            semel_translated_fields[heb_field_name] = value
            
            # מוסיפים רק אם נמצאו נתונים
            if semel_translated_fields:
                translated_data[heb_name] = semel_translated_fields
                
    print(f"[TRANSLATOR] התרגום הסתיים. סמלים מתורגמים: {list(translated_data.keys())}")
    return translated_data

# -------------------------------------------------------
# פונקציה ראשית - ניהול הסוכן
# -------------------------------------------------------
def explain_tax(employee_data: dict, question: str) -> str:
    print(f"\n{'='*50}")
    print(f"[TAX AGENT] התחלה - ארכיטקטורה חכמה")
    print(f"[TAX AGENT] שאלת משתמש: {question}")
    print(f"{'='*50}")

    try:
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(
            model="claude-sonnet-4-5",
            temperature=0,
            max_tokens=2048,
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        print(f"[TAX AGENT] ✅ LLM אותחל")
    except Exception as e:
        print(f"[TAX AGENT] ❌ שגיאה באתחול LLM: {e}")
        traceback.print_exc()
        raise

    # 1. טעינת בסיס הידע (Knowledge Base)
    tax_prompt = load_text_file(TAX_PROMPT_FILE, default="ענה כסוכן מס מקצועי.")
    mapping_dict = load_json_file(TAX_MAPPING_FILE)
    tax_data = load_text_file(TAX_DATA_FILE) # טוענים כטקסט פשוט כדי להזריק לפרומפט
    children_points = load_text_file(CHILDREN_POINTS_FILE) # טוענים כטקסט פשוט

    if not mapping_dict:
        return f"❌ שגיאה: קובץ המילון {TAX_MAPPING_FILE} לא נמצא. המערכת לא יכולה לתרגם את נתוני התלוש."

    # 2. תרגום הנתונים למילים (The Magic)
    translated_payslip = translate_data_for_llm(employee_data, mapping_dict)

    # 3. הרכבת הפרומפט הסופי למודל (RAG Pipeline)
    prompt = f"""
{tax_prompt}

--- ספר החוקים ופרמטרים (Reference Data) ---
1. מדרגות מס לתקופה זו:
{tax_data}

2. חוקת זכאות לנקודות ילדים:
{children_points}

--- נתוני התלוש המתורגמים של העובד החודש ---
{json.dumps(translated_payslip, ensure_ascii=False, indent=2)}

====================================================
שאלת העובד: {question}
====================================================
"""

    print(f"[LLM] שולח פרומפט מאוחד למודל... (טקסט באורך {len(prompt)} תווים)")
    
    # 4. ביצוע החשיבה (Reasoning)
    try:
        result = llm.invoke(prompt)
        content = result.content if hasattr(result, "content") else str(result)
        print(f"[LLM] ✅ ההסבר הושלם. מחזיר למשתמש.")
        return content
    except Exception as e:
        print(f"[LLM] ❌ שגיאה בקריאה למודל השפה: {e}")
        traceback.print_exc()
        raise
