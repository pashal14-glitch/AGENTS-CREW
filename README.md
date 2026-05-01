# Salary Explainer Agent 🏛️

סוכן AI לפענוח תלושי שכר של עובדי מדינה ישראל.

---

## מבנה הפרויקט

```
salary_agent/
├── main.py          ← שרת FastAPI
├── agent.py         ← Orchestrator (LangChain + Ollama)
├── tools.py         ← כלי חיפוש סמנטי (ChromaDB)
├── indexer.py       ← טעינת קבצי knowledge לאינדקס
├── start.sh         ← סקריפט הפעלה ב-RunPod
├── requirements.txt
├── .env             ← הגדרות סביבה
├── knowledge/       ← קבצי תקשי"ר, תכ"ם, פרומפט (MD + DOCX)
└── chroma_db/       ← נוצר אוטומטית
```

---

## הפעלה ב-RunPod

### שלב 1 — הכנת הפוד
```
GPU:              A40
Container disk:   20GB
Volume disk:      50GB
Expose HTTP ports: 8888, 11434, 8000
```

### שלב 2 — העלאת הקוד ל-/workspace
דרך Jupyter (פורט 8888) — גרור את תיקיית `salary_agent` ל-`/workspace/`.

### שלב 3 — העלאת קבצי knowledge
```bash
# העתק את תיקיית knowledge לתוך salary_agent
cp -r /path/to/knowledge /workspace/salary_agent/knowledge
```

### שלב 4 — הרצה
```bash
cd /workspace/salary_agent
bash start.sh
```

זהו. הסקריפט עושה הכל אוטומטית:
- מפעיל Ollama
- מוריד Aya B32 (אם לא קיים)
- מתקין תלויות Python
- בונה אינדקס ChromaDB
- מפעיל FastAPI

---

## בדיקת תקינות

פתחי בדפדפן:
```
http://[RUNPOD-URL]:8000/health
```

תשובה תקינה:
```json
{
  "ollama":  "✅ פעיל",
  "chromadb":"✅ פעיל",
  "status":  "ok"
}
```

---

## שינויים נדרשים ב-HesberBeKlik.html

כדי לשלוח בקשה לסוכן, יש להוסיף לקוד ה-JavaScript:

```javascript
async function askAgent(semelTarget) {
    const AGENT_URL = "http://[RUNPOD-URL]:8000/symbol-explain";
    
    const response = await fetch(AGENT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            employeeData: employeeData,   // האובייקט הקיים
            semel_target: semelTarget
        })
    });
    
    const data = await response.json();
    return data.explanation;
}
```

---

## עדכון כתובת RunPod ב-.env

בכל פעם שפותחים פוד חדש — הכתובת משתנה.
עדכני בקובץ `.env`:
```
OLLAMA_BASE_URL=http://localhost:11434
```
(בתוך הפוד זה תמיד localhost — לא צריך לשנות)

---

## מעבר למחשב חזק (עתידי)

1. התקני Ollama: https://ollama.ai
2. הורידי את המודל: `ollama pull aya:32b`
3. הריצי: `python indexer.py` ואז `uvicorn main:app --host 0.0.0.0 --port 8000`
4. עדכני ב-.env: `OLLAMA_BASE_URL=http://localhost:11434`
5. הכל עובד אופליין ✅
