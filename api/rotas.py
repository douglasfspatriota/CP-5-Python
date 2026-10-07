"""
Endpoints da API. Todos os dados vêm do MongoDB através do módulo
database.repositorio; a API nunca acessa a Wikipédia.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.database import Database

from crawler.ligas import LIGAS
from database import repositorio as repo
from database.conexao import ARTILHEIROS, CLASSIFICACOES, TEMPORADAS, obter_banco

router = APIRouter(prefix="/api")

SlugLiga = Literal[tuple(LIGAS)]  # type: ignore[valid-type]


def obter_db() -> Database:
    return obter_banco()


def _ou_404(doc, oque: str):
    if doc is None:
        raise HTTPException(status_code=404, detail=f"{oque} não encontrado(a)")
    return doc


# ---------------------------------------------------------------- Ligas / temporadas
@router.get("/ligas", tags=["Ligas e temporadas"], summary="Lista as ligas coletadas")
def ligas(db: Database = Depends(obter_db)):
    return repo.listar_ligas(db)


@router.get("/temporadas", tags=["Ligas e temporadas"],
            summary="Resumo de cada temporada (campeão, vice, gols, artilheiro...)")
def temporadas(liga: SlugLiga | None = None, db: Database = Depends(obter_db)):
    return repo.listar_temporadas(db, liga)


@router.get("/temporadas/em-andamento", tags=["Ligas e temporadas"],
            summary="Temporadas atuais, ainda sem campeão (líder, vice, gols até agora)")
def temporadas_atuais(db: Database = Depends(obter_db)):
    return repo.temporadas_em_andamento(db)


@router.get("/temporadas/{id}", tags=["Ligas e temporadas"], summary="Detalhe de uma temporada")
def temporada(id: str, db: Database = Depends(obter_db)):
    return _ou_404(repo.buscar_por_id(db, TEMPORADAS, id), "Temporada")


# ---------------------------------------------------------------- Classificações
@router.get("/classificacoes", tags=["Classificações"],
            summary="Lista registros (um time em uma temporada) com filtros e paginação")
def classificacoes(
    liga: SlugLiga | None = Query(None, description="Slug da liga, ex.: brasileirao"),
    temporada: str | None = Query(None, description="Ex.: 2023-24 (Europa) ou 2023 (Brasil)"),
    busca: str | None = Query(None, description="Parte do nome do time (sem diferenciar acentos)"),
    campeao: bool | None = Query(None, description="true = só campeões"),
    rebaixado: bool | None = Query(None, description="true = só rebaixados"),
    ordenar: str | None = Query(None, description="Campo de ordenação; prefixo '-' = decrescente. Ex.: -pontos"),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=200),
    db: Database = Depends(obter_db),
):
    return repo.listar_classificacoes(db, liga, temporada, busca, campeao, rebaixado,
                                      ordenar, pagina, por_pagina)


@router.get("/classificacoes/{id}", tags=["Classificações"], summary="Consulta um registro específico")
def classificacao(id: str, db: Database = Depends(obter_db)):
    return _ou_404(repo.buscar_por_id(db, CLASSIFICACOES, id), "Registro")


# ---------------------------------------------------------------- Times
@router.get("/times", tags=["Times"], summary="Lista os nomes dos times (com busca)")
def times(liga: SlugLiga | None = None, busca: str | None = None, db: Database = Depends(obter_db)):
    return repo.listar_times(db, liga, busca)


@router.get("/times/{nome}/historico", tags=["Times"],
            summary="Posição e pontos de um time em todas as temporadas coletadas")
def historico(nome: str, db: Database = Depends(obter_db)):
    dados = repo.historico_time(db, nome)
    if not dados:
        raise HTTPException(status_code=404, detail="Time não encontrado")
    return dados


# ---------------------------------------------------------------- Artilheiros
@router.get("/artilheiros", tags=["Artilheiros"], summary="Lista artilheiros com filtros")
def artilheiros(
    liga: SlugLiga | None = None,
    temporada: str | None = None,
    busca: str | None = Query(None, description="Nome do jogador ou do clube"),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=200),
    db: Database = Depends(obter_db),
):
    return repo.listar_artilheiros(db, liga, temporada, busca, pagina, por_pagina)


@router.get("/artilheiros/{id}", tags=["Artilheiros"], summary="Consulta um artilheiro específico")
def artilheiro(id: str, db: Database = Depends(obter_db)):
    return _ou_404(repo.buscar_por_id(db, ARTILHEIROS, id), "Artilheiro")


# ---------------------------------------------------------------- Estatísticas
@router.get("/estatisticas/resumo", tags=["Estatísticas"],
            summary="Indicadores gerais (totais, médias, recordes, última coleta)")
def resumo(liga: SlugLiga | None = None, db: Database = Depends(obter_db)):
    return repo.resumo_geral(db, liga)


@router.get("/estatisticas/gols-por-jogo", tags=["Estatísticas"],
            summary="Média de gols por partida em cada temporada")
def gols_por_jogo(liga: SlugLiga | None = None, db: Database = Depends(obter_db)):
    return repo.gols_por_jogo(db, liga)


@router.get("/estatisticas/titulos", tags=["Estatísticas"], summary="Clubes com mais títulos")
def titulos(liga: SlugLiga | None = None, limite: int = Query(10, ge=1, le=50),
            db: Database = Depends(obter_db)):
    return repo.titulos_por_clube(db, liga, limite)


@router.get("/estatisticas/disputa", tags=["Estatísticas"],
            summary="Diferença de pontos entre 1º e 2º colocados por temporada")
def disputa(liga: SlugLiga | None = None, db: Database = Depends(obter_db)):
    return repo.disputa_titulo(db, liga)


@router.get("/estatisticas/ligas", tags=["Estatísticas"], summary="Comparativo entre as ligas")
def comparativo(db: Database = Depends(obter_db)):
    return repo.comparativo_ligas(db)


# ---------------------------------------------------------------- Coletas
@router.get("/execucoes", tags=["Coletas"], summary="Histórico de execuções do crawler")
def execucoes(limite: int = Query(20, ge=1, le=100), db: Database = Depends(obter_db)):
    return repo.listar_execucoes(db, limite)
