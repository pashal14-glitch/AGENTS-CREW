"""
agent_tax.py
------------
סוכן מומחה מס הכנסה - ארכיטקטורת Time-Series (היסטוריה שנתית) וזיהוי מצטברים.
"""

import os
import json
import traceback
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR", "./knowledge"))

# שמות קבצי הידע (Knowledge Base)
TAX_PROMPT_FILE = "tax_prompt.md"
TAX_MAPPING_FILE_1 = "tax_input_output_symbols.json"
TAX_MAPPING_FILE_2 = "tax_output_symbols.json"
TAX_DATA_FILE_2026 = "tax_data_2026.json" # אפשר לשנות לפי שנת המס
TAX_DATA_FILE_2025 = "tax_data_2025.json"
CHILDREN_POINTS_FILE = "children_points.json"

# -------------------------------------------------------
# פונקציות עזר 
# -------------------------------------------------------
def load_text_file(filename: str, default: str = "") -> str:
    path = KNOWLEDGE_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    print(f"[LOAD] ⚠️ קובץ {filename} לא נמצא. משתמש בברירת מחדל.")
    return default

def load_json_file(filename: str):
    path = KNOWLEDGE_DIR / filename
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    print(f"[LOAD] ⚠️ קובץ {filename} לא נמצא.")
    return None

def excel_to_date(serial) -> datetime:
    """המרת תאריך מספרי (כפי שנהוג במערכות שכר) לתאריך אמיתי"""
    try:
        return datetime(1899, 12, 30) + timedelta(days=int(float(serial)))
    except Exception:
        return datetime(2000, 1, 1)

def get_field_key(idx: int) -> str:
    """המרת אינדקס לשם השדה הלוגי במערכת השכר (schum, kamut, וכו')"""
    idx = int(idx)
    if idx == 1: return "schum"
    if idx == 2: return "kamut"
    if idx == 3: return "achuz"
    if idx == 4: return "taarif"
    return f"field{idx + 4}" # לדוגמה אינדקס 5 הופך ל-field9

# -------------------------------------------------------
# הרכבת המילון והזרקת תגיות "מצטבר"
# -------------------------------------------------------
def build_unified_mapping() -> dict:
    """קורא את שני קבצי המילון ומשלב אותם, תוך סימון סמלי פלט כמצטברים"""
    mapping = {}
    
    # 1. טעינת קובץ קלט/פלט כללי
    data1 = load_json_file(TAX_MAPPING_FILE_1) or {}
    items1 = data1.get("סמלי_קלט", []) + data1.get("סמלי_פלט", [])
    for item in items1:
        semel = str(item.get("סמל", ""))
        if not semel or semel == "None": continue
        if semel not in mapping: mapping[semel] = {}
        idx = item.get("שדה_בסמל")
        name = item.get("אופי_הנתון", "")
        if idx and name:
            mapping[semel][get_field_key(idx)] = {"name": name}
            
    # 2. טעינת קובץ הפלט (tax_output_symbols.json) - חובה לסמן כמצטבר!
    data2 = load_json_file(TAX_MAPPING_FILE_2) or []
    if isinstance(data2, list):
        for item in data2:
            semel = str(item.get("סמל", ""))
            if not semel or semel == "None": continue
            if semel not in mapping: mapping[semel] = {}
            idx = item.get("שדה_בסמל")
            name = item.get("אופי_הנתון", "")
            if idx and name and name != "ריק":
                # הזרקה אוטומטית של המילה "מצטבר" כדי שהמודל יבין
                if "(מצטבר)" not in name:
                    name = f"{name} (מצטבר)"
                mapping[semel][get_field_key(idx)] = {"name": name}
                
    return mapping

