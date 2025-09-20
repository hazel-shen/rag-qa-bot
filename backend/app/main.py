from fastapi import FastAPI

app = FastAPI(title="RAG-QA-BOT API")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def root():
    return {"message": "hello from rag-qa-bot"}
