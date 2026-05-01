import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

app = FastAPI(
    title       = "Salary Explainer Agent",
    description = "סוכן AI לפענוח תלושי שכר — עובדי מדינה ישראל",
    version     = "1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins  = ["*"],
    allow_methods  = ["*"],
    allow_headers  = ["*"],
)


class ExplainRequest(BaseModel):
    employeeData:   dict
    semel_target:   int
    free_question:  str = ""   # שאלה חופשית מהצ'אט


class ExplainResponse(BaseModel):
    explanation: str
    semel:       int
    semel_name:  str


@app.get("/")
def root():
    return {"status": "✅ Salary Agent פעיל", "version": "1.0.0"}


@app.get("/health")
def health():
    import httpx
    from tools import _get_collection

    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_ok  = False
    chroma_ok  = False

    try:
        r = httpx.get(f"{ollama_url}/api/tags", timeout=5)
        ollama_ok = r.status_code == 200
    except Exception:
        pass

    try:
        col = _get_collection()
        chroma_ok = col is not None
    except Exception:
        pass

    return {
        "ollama":   "✅ פעיל" if ollama_ok  else "❌ לא נגיש",
        "chromadb": "✅ פעיל" if chroma_ok  else "❌ לא נגיש",
        "status":   "ok"      if (ollama_ok and chroma_ok) else "degraded",
    }


@app.post("/symbol-explain", response_model=ExplainResponse)
def symbol_explain(request: ExplainRequest):
    from orchestrator import route_and_explain

    # שם הסמל
    semel_name = ""
    elements   = request.employeeData.get("elements", {})
    semel_key  = str(request.semel_target)
    if semel_key in elements and elements[semel_key]:
        semel_name = elements[semel_key][0].get("shemSemel", "")

    try:
      explanation = route_and_explain(
            employee_data  = request.employeeData,
            semel_target   = request.semel_target,
            free_question  = request.free_question,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"שגיאה בסוכן: {e}")

    return ExplainResponse(
        explanation = explanation,
        semel       = request.semel_target,
        semel_name  = semel_name,
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
