"""
agent_tax.py
------------
סוכן מומחה מס הכנסה.
"""

import os
import json
import re
import traceback
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR", "./knowledge"))
TAX_PROMPT_FILE = "tax_prompt.md"
TAX_DATA_FILE = "tax_data_2025.json"

_tax_prompt = None
_tax_data = None

# -------------------------------------------------------
# טעינת קבצי ידע
# -------------------------------------------------------

def load_tax_prompt() -> str:
    global _tax_prompt
    if _tax_prompt:
        return _tax_prompt
    path = KNOWLEDGE_DIR / TAX_PROMPT_FILE
    print(f"[LOAD] טוען tax_prompt מ: {path} | קיים: {path.exists()}")
    if not path.exists():
        print(f"[LOAD] ⚠️ tax_prompt.md לא נמצא — משתמש בברירת מחדל")
        return "אתה סוכן מומחה למס הכנסה לעובדי מדינה."
    _tax_prompt = path.read_text(encoding="utf-8")
    print(f"[LOAD] ✅ tax_prompt נטען ({len(_tax_prompt)} תווים)")
    return _tax_prompt

def load_tax_data() -> dict:
    global _tax_data
    if _tax_data:
        print(f"[LOAD] tax_data כבר בזיכרון")
        return _tax_data
    path = KNOWLEDGE_DIR / TAX_DATA_FILE
    print(f"[LOAD] טוען tax_data מ: {path} | קיים: {path.exists()}")
    if not path.exists():
        print(f"[LOAD] ❌ {TAX_DATA_FILE} לא נמצא!")
        return {}
    _tax_data = json.loads(path.read_text(encoding="utf-8"))
    print(f"[LOAD] ✅ tax_data נטען, מפתחות: {list(_tax_data.keys())}")
    return _tax_data

def invoke_llm(llm, prompt: str) -> str:
    print(f"[LLM] שולח prompt ({len(prompt)} תווים)...")
    try:
        result = llm.invoke(prompt)
        content = result.content if hasattr(result, "content") else str(result)
        print(f"[LLM] ✅ תשובה התקבלה ({len(content)} תווים)")
        print(f"[LLM] תשובה גולמית: {content[:300]}...")
        return content
    except Exception as e:
        print(f"[LLM] ❌ שגיאה בקריאה ל-LLM: {e}")
        traceback.print_exc()
        raise

# -------------------------------------------------------
# שלב 1: LLM מזהה סמלים
# -------------------------------------------------------

def identify_tax_symbols(question: str, llm) -> dict:
    print(f"\n[שלב 1] זיהוי סמלים לשאלה: {question}")
    tax_prompt = load_tax_prompt()

    prompt = (
        tax_prompt + "\n\n"
        "====================================================\n"
        "שאלת המשתמש: " + question + "\n\n"
        "החזר JSON בלבד:\n"
        "{\n"
        "  \"symbols\": [\"91430\", \"91434\", \"91435\", \"91436\", \"91400\", \"91410\", \"91003\"],\n"
        "  \"time_scope\": \"year_to_date\",\n"
        "  \"question_type\": \"points|tax_calc|general\"\n"
        "}"
    )

    result = invoke_llm(llm, prompt)

    result_clean = re.sub(r'```json\s*', '', result)
    result_clean = re.sub(r'```\s*', '', result_clean)
    match = re.search(r'\{.*\}', result_clean, re.DOTALL)

    if match:
        try:
            parsed = json.loads(match.group())
            print(f"[שלב 1] ✅ JSON תקין: {parsed}")
            return parsed
        except Exception as e:
            print(f"[שלב 1] ❌ שגיאת פירוש JSON: {e}")
            print(f"[שלב 1] טקסט שניסינו לפרש: {match.group()[:200]}")

    print(f"[שלב 1] ⚠️ חוזר לברירת מחדל")
    return {
        "symbols": ["91430", "91434", "91435", "91436", "91400", "91410", "91003"],
        "time_scope": "year_to_date",
        "question_type": "general"
    }

# -------------------------------------------------------
# שלב 2: שליפת נתונים
# -------------------------------------------------------

def excel_to_date(serial: int) -> datetime:
    try:
        return datetime(1899, 12, 30) + timedelta(days=int(serial))
    except Exception:
        return datetime(2000, 1, 1)

