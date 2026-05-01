"""
agent.py
--------
לוגיקה לפי תרשים זרימה v5:
1. LLM קורא שאלה → מחזיר query לחיפוש
2. Python מחפש בתקשי"ר/תכ"ם/MD
3. LLM מנתח → מחזיר JSON (שמות/תכונה/נוסחה/time_scope)
4. Python מחפש שמות ב-employeeData או תכונה ב-ecology
5. Python שולף נתונים לפי time_scope
6. Python מחשב ומאמת מול תלוש
"""

import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "aya-expanse:32b")
KNOWLEDGE_DIR   = Path(os.getenv("KNOWLEDGE_DIR", "./knowledge"))
PROMPT_FILE     = os.getenv("PROMPT_FILE", "hesberbeclick_bot_prompt_v2.md")
MAX_RETRIES     = 1

# -------------------------------------------------------
# כלים עזר
# -------------------------------------------------------

def get_llm():
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(
        model       = "claude-sonnet-4-5",
        temperature = 0,
        max_tokens  = 2048,
        api_key     = os.getenv("ANTHROPIC_API_KEY")
    )

def load_system_prompt() -> str:
    path = KNOWLEDGE_DIR / PROMPT_FILE
    restriction = (
        "\n\n====================================================\n"
        "כללים קשוחים — חובה לפעול לפיהם:\n"
        "====================================================\n"
        "- ענה אך ורק על בסיס המידע שסופק מהתקשי\"ר, התכ\"ם, וקובץ הלוגיקה.\n"
        "- אסור להשתמש בידע כללי או מידע מהאינטרנט.\n"
        "- אם המידע לא נמצא במקורות — אמור במפורש: 'לא נמצא מידע במקורות הידע'.\n"
        "- אל תנחש ואל תמציא נוסחאות.\n"
    )
    if not path.exists():
        return "אתה עוזר מקצועי לניתוח תלושי שכר של עובדי מדינה בישראל." + restriction
    return path.read_text(encoding="utf-8") + restriction

_ecology = None
def get_ecology() -> dict:
    global _ecology
    if _ecology is not None:
        return _ecology
    path = KNOWLEDGE_DIR / "ecology.json"
    if not path.exists():
        _ecology = {}
    else:
        _ecology = json.loads(path.read_text(encoding="utf-8"))
    return _ecology

def extract_json(text: str) -> dict | None:
    """מחלץ JSON מתוך תשובת המודל."""
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            return None
    return None
def invoke_llm(llm, prompt: str) -> str:
    """קורא ל-LLM ומחזיר תמיד string — תומך ב-ChatAnthropic וב-Ollama."""
    result = llm.invoke(prompt)
    if hasattr(result, 'content'):
        return result.content
    return str(result)

# -------------------------------------------------------
# שלב 1: LLM קורא שאלה → מחזיר query לחיפוש
# -------------------------------------------------------

def extract_search_query(question: str, llm) -> str:
    """
    LLM מקבל שאלה חופשית ומחזיר מילות מפתח לחיפוש בתקשי"ר.
    """
    prompt = (
        "אתה עוזר לניתוח שכר עובדי מדינה.\n"
        "קרא את השאלה הבאה והחזר מילות מפתח בעברית לחיפוש בתקשי\"ר.\n"
        "החזר 3-5 מילות מפתח בלבד, מופרדות ברווח.\n"
        "אל תוסיף הסברים.\n\n"
        "שאלה: " + question
    )
  
    result = invoke_llm(llm, prompt).strip()
    print(f"🔍 מילות מפתח לחיפוש: {result}")
    return result


# -------------------------------------------------------
# שלב 3: LLM מנתח תקשי"ר + שאלה → JSON
# -------------------------------------------------------

