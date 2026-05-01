#!/bin/bash
# ======================================================
# start.sh — סקריפט הפעלה מלא ב-RunPod
# הרץ אחת: bash start.sh
# ======================================================

echo "🚀 מתחיל Salary Agent..."

# --- 1. התקנת/טעינת Ollama מה-Volume ---
if [ ! -f "/workspace/ollama_bin" ]; then
    echo "⬇️ מתקין Ollama..."
    apt-get update && apt-get install zstd -y
    curl -fsSL https://ollama.ai/install.sh | sh
    cp /usr/local/bin/ollama /workspace/ollama_bin
    echo "✅ Ollama הותקן ונשמר ב-Volume"
else
    echo "✅ Ollama קיים ב-Volume — מעתיק..."
    cp /workspace/ollama_bin /usr/local/bin/ollama
    chmod +x /usr/local/bin/ollama
fi
# --- 2. הפעלת Ollama ברקע ---
echo "▶ מפעיל Ollama..."
export OLLAMA_MODELS=/workspace/ollama_models
nohup ollama serve > /workspace/ollama.log 2>&1 &
sleep 5
echo "✅ Ollama פועל"

# --- 3. הורדת המודל אם לא קיים ---
echo "▶ בודק מודל aya-expanse:32b..."
if ! OLLAMA_MODELS=/workspace/ollama_models ollama list | grep -q "aya-expanse:32b"; then
    echo "  ⬇️  מוריד aya-expanse:32b (עשוי לקחת זמן)..."
    OLLAMA_MODELS=/workspace/ollama_models ollama pull aya-expanse:32b
    echo "  ✅ המודל הורד"
else
    echo "  ✅ המודל כבר קיים"
fi

# --- 4. התקנת תלויות Python ---
echo "▶ מתקין תלויות Python..."
cd /workspace/salary_agent
pip install -r requirements.txt -q
echo "✅ תלויות מותקנות"

# --- 5. בניית אינדקס ChromaDB (אם לא קיים) ---
if [ ! -d "/workspace/salary_agent/chroma_db" ]; then
    echo "▶ בונה אינדקס ChromaDB..."
    python indexer.py
    echo "✅ אינדקס מוכן"
else
    echo "✅ אינדקס ChromaDB כבר קיים"
fi

# --- 6. הפעלת FastAPI ---
echo "▶ מפעיל FastAPI על פורט 8000..."
echo "✅ הכל מוכן — השרת עולה!"
uvicorn main:app --host 0.0.0.0 --port 8000