"""
Aplicação FastAPI.

Para rodar:
    uvicorn api.main:app --reload

  * Documentação interativa: http://localhost:8000/docs
  * Dashboard:               http://localhost:8000/dashboard/
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.rotas import router

PASTA_DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard"

app = FastAPI(
    title="Futebol Dados API",
    description=(
        "API com classificações, artilheiros e estatísticas das 5 principais ligas "
        "europeias e do Brasileirão, coletados da Wikipédia por um web crawler.\n\n"
        "**Grupo:** Douglas Patriota (RM569713), Vitor Cintra (RM569416), Octavio Kal (RM571838), "
        "Pedro Brito (RM573187) e Guilherme Zeferino (RM572075)."
    ),
    version="1.0.0",
)

# Permite que o dashboard seja aberto de outra origem (ex.: Live Server do VS Code)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

app.include_router(router)


@app.get("/", include_in_schema=False)
def inicio():
    return RedirectResponse("/dashboard/")


@app.get("/api/saude", tags=["Coletas"], summary="Verifica se a API está no ar")
def saude():
    return {"status": "ok"}


# O dashboard é só HTML/CSS/JS estático; ele busca os dados nos endpoints /api/...
app.mount("/dashboard", StaticFiles(directory=PASTA_DASHBOARD, html=True), name="dashboard")