def analyze_and_extract(question: str, regulations: str, llm, employee_data: dict = {}) -> dict:
    """
    LLM מצליב שאלה + מידע מהתקשי"ר ומחזיר JSON מובנה.
    מקבל גם רשימת שמות סמלים מהתלוש כדי לבחור בדיוק.
    """
    system_prompt = load_system_prompt()

    # רשימת שמות סמלים מהתלוש
    available_names = list(set(
        rows[0].get("shemSemel", "")
        for rows in employee_data.get("elements", {}).values()
        if rows and rows[0].get("shemSemel")
    ))

    prompt = (
        system_prompt + "\n\n"
        "====================================================\n"
        "מידע שנמצא בתקשי\"ר / תכ\"ם:\n"
        "====================================================\n"
        + regulations +
        "\n\n====================================================\n"
        "רשימת שמות הסמלים הקיימים בתלוש העובד:\n"
        "====================================================\n"
        + str(available_names) +
        "\n\n====================================================\n"
        "שאלת המשתמש:\n"
        "====================================================\n"
        + question +
        "\n\n====================================================\n"
        "משימה:\n"
        "====================================================\n"
        "נתח את השאלה והמידע מהתקשי\"ר.\n"
        "החזר JSON בלבד ללא טקסט נוסף:\n"
        "{\n"
        "  \"names\": [\"בחר שמות מדויקים מתוך רשימת הסמלים שסופקה בלבד. "
        "התאם בין שמות התקשי\\\"ר לשמות בתלוש לפי הבנה סמנטית. "
        "למשל: 'ברוטו פנסיה' בתקשי\\\"ר = 'בסיס לפנסיה' בתלוש\"],\n"
        "  \"property\": \"מספר תכונה אם נדרש לפי תכונה, למשל: 201. אחרת null\",\n"
        "  \"formula\": \"נוסחה מתמטית. השתמש בשמות הסמלים בדיוק כפי שהם מופיעים ברשימת הסמלים — "
        "ללא קווים תחתונים וללא מילת semel. "
        "למשל: 'בסיס לפנסיה * 0.6'\",\n"
        "  \"time_scope\": \"current | year_to_date | last_3_months | all\"\n"
       "  \"logic\": \"הסבר קצר על הסמל ואופן חישובו לפי המידע שנמצא במקורות (תקשי\\\"ר / תכ\\\"ם / לוגיקת מערכת). אם לא נמצא מידע — החזר null\"\n"
        "}\n\n"
        "הערות:\n"
        "- names: חייב להיות שמות מדויקים מרשימת הסמלים שסופקה\n"
        "- property: רק אם הנוסחה מתבססת על תכונה של סמלים\n"
        "- time_scope: current = שוטף בלבד (ברירת מחדל)\n"
        "- formula: השתמש בשמות בדיוק כפי שהם ברשימה"
    )

    response = invoke_llm(llm, prompt)
    result = extract_json(response)

    if not result:
        print("⚠️ המודל לא החזיר JSON תקין")
        return {
            "names": [],
            "property": None,
            "formula": "",
            "time_scope": "current"
        }

    print(f"📋 JSON מהמודל: {result}")
    return result


# -------------------------------------------------------
# שלב 4: Python מחפש מספרי סמלים
# -------------------------------------------------------

def find_semels_by_names(names: list, employee_data: dict) -> dict:
    """
    מחפש שמות סמלים ב-employeeData לפי shemSemel.
    מחזיר: {שם_סמל: מספר_סמל}
    """
    elements = employee_data.get("elements", {})
    found = {}

    for semel_id, rows in elements.items():
        if not rows:
            continue
        shem = rows[0].get("shemSemel", "")
        for name in names:
            if name and shem and name in shem:
                found[name] = semel_id
                print(f"  ✅ '{name}' → סמל {semel_id}")
                break

    return found


def find_semels_by_property(property_num: str, employee_data: dict) -> list:
    """
    מחפש סמלים לפי תכונה ב-ecology.json.
    מחזיר: [מספרי סמלים שיש להם את התכונה]
    """
    ecology = get_ecology()
    elements = employee_data.get("elements", {})
    found = []

    prop_key = None
    for key in ecology.get(list(ecology.keys())[0], {}).keys():
        if property_num in key:
            prop_key = key
            break

    if not prop_key:
        print(f"⚠️ תכונה {property_num} לא נמצאה ב-ecology")
        return []

    for semel_id, props in ecology.items():
        val = props.get(prop_key, "")
        if val and "T כן" in str(val) and semel_id in elements:
            found.append(semel_id)

    print(f"  ✅ נמצאו {len(found)} סמלים עם תכונה {property_num}")
    return found


# -------------------------------------------------------
# שלב 5: שליפת נתונים לפי time_scope
# -------------------------------------------------------

def fetch_employee_data(semel_ids: list, employee_data: dict, time_scope: str) -> dict:
    """
    שולף שורות מ-employeeData לפי רשימת סמלים וטווח זמן.
    """
    elements = employee_data.get("elements", {})
    result = {}

    # מציאת החודש הנוכחי
    max_date = 0
    for rows in elements.values():
        for row in rows:
            d = row.get("taarichSachar", 0)
            if d > max_date:
                max_date = d

    # המרת תאריך Excel לשנה
    def excel_to_year(serial):
        from datetime import datetime, timedelta
        try:
            dt = datetime(1899, 12, 30) + timedelta(days=int(serial))
            return dt.year
        except Exception:
            return 0

    current_year = excel_to_year(max_date)

    for semel_id in semel_ids:
        if semel_id not in elements:
            continue
        rows = elements[semel_id]

        if time_scope == "current":
            filtered = [r for r in rows if r.get("taarichSachar") == r.get("taarichErech")]
        elif time_scope == "year_to_date":
            filtered = [r for r in rows if excel_to_year(r.get("taarichErech", 0)) == current_year]
        elif time_scope == "last_3_months":
            dates = sorted(set(r.get("taarichErech", 0) for r in rows), reverse=True)
            last_3 = set(dates[:3])
            filtered = [r for r in rows if r.get("taarichErech", 0) in last_3]
        else:  # all
            filtered = rows

        if filtered:
            result[semel_id] = filtered

    return result


