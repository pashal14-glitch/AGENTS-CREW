"""
orchestrator.py
---------------
מנהל הסוכנים — מזהה נושא השאלה ומנתב לסוכן המתאים.

סוכנים:
  salary → agent.py       (שכר, מענקים, ברוטו)
  tax    → agent_tax.py   (מס הכנסה, נקודות זיכוי)
  bituach → עתידי         (ביטוח לאומי)
  gilum   → עתידי         (גילומים)
"""

import os
import json
import re
from dotenv import load_dotenv

load_dotenv()


def invoke_llm(llm, prompt: str) -> str:
    result = llm.invoke(prompt)
    if hasattr(result, "content"):
        return result.content
    return str(result)


def identify_agent(question: str, llm) -> list:
    """
    LLM מזהה לאיזה סוכן לנתב.
    מחזיר רשימת סוכנים (לפעמים יותר מאחד — כמו גילום).
    """
    prompt = (
        "זהה את נושא השאלה הבאה ובחר סוכנים מתאימים.\n\n"
        "סוכנים זמינים:\n"
        "- salary: שכר, מענקים, ברוטו פנסיה, ותק, הבראה, ביגוד, טופס 161\n"
        "- tax: מס הכנסה, נקודות זיכוי, ניכוי מס, מדרגות מס\n"
        "- bituach: ביטוח לאומי, מס בריאות (עתידי)\n"
        "- gilum: גילום, נטו מגולם (עתידי)\n\n"
        "החזר JSON בלבד:\n"
        "{\"agents\": [\"salary\"]}\n\n"
        "הערות:\n"
        "- גילום דורש שניים: [\"tax\", \"bituach\"]\n"
        "- אם לא ברור — החזר [\"salary\"]\n\n"
        "שאלה: " + question
    )

    result = invoke_llm(llm, prompt)
    result = re.sub(r'```json\s*', '', result)
    result = re.sub(r'```\s*', '', result)
    match = re.search(r'\{.*\}', result, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return data.get("agents", ["salary"])
        except Exception:
            pass

    return ["salary"]


def route_and_explain(employee_data: dict, semel_target: int, free_question: str) -> str:
    """
    נקודת הכניסה הראשית — מנתב לסוכן המתאים.
    """
    from langchain_anthropic import ChatAnthropic

    llm = ChatAnthropic(
        model       = "claude-sonnet-4-5",
        temperature = 0,
        max_tokens  = 512,
        api_key     = os.getenv("ANTHROPIC_API_KEY")
    )

    # קביעת השאלה
    question = free_question if free_question else f"כיצד מחושב סמל {semel_target}"
    print(f"\n🎯 Orchestrator: {question}")

    # זיהוי סוכן
    agents = identify_agent(question, llm)
    print(f"   נתב ל: {agents}")

    results = []

    for agent_name in agents:

        if agent_name == "salary":
            from agent import explain_symbol
            result = explain_symbol(employee_data, semel_target, free_question)
            results.append(result)

        elif agent_name == "tax":
            from agent_tax import explain_tax
            result = explain_tax(employee_data, question)
            results.append(result)

        elif agent_name == "bituach":
            results.append("⚠️ סוכן ביטוח לאומי — בפיתוח")

        elif agent_name == "gilum":
            results.append("⚠️ סוכן גילומים — בפיתוח")

    # איחוד תשובות אם יש יותר מסוכן אחד
    if len(results) == 1:
        return results[0]

    return "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n".join(results)