def fetch_tax_data(symbols: list, employee_data: dict, time_scope: str) -> dict:
    print(f"\n[שלב 2] שולף סמלים: {symbols} | טווח: {time_scope}")
    elements = employee_data.get("elements", {})
    print(f"[שלב 2] סמלים קיימים בתלוש: {list(elements.keys())[:20]}...")

    result = {}

    max_date = 0
    for rows in elements.values():
        for row in rows:
            d = row.get("taarichSachar", 0)
            try:
                if int(float(d)) > max_date:
                    max_date = int(float(d))
            except (ValueError, TypeError):
                pass

    current_dt = excel_to_date(max_date)
    current_year = current_dt.year
    print(f"[שלב 2] תאריך מקסימלי: {max_date} → {current_dt.date()} | שנה: {current_year}")

    for symbol in symbols:
        if symbol not in elements:
            print(f"[שלב 2] ⚠️ סמל {symbol} — לא קיים בתלוש")
            continue

        rows = elements[symbol]
        print(f"[שלב 2] סמל {symbol}: {len(rows)} שורות")

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

        print(f"[שלב 2] סמל {symbol}: {len(filtered)} שורות אחרי סינון")
        if filtered:
            result[symbol] = filtered
        else:
            print(f"[שלב 2] ⚠️ סמל {symbol} — 0 שורות אחרי סינון!")

    print(f"[שלב 2] ✅ סמלים שנשלפו בהצלחה: {list(result.keys())}")
    return result

# -------------------------------------------------------
# שלב 3: חישוב מס
# -------------------------------------------------------

def calc_tax_by_brackets(monthly_income: float, tax_data: dict) -> float:
    brackets = tax_data.get("מדרגות_חודשי", [])
    print(f"[חישוב] הכנסה חייבת: {monthly_income} | מדרגות: {len(brackets)}")
    tax = 0.0
    for bracket in brackets:
        low = bracket.get("מ", 0)
        high = bracket.get("עד", 999999)
        rate = bracket.get("שיעור", 0) / 100
        if monthly_income <= low:
            break
        taxable = min(monthly_income, high) - low
        tax += taxable * rate
        print(f"[חישוב]   מדרגה {low}-{high} @ {rate*100}%: {taxable:.2f} → מס: {taxable*rate:.2f}")
    print(f"[חישוב] סה\"כ מס לפי מדרגות: {round(tax, 2)}")
    return round(tax, 2)

def calc_credit_points_value(points: float, tax_data: dict) -> float:
    point_value = tax_data.get("ערך_נקודת_זיכוי_חודשי", 242)
    result = round(points * point_value, 2)
    print(f"[חישוב] נקודות זיכוי: {points} × {point_value} = {result} ₪")
    return result

def perform_tax_calculation(fetched_data: dict, tax_data: dict) -> dict:
    print(f"\n[שלב 3] מחשב מס. סמלים בנתונים: {list(fetched_data.keys())}")

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

    r91430 = get_latest_row(fetched_data.get("91430", []))
    print(f"[שלב 3] 91430 שורה: {r91430}")
    points_monthly = get_field(r91430, "schum")
    marginal_rate = get_field(r91430, "field13")
    points_cumul = get_field(r91430, "field18")
    print(f"[שלב 3] נקודות חודשי={points_monthly} | שולי={marginal_rate} | מצטבר={points_cumul}")

    r91434 = get_latest_row(fetched_data.get("91434", []))
    print(f"[שלב 3] 91434 שורה: {r91434}")
    points_detail_monthly = {}
    field_map_monthly = {
        "תושב": "schum", "צעיר": "kamut", "ילד 18/0": "achuz",
        "ילד 6-17": "taarif", "חד הורי": "field9", "בן זוג": "field10",
        "חייל": "field11", "עולה": "field12", "אקדמי": "field13",
    }
    for name, field in field_map_monthly.items():
        val = get_field(r91434, field)
        if val > 0:
            points_detail_monthly[name] = val
    points_toshav_cumul = get_field(r91434, "field19")
    print(f"[שלב 3] פירוט נקודות חודשי: {points_detail_monthly}")

    r91435 = get_latest_row(fetched_data.get("91435", []))
    print(f"[שלב 3] 91435 שורה: {r91435}")
    points_detail_cumul = {}
    if get_field(r91435, "schum") > 0:
        points_detail_cumul["פעוט 1-5 מצטבר"] = get_field(r91435, "schum")
    if get_field(r91435, "kamut") > 0:
        points_detail_cumul["חד הורי מצטבר"] = get_field(r91435, "kamut")
    if get_field(r91435, "achuz") > 0:
        points_detail_cumul["בן זוג מצטבר"] = get_field(r91435, "achuz")

    r91436 = get_latest_row(fetched_data.get("91436", []))
    print(f"[שלב 3] 91436 שורה: {r91436}")
    field_map_children = {
        "ילד 0 מצטבר": "schum", "ילד 0 חודשי": "kamut",
        "ילד 1-5 חודשי": "achuz", "ילד 6-12 אשה חודשי": "field12",
        "ילד 6-12 גבר חודשי": "field13", "ילד 6-12 אשה מצטבר": "field16",
        "ילד 6-12 גבר מצטבר": "field17",
    }
    for name, field in field_map_children.items():
        val = get_field(r91436, field)
        if val > 0:
            points_detail_cumul[name] = val

    r91400 = get_latest_row(fetched_data.get("91400", []))
    print(f"[שלב 3] 91400 שורה: {r91400}")
    income_regular = get_field(r91400, "schum")
    income_annual = get_field(r91400, "kamut")
    print(f"[שלב 3] הכנסה רגילה={income_regular} | שנתית={income_annual}")

    r91410 = get_latest_row(fetched_data.get("91410", []))
    print(f"[שלב 3] 91410 שורה: {r91410}")
    income_cumul = get_field(r91410, "schum") if r91410 else income_regular

    r91003 = get_latest_row(fetched_data.get("91003", []))
    print(f"[שלב 3] 91003 שורה: {r91003}")
    actual_deduction = get_field(r91003, "schum")
    print(f"[שלב 3] ניכוי בפועל: {actual_deduction}")

    total_income = income_regular + income_annual
    tax_by_brackets = calc_tax_by_brackets(total_income, tax_data)
    credit_value = calc_credit_points_value(points_monthly, tax_data)
    calculated_tax = max(0.0, round(tax_by_brackets - credit_value, 2))
    print(f"[שלב 3] ✅ מס סופי: {tax_by_brackets} - {credit_value} = {calculated_tax}")

    if points_toshav_cumul > 0:
        points_detail_cumul["תושב מצטבר"] = points_toshav_cumul

    return {
        "הכנסה_חייבת_רגילה": income_regular,
        "הכנסה_חייבת_שנתית": income_annual,
        "הכנסה_חייבת_סה_כ": total_income,
        "הכנסה_מצטברת": income_cumul,
        "מס_לפי_מדרגות": tax_by_brackets,
        "נקודות_זיכוי_חודש": points_monthly,
        "נקודות_זיכוי_מצטבר": points_cumul,
        "פירוט_נקודות_חודשי": points_detail_monthly,
        "פירוט_נקודות_מצטבר": points_detail_cumul,
        "שווי_נקודות_זיכוי": credit_value,
        "מס_מחושב": calculated_tax,
        "ניכוי_בפועל": actual_deduction,
        "אחוז_שולי": marginal_rate,
        "תואם": abs(calculated_tax - actual_deduction) < 10.0,
    }