# -------------------------------------------------------
# שלב 6: חישוב ואימות
# -------------------------------------------------------
def perform_calculation(formula: str, name_to_semel: dict, fetched_data: dict) -> tuple[float, str]:
    expr = formula
    vars_dict = {}

    for name, semel_id in name_to_semel.items():
        rows = fetched_data.get(semel_id, [])
        total = sum(float(r.get("schum", 0)) for r in rows)
        vars_dict[name] = total
        expr = expr.replace(name, str(total))

    clean_expr = re.sub(r'[^0-9\+\-\*\/\.\(\) ]', '', expr)

    if not clean_expr.strip():
        return 0.0, formula

    try:
        result = eval(clean_expr, {"__builtins__": None}, {})
        return float(result), clean_expr
    except Exception:
        return 0.0, clean_expr


def format_response(
    question: str,
    analysis: dict,
    name_to_semel: dict,
    calc_value: float,
    actual_value: float,
    formula_with_values: str,
    success: bool
) -> str:
    status = "✅ חישוב מאומת" if success else "⚠️ פער בחישוב"

    res = f"📊 סטטוס: {status}\n"
    res += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

    formula = analysis.get('formula', '')
    if formula and formula != 'None':
        res += f"📝 נוסחה מהתקשי\"ר: {formula}\n\n"
        res += f"🔢 חישוב:\n{formula_with_values} = {calc_value:,.2f} ₪\n\n"
    else:
        res += f"📝 הסבר:\n{analysis.get('logic', 'לא נמצא מידע רלוונטי.')}\n\n"

    if actual_value and actual_value > 0:
        res += f"💰 מחושב: {calc_value:,.2f} ₪\n"
        res += f"💰 בתלוש: {actual_value:,.2f} ₪\n"

    res += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

    if not success and actual_value and actual_value > 0:
        res += "📌 הערה: נמצא פער — ייתכנו תנאים אישיים או עדכון חוקה מקומי."

    return res

# -------------------------------------------------------
# פונקציה ראשית
# -------------------------------------------------------

def explain_symbol(employee_data: dict, semel_target: int, free_question: str = "") -> str:
    from tools import search_salary_regulations

    llm = get_llm()

    # קביעת השאלה
    question = free_question if free_question else f"כיצד מחושב סמל {semel_target}"
    print(f"\n💬 שאלה: {question}")

    # --- שלב 1: LLM מחלץ query לחיפוש ---
    search_query = extract_search_query(question, llm)

    # --- שלב 2: Python מחפש בתקשי"ר/תכ"ם/MD ---
    print("📚 מחפש בתקשי\"ר...")
    regulations = search_salary_regulations(search_query)

    # --- שלב 3: LLM מנתח → JSON ---
    print("🧠 מנתח...")
    analysis = analyze_and_extract(question, regulations, llm, employee_data)
    names      = analysis.get("names", [])
    property_  = analysis.get("property")
    formula    = analysis.get("formula", "")
    time_scope = analysis.get("time_scope", "current")

    # --- שלב 4: Python מחפש מספרי סמלים ---
    print("🔬 מחפש סמלים...")
    name_to_semel = {}
    semel_ids = []

    if names:
        name_to_semel = find_semels_by_names(names, employee_data)
        semel_ids = list(name_to_semel.values())

    if property_:
        prop_semels = find_semels_by_property(str(property_), employee_data)
        semel_ids.extend(prop_semels)

    # --- שלב 5: שליפת נתונים לפי time_scope ---
    print(f"📊 שולף נתונים ({time_scope})...")
    fetched_data = fetch_employee_data(list(set(semel_ids)), employee_data, time_scope)

    # --- שלב 6: חישוב ואימות ---
    calc_value = 0.0
    formula_with_values = formula
    actual_value = 0.0
    success = False

    if formula and name_to_semel:
        calc_value, formula_with_values = perform_calculation(formula, name_to_semel, fetched_data)

        # ערך בפועל מהתלוש — הסמל הראשון ברשימה
        if names and names[0] in name_to_semel:
            first_semel = name_to_semel[names[0]]
            current_rows = [
                r for r in fetched_data.get(first_semel, [])
                if r.get("taarichSachar") == r.get("taarichErech")
            ]
            if current_rows:
                actual_value = float(current_rows[0].get("schum", 0))

        success = actual_value > 0 and abs(calc_value - actual_value) < 1.0

    return format_response(
        question            = question,
        analysis            = analysis,
        name_to_semel       = name_to_semel,
        calc_value          = calc_value,
        actual_value        = actual_value,
        formula_with_values = formula_with_values,
        success             = success,
    )
