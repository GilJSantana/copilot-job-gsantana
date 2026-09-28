"""Ponto de entrada: `uv run main.py` (ou `uv run uvicorn main:app --reload`)."""

import uvicorn

from app.web.app import create_app

app = create_app()

if __name__ == "__main__":
    # 127.0.0.1: a aplicação é pessoal e não tem autenticação — não expor na rede
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