# -------------------------------------------------------
# שלב 4: הסבר LLM
# -------------------------------------------------------

def explain_tax_calculation(question: str, calc_result: dict, llm) -> str:
    print(f"\n[שלב 4] מסביר תוצאה ל-LLM...")
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
        " פירוט: [רק רכיבים > 0]\n"
        "📊 נקודות מצטברות: Y\n"
        "📊 שווי נקודות: Z ₪\n"
        "הצג רק רכיבים עם ערך גדול מאפס. ללא מלל מיותר."
    )

    return invoke_llm(llm, prompt)

# -------------------------------------------------------
# פונקציה ראשית
# -------------------------------------------------------

def explain_tax(employee_data: dict, question: str) -> str:
    print(f"\n{'='*50}")
    print(f"[TAX AGENT] התחלה")
    print(f"[TAX AGENT] שאלה: {question}")
    print(f"[TAX AGENT] מפתחות employee_data: {list(employee_data.keys())}")
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

    tax_data = load_tax_data()
    if not tax_data:
        return f"❌ לא נמצא קובץ {TAX_DATA_FILE}. יש להוסיפו לתיקיית knowledge."

    # שלב 1
    try:
        identification = identify_tax_symbols(question, llm)
        symbols = identification.get("symbols", ["91430", "91434", "91435", "91436", "91400", "91410", "91003"])
        time_scope = identification.get("time_scope", "year_to_date")
    except Exception as e:
        print(f"[שלב 1] ❌ נפל: {e}")
        traceback.print_exc()
        raise

    # שלב 2
    try:
        fetched_data = fetch_tax_data(symbols, employee_data, time_scope)
    except Exception as e:
        print(f"[שלב 2] ❌ נפל: {e}")
        traceback.print_exc()
        raise

    # שלב 3
    try:
        calc_result = perform_tax_calculation(fetched_data, tax_data)
        print(f"[TAX AGENT] ✅ חישוב הושלם: מס={calc_result['מס_מחושב']} | בפועל={calc_result['ניכוי_בפועל']}")
    except Exception as e:
        print(f"[שלב 3] ❌ נפל: {e}")
        traceback.print_exc()
        raise

    # שלב 4
    try:
        result = explain_tax_calculation(question, calc_result, llm)
        print(f"[TAX AGENT] ✅ הסבר הושלם")
        return result
    except Exception as e:
        print(f"[שלב 4] ❌ נפל: {e}")
        traceback.print_exc()
        raise