# -------------------------------------------------------
# מנוע בניית ציר הזמן (Time-Series) למודל השפה
# -------------------------------------------------------
def translate_data_for_llm(raw_employee_data: dict, mapping_dict: dict) -> dict:
    """מתרגם נתונים ואוסף היסטוריה מתחילת השנה הנוכחית בלבד"""
    print("[TRANSLATOR] מתחיל איסוף היסטורי מתחילת שנת המס...")
    elements = raw_employee_data.get("elements", {})
    
    # מציאת שנת המס הנוכחית (לפי התאריך המקסימלי שנמצא בתלוש)
    max_serial = 0
    for rows in elements.values():
        for r in rows:
            val = r.get("taarichSachar", 0)
            if val:
                try: max_serial = max(max_serial, float(val))
                except: pass
                
    current_year = excel_to_date(max_serial).year if max_serial > 0 else datetime.now().year
    print(f"[TRANSLATOR] שנת המס שזוהתה לחישוב: {current_year}")

    translated_data = {}
    
    for semel, rows in elements.items():
        if semel not in mapping_dict:
            continue
            
        semel_mapping = mapping_dict[semel]
        
        # מיון השורות לפי תאריך כדי שהחודשים יופיעו כרונולוגית (חודש 1, חודש 2...)
        sorted_rows = sorted(rows, key=lambda r: float(r.get("taarichSachar", 0) or 0))
        
        for row in sorted_rows:
            serial = row.get("taarichSachar", 0)
            if not serial: continue
            
            try:
                dt = excel_to_date(serial)
                # דרישת הברזל: מביאים נתונים אך ורק מתחילת שנת המס!
                if dt.year != current_year:
                    continue 
                month_str = f"חודש {dt.month}"
            except Exception:
                continue
                
            for field_key, field_info in semel_mapping.items():
                val = row.get(field_key)
                if val is not None and str(val).strip() != "":
                    try:
                        f_val = float(val)
                        if f_val == 0: continue # מתעלמים מאפסים כדי למנוע רעש למודל
                    except ValueError:
                        f_val = val
                        
                    heb_name = field_info["name"]
                    if heb_name not in translated_data:
                        translated_data[heb_name] = {}
                        
                    # שמירת הנתון בציר הזמן של השדה הזה
                    translated_data[heb_name][month_str] = f_val
                    
    print(f"[TRANSLATOR] נאספו נתונים היסטוריים עבור {len(translated_data)} שדות.")
    return translated_data

# -------------------------------------------------------
# פונקציה ראשית - ניהול הסוכן
# -------------------------------------------------------
def explain_tax(employee_data: dict, question: str) -> str:
    print(f"\n{'='*50}")
    print(f"[TAX AGENT] התחלה - מנתח שאלת משתמש: {question}")
    print(f"{'='*50}")

    try:
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(
            model="claude-3-5-sonnet-20241022",
            temperature=0, # חובה לשמור על 0 למניעת הזיות
            max_tokens=2048,
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
    except Exception as e:
        print(f"[TAX AGENT] ❌ שגיאה באתחול LLM: {e}")
        traceback.print_exc()
        raise

    # 1. טעינת בסיס הידע
    tax_prompt = load_text_file(TAX_PROMPT_FILE, default="ענה כסוכן מס מקצועי.")
    mapping_dict = build_unified_mapping()
    tax_data = load_text_file(TAX_DATA_FILE_2026) 
    children_points = load_text_file(CHILDREN_POINTS_FILE)

    if not mapping_dict:
        return "❌ שגיאה: קבצי המילון לא נטענו. בדוק את תיקיית knowledge."

    # 2. בניית ציר הזמן לעברית
    translated_payslip = translate_data_for_llm(employee_data, mapping_dict)

    # 3. הרכבת הפרומפט הסופי (RAG Pipeline)
    prompt = f"""
{tax_prompt}

--- ספר החוקים ופרמטרים (Reference Data) ---
1. מדרגות מס לתקופה זו:
{tax_data}

2. חוקת זכאות לנקודות ילדים:
{children_points}

--- היסטוריית נתוני התלוש (מתחילת שנת המס) ---
{json.dumps(translated_payslip, ensure_ascii=False, indent=2)}

====================================================
שאלת העובד: {question}
====================================================
"""

    print(f"[LLM] שולח נתונים (ציר זמן) למודל לקבלת הסבר...")
    
    try:
        result = llm.invoke(prompt)
        content = result.content if hasattr(result, "content") else str(result)
        print(f"[LLM] ✅ ההסבר הושלם.")
        return content
    except Exception as e:
        print(f"[LLM] ❌ שגיאה בקריאה למודל: {e}")
        traceback.print_exc()
        raise
