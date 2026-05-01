"""
agent_tax.py
------------
סוכן מומחה מס הכנסה.

לוגיקה:
1. LLM קורא שאלה + tax_prompt.md → מחזיר סמלים + time_scope=year_to_date
2. Python שולף נתונים מינואר עד החודש הנוכחי
3. Python מחשב מס לפי מדרגות מ-tax_data_2026.json
4. LLM מסביר את החישוב בשפה אנושית
"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR", "./knowledge"))
TAX_PROMPT_FILE = "tax_prompt.md"
TAX_DATA_FILE   = "tax_data_2025.json"


# -------------------------------------------------------
# טעינת קבצי ידע
# -------------------------------------------------------

_tax_prompt = None
_tax_data   = None

def load_tax_prompt() -> str:
    global _tax_prompt
    if _tax_prompt:
        return _tax_prompt
    path = KNOWLEDGE_DIR / TAX_PROMPT_FILE
    if not path.exists():
        return "אתה סוכן מומחה למס הכנסה לעובדי מדינה."
    _tax_prompt = path.read_text(encoding="utf-8")
    return _tax_prompt

def load_tax_data() -> dict:
    global _tax_data
    if _tax_data:
        return _tax_data
    path = KNOWLEDGE_DIR / TAX_DATA_FILE
    if not path.exists():
        print(f"⚠️ {TAX_DATA_FILE} לא נמצא")
        return {}
    _tax_data = json.loads(path.read_text(encoding="utf-8"))
    return _tax_data

def invoke_llm(llm, prompt: str) -> str:
    result = llm.invoke(prompt)
    if hasattr(result, "content"):
        return result.content
    return str(result)


# -------------------------------------------------------
# שלב 1: LLM מזהה סמלים ו-time_scope
# -------------------------------------------------------

def identify_tax_symbols(question: str, llm) -> dict:
    """
    LLM קורא את השאלה ו-tax_prompt.md
    מחזיר: סמלים לשלוף + time_scope
    """
    tax_prompt = load_tax_prompt()

    prompt = (
        tax_prompt + "\n\n"
        "====================================================\n"
        "שאלת המשתמש: " + question + "\n\n"
        "החזר JSON בלבד:\n"
        "{\n"
        "  \"symbols\": [\"91430\", \"91434\", \"91003\"],\n"
        "  \"time_scope\": \"year_to_date\",\n"
        "  \"question_type\": \"points|tax_calc|general\"\n"
        "}"
    )

    result = invoke_llm(llm, prompt)

    import re
    result = re.sub(r'```json\s*', '', result)
    result = re.sub(r'```\s*', '', result)
    match = re.search(r'\{.*\}', result, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass

    # ברירת מחדל
    return {
        "symbols": ["91430", "91434", "91003", "91400"],
        "time_scope": "year_to_date",
        "question_type": "general"
    }


# -------------------------------------------------------
# שלב 2: Python שולף נתונים לפי time_scope
# -------------------------------------------------------

def excel_to_date(serial: int) -> datetime:
    try:
        return datetime(1899, 12, 30) + timedelta(days=int(serial))
    except Exception:
        return datetime(2000, 1, 1)

def fetch_tax_data(symbols: list, employee_data: dict, time_scope: str) -> dict:
    """שולף נתונים לפי סמלים וטווח זמן."""
    elements = employee_data.get("elements", {})
    result   = {}

    # מציאת החודש הנוכחי ושנת המס
    max_date = 0
    for rows in elements.values():
        for row in rows:
            d = row.get("taarichSachar", 0)
            if d > max_date:
                max_date = d

    current_dt   = excel_to_date(max_date)
    current_year = current_dt.year

    for symbol in symbols:
        if symbol not in elements:
            continue
        rows = elements[symbol]

        if time_scope == "year_to_date":
            filtered = [
                r for r in rows
                if excel_to_date(r.get("taarichErech", 0)).year == current_year
            ]
        elif time_scope == "current":
            filtered = [
                r for r in rows
                if r.get("taarichSachar") == r.get("taarichErech")
            ]
        else:
            filtered = rows

        if filtered:
            result[symbol] = filtered

    return result


# -------------------------------------------------------
# שלב 3: Python מחשב מס לפי מדרגות
# -------------------------------------------------------

def calc_tax_by_brackets(monthly_income: float, tax_data: dict) -> float:
    """מחשב מס חודשי לפי מדרגות."""
    brackets = tax_data.get("מדרגות_חודשי", [])
    tax = 0.0

    for bracket in brackets:
        low  = bracket.get("מ", 0)
        high = bracket.get("עד", 999999)
        rate = bracket.get("שיעור", 0) / 100

        if monthly_income <= low:
            break
        taxable = min(monthly_income, high) - low
        tax += taxable * rate

    return round(tax, 2)


def calc_credit_points_value(points: float, tax_data: dict) -> float:
    """מחשב שווי נקודות זיכוי."""
    point_value = tax_data.get("ערך_נקודת_זיכוי_חודשי", 242)
    return round(points * point_value, 2)


def perform_tax_calculation(fetched_data: dict, tax_data: dict) -> dict:
    """
    מחשב את המס המלא לפי הנתונים שנשלפו.
    בוחר את החודש עם תאריך השכר הגבוה ביותר.
    """

    def get_latest_row(rows: list) -> dict:
        if not rows:
            return {}
        return max(rows, key=lambda r: r.get("taarichSachar", 0))

 def get_field(row: dict, field: str, default: float = 0.0) -> float:
    val = row.get(field, default)
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

    # --- סמל 91430 ---
    r91430 = get_latest_row(fetched_data.get("91430", []))
    points_monthly = get_field(r91430, "schum")
    marginal_rate  = get_field(r91430, "field13")
    points_cumul   = get_field(r91430, "field18")

    # --- סמל 91434 ---
    r91434 = get_latest_row(fetched_data.get("91434", []))
    points_detail_monthly = {}
    field_map_monthly = {
        "תושב":     "schum",
        "צעיר":     "kamut",
        "ילד 18/0": "achuz",
        "ילד 6-17": "taarif",
        "חד הורי":  "field9",
        "בן זוג":   "field10",
        "חייל":     "field11",
        "עולה":     "field12",
        "אקדמי":    "field13",
    }
    for name, field in field_map_monthly.items():
        val = get_field(r91434, field)
        if val > 0:
            points_detail_monthly[name] = val

    points_toshav_cumul = get_field(r91434, "field19")

    # --- סמל 91435 ---
    r91435 = get_latest_row(fetched_data.get("91435", []))
    points_detail_cumul = {}
    if get_field(r91435, "schum") > 0:
        points_detail_cumul["פעוט 1-5 מצטבר"] = get_field(r91435, "schum")
    if get_field(r91435, "kamut") > 0:
        points_detail_cumul["חד הורי מצטבר"] = get_field(r91435, "kamut")
    if get_field(r91435, "achuz") > 0:
        points_detail_cumul["בן זוג מצטבר"] = get_field(r91435, "achuz")

    # --- סמל 91436 ---
    r91436 = get_latest_row(fetched_data.get("91436", []))
    field_map_children = {
        "ילד 0 מצטבר":       "schum",
        "ילד 0 חודשי":        "kamut",
        "ילד 1-5 חודשי":      "achuz",
        "ילד 6-12 אשה חודשי": "field12",
        "ילד 6-12 גבר חודשי": "field13",
        "ילד 6-12 אשה מצטבר": "field16",
        "ילד 6-12 גבר מצטבר": "field17",
    }
    for name, field in field_map_children.items():
        val = get_field(r91436, field)
        if val > 0:
            points_detail_cumul[name] = val

    # --- סמל 91400 ---
    r91400 = get_latest_row(fetched_data.get("91400", []))
    income_regular = get_field(r91400, "schum")
    income_annual  = get_field(r91400, "kamut")

    # --- סמל 91410 ---
    r91410 = get_latest_row(fetched_data.get("91410", []))
    income_cumul = get_field(r91410, "schum") if r91410 else income_regular

    # --- סמל 91003 ---
    r91003 = get_latest_row(fetched_data.get("91003", []))
    actual_deduction = get_field(r91003, "schum")

    # --- חישוב מס ---
    total_income    = income_regular + income_annual
    tax_by_brackets = calc_tax_by_brackets(total_income, tax_data)
    credit_value    = calc_credit_points_value(points_monthly, tax_data)
    calculated_tax  = max(0.0, round(tax_by_brackets - credit_value, 2))

    if points_toshav_cumul > 0:
        points_detail_cumul["תושב מצטבר"] = points_toshav_cumul

    return {
        "הכנסה_חייבת_רגילה":  income_regular,
        "הכנסה_חייבת_שנתית":  income_annual,
        "הכנסה_חייבת_סה_כ":   total_income,
        "הכנסה_מצטברת":       income_cumul,
        "מס_לפי_מדרגות":      tax_by_brackets,
        "נקודות_זיכוי_חודש":  points_monthly,
        "נקודות_זיכוי_מצטבר": points_cumul,
        "פירוט_נקודות_חודשי": points_detail_monthly,
        "פירוט_נקודות_מצטבר": points_detail_cumul,
        "שווי_נקודות_זיכוי":  credit_value,
        "מס_מחושב":           calculated_tax,
        "ניכוי_בפועל":        actual_deduction,
        "אחוז_שולי":          marginal_rate,
        "תואם": abs(calculated_tax - actual_deduction) < 10.0,
    }


def explain_tax_calculation(question: str, calc_result: dict, llm) -> str:
    """LLM מקבל את החישוב המתמטי ומסביר בשפה אנושית."""
    tax_prompt = load_tax_prompt()

    prompt = (
        tax_prompt + "\n\n"
        "====================================================\n"
        "תוצאות החישוב (בוצע על ידי Python):\n"
        "====================================================\n"
        + json.dumps(calc_result, ensure_ascii=False, indent=2) +
        "\n\n====================================================\n"
        "שאלת המשתמש: " + question + "\n\n"
        "====================================================\n"
        "הסבר בעברית תמציתית לפי הפורמט:\n"
        "📊 נקודות זיכוי בחודש: X\n"
        "   פירוט: [רק רכיבים > 0]\n"
        "📊 נקודות מצטברות: Y\n"
        "📊 שווי נקודות: Z ₪\n"
        "הצג רק רכיבים עם ערך גדול מאפס. ללא מלל מיותר."
    )

    return invoke_llm(llm, prompt)
# -------------------------------------------------------
# פונקציה ראשית
# -------------------------------------------------------

def explain_tax(employee_data: dict, question: str) -> str:
    from langchain_anthropic import ChatAnthropic

    llm = ChatAnthropic(
        model       = "claude-sonnet-4-5",
        temperature = 0,
        max_tokens  = 2048,
        api_key     = os.getenv("ANTHROPIC_API_KEY")
    )

    tax_data = load_tax_data()
    if not tax_data:
        return "❌ לא נמצא קובץ tax_data_2026.json. יש להוסיפו לתיקיית knowledge."

    print(f"\n💰 סוכן מס: {question}")

    # שלב 1: זיהוי סמלים
    print("🧠 מזהה סמלים...")
    identification = identify_tax_symbols(question, llm)
    symbols    = identification.get("symbols", ["91430", "91434", "91003", "91400"])
    time_scope = identification.get("time_scope", "year_to_date")
    print(f"   סמלים: {symbols} | טווח: {time_scope}")

    # שלב 2: שליפת נתונים
  print("📊 שולף נתונים...")
try:
    fetched_data = fetch_tax_data(symbols, employee_data, time_scope)
except Exception as e:
    import traceback
    print(f"❌ שגיאה בשליפה: {e}")
    traceback.print_exc()
    raise
    print(f"   נשלפו: {list(fetched_data.keys())}")

    # שלב 3: חישוב
    print("🔢 מחשב...")
    calc_result = perform_tax_calculation(fetched_data, tax_data)
    print(f"   מס מחושב: {calc_result['מס_מחושב']} ₪ | בפועל: {calc_result['ניכוי_בפועל']} ₪")

    # שלב 4: הסבר
    print("💬 מסביר...")
    return explain_tax_calculation(question, calc_result, llm)
