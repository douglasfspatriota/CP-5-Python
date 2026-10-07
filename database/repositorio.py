"""
Camada de persistência: toda leitura e escrita no MongoDB passa por aqui.

  * Escrita (usada pelo crawler): upsert por chave única -> sem duplicatas
    e sem apagar coletas anteriores.
  * Leitura (usada pela API): listagens, filtros e agregações estatísticas.
"""
import re
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.database import Database

from database.conexao import ARTILHEIROS, CLASSIFICACOES, EXECUCOES, TEMPORADAS
from utils import normalizar_busca


def agora() -> datetime:
    return datetime.now(timezone.utc)


# ===========================================================================
# ESCRITA
# ===========================================================================
def salvar_documentos(db: Database, colecao: str, documentos: list[dict],
                      chave: tuple[str, ...], execucao_id: ObjectId,
                      campos_historico: tuple[str, ...] | None = None) -> dict:
    """
    Grava cada documento com upsert:
      - se ainda não existe -> insere e registra 'primeira_coleta';
      - se já existe        -> atualiza os dados e 'ultima_coleta'.
    Assim, nada é apagado e não surgem registros repetidos.

    campos_historico: usado na temporada em andamento. A cada coleta, os campos
    indicados são acrescentados à lista 'historico' do documento, preservando
    os valores de coletas anteriores (ex.: pontos do time em cada rodada coletada).
    """
    if not documentos:
        return {"inseridos": 0, "atualizados": 0}
    momento = agora()
    inseridos = 0
    for doc in documentos:
        filtro = {campo: doc[campo] for campo in chave}
        operacao = {
            "$set": {**doc, "coleta.ultima_coleta": momento, "coleta.execucao_id": execucao_id},
            "$setOnInsert": {"coleta.primeira_coleta": momento},
            "$inc": {"coleta.total_coletas": 1},
        }
        if campos_historico:
            retrato = {campo: doc.get(campo) for campo in campos_historico}
            operacao["$push"] = {"historico": {"coletado_em": momento, **retrato}}
        resultado = db[colecao].update_one(filtro, operacao, upsert=True)
        if resultado.upserted_id is not None:
            inseridos += 1
    return {"inseridos": inseridos, "atualizados": len(documentos) - inseridos}


def marcar_fora_do_ranking(db: Database, liga: str, temporada: str, jogadores: list[str]) -> None:
    """
    Numa temporada em andamento, um jogador pode sair do top 20 de uma coleta
    para outra. Em vez de apagar o registro dele, marcamos que ele não está no
    ranking atual; a API mostra só quem está no ranking atual.
    """
    if not jogadores:
        return
    db[ARTILHEIROS].update_many({"liga": liga, "temporada": temporada, "jogador": {"$nin": jogadores}},
                                {"$set": {"no_ranking_atual": False}})
    db[ARTILHEIROS].update_many({"liga": liga, "temporada": temporada, "jogador": {"$in": jogadores}},
                                {"$set": {"no_ranking_atual": True}})


def iniciar_execucao(db: Database, parametros: dict) -> ObjectId:
    return db[EXECUCOES].insert_one({
        "inicio": agora(), "fim": None, "status": "em_andamento",
        "parametros": parametros, "paginas": [], "erros": [],
        "totais": {"paginas_ok": 0, "inseridos": 0, "atualizados": 0},
    }).inserted_id


def registrar_pagina(db: Database, execucao_id: ObjectId, info: dict) -> None:
    db[EXECUCOES].update_one({"_id": execucao_id}, {
        "$push": {"paginas": info},
        "$inc": {"totais.paginas_ok": 1,
                 "totais.inseridos": info.get("inseridos", 0),
                 "totais.atualizados": info.get("atualizados", 0)},
    })


def registrar_erro(db: Database, execucao_id: ObjectId, info: dict) -> None:
    db[EXECUCOES].update_one({"_id": execucao_id}, {"$push": {"erros": info}})


def finalizar_execucao(db: Database, execucao_id: ObjectId) -> dict:
    exe = db[EXECUCOES].find_one({"_id": execucao_id})
    status = "concluida" if not exe["erros"] else ("parcial" if exe["paginas"] else "falhou")
    db[EXECUCOES].update_one({"_id": execucao_id}, {"$set": {"fim": agora(), "status": status}})
    return db[EXECUCOES].find_one({"_id": execucao_id})


# ===========================================================================
# LEITURA
# ===========================================================================
def serializar(doc: dict | None) -> dict | None:
    """Converte ObjectId em texto para que o documento vire JSON."""
    if doc is None:
        return None
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    if isinstance(doc.get("coleta"), dict) and isinstance(doc["coleta"].get("execucao_id"), ObjectId):
        doc["coleta"] = {**doc["coleta"], "execucao_id": str(doc["coleta"]["execucao_id"])}
    return doc


def _busca_regex(texto: str) -> dict:
    return {"$regex": re.escape(normalizar_busca(texto))}


def buscar_por_id(db: Database, colecao: str, id_: str) -> dict | None:
    try:
        oid = ObjectId(id_)
    except (InvalidId, TypeError):
        return None
    return serializar(db[colecao].find_one({"_id": oid}))


def _paginar(db, colecao, filtro, ordem, pagina, por_pagina) -> dict:
    total = db[colecao].count_documents(filtro)
    cursor = (db[colecao].find(filtro).sort(ordem)
              .skip((pagina - 1) * por_pagina).limit(por_pagina))
    return {
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total_paginas": max(1, -(-total // por_pagina)),
        "itens": [serializar(d) for d in cursor],
    }


CAMPOS_ORDENAVEIS = {"posicao", "pontos", "time", "ano_inicio", "gols_pro", "gols_contra",
                     "saldo", "aproveitamento", "vitorias", "temporada", "liga"}


def _ordem(ordenar: str | None, padrao: list[tuple[str, int]]) -> list[tuple[str, int]]:
    if not ordenar:
        return padrao
    campo, direcao = (ordenar[1:], -1) if ordenar.startswith("-") else (ordenar, 1)
    if campo not in CAMPOS_ORDENAVEIS:
        return padrao
    return [(campo, direcao)] + [p for p in padrao if p[0] != campo]


def listar_classificacoes(db: Database, liga=None, temporada=None, busca=None,
                          campeao=None, rebaixado=None, ordenar=None,
                          pagina=1, por_pagina=20) -> dict:
    filtro: dict = {}
    if liga:
        filtro["liga"] = liga
    if temporada:
        filtro["temporada"] = temporada
    if busca:
        filtro["time_busca"] = _busca_regex(busca)
    if campeao is not None:
        filtro["campeao"] = campeao
    if rebaixado is not None:
        filtro["rebaixado"] = rebaixado
    padrao = [("ano_inicio", -1), ("liga", 1), ("posicao", 1)]
    return _paginar(db, CLASSIFICACOES, filtro, _ordem(ordenar, padrao), pagina, por_pagina)


def listar_artilheiros(db: Database, liga=None, temporada=None, busca=None,
                       pagina=1, por_pagina=20) -> dict:
    filtro: dict = {"no_ranking_atual": {"$ne": False}}
    if liga:
        filtro["liga"] = liga
    if temporada:
        filtro["temporada"] = temporada
    if busca:
        filtro["$or"] = [{"jogador_busca": _busca_regex(busca)},
                         {"time": {"$regex": re.escape(busca), "$options": "i"}}]
    ordem = [("gols", -1), ("ano_inicio", -1), ("jogador", 1)]
    return _paginar(db, ARTILHEIROS, filtro, ordem, pagina, por_pagina)


def listar_temporadas(db: Database, liga=None) -> list[dict]:
    filtro = {"liga": liga} if liga else {}
    cursor = db[TEMPORADAS].find(filtro).sort([("ano_inicio", -1), ("liga", 1)])
    return [serializar(d) for d in cursor]


def listar_ligas(db: Database) -> list[dict]:
    pipeline = [
        {"$group": {"_id": "$liga", "nome": {"$first": "$liga_nome"}, "pais": {"$first": "$pais"},
                    "temporadas": {"$sum": 1}, "primeira": {"$min": "$ano_inicio"},
                    "ultima": {"$max": "$ano_inicio"}}},
        {"$sort": {"_id": 1}},
    ]
    return [{"slug": d["_id"], "nome": d["nome"], "pais": d["pais"],
             "temporadas": d["temporadas"], "primeira_temporada": d["primeira"],
             "ultima_temporada": d["ultima"]}
            for d in db[TEMPORADAS].aggregate(pipeline)]


def listar_times(db: Database, liga=None, busca=None) -> list[str]:
    filtro: dict = {}
    if liga:
        filtro["liga"] = liga
    if busca:
        filtro["time_busca"] = _busca_regex(busca)
    return sorted(db[CLASSIFICACOES].distinct("time", filtro))


def historico_time(db: Database, time: str) -> list[dict]:
    cursor = db[CLASSIFICACOES].find({"time": time}).sort("ano_inicio", 1)
    return [serializar(d) for d in cursor]


# ---------------------------------------------------------------------------
# Estatísticas (agregações)
# ---------------------------------------------------------------------------
def resumo_geral(db: Database, liga=None) -> dict:
    filtro = {"liga": liga} if liga else {}
    temporadas = list(db[TEMPORADAS].find(filtro))
    partidas = sum(t["partidas"] for t in temporadas)
    gols = sum(t["total_gols"] for t in temporadas)

    maior_campeao = next(iter(titulos_por_clube(db, liga, limite=1)), None)
    recorde = db[TEMPORADAS].find_one({**filtro, "campeao": {"$ne": None}},
                                      sort=[("pontos_campeao", -1)])
    recorde_aprov = db[TEMPORADAS].find_one({**filtro, "campeao": {"$ne": None}},
                                            sort=[("aproveitamento_campeao", -1)])
    ultima = db[EXECUCOES].find_one({"status": {"$in": ["concluida", "parcial"]}}, sort=[("fim", -1)])
    return {
        "total_registros": db[CLASSIFICACOES].count_documents(filtro),
        "total_artilheiros": db[ARTILHEIROS].count_documents(filtro),
        "total_temporadas": len(temporadas),
        "total_ligas": len({t["liga"] for t in temporadas}),
        "total_times": len(db[CLASSIFICACOES].distinct("time", filtro)),
        "total_partidas": partidas,
        "total_gols": gols,
        "media_gols_jogo": round(gols / partidas, 2) if partidas else 0,
        "campeoes_diferentes": len({t["campeao"] for t in temporadas if t.get("campeao")}),
        "maior_campeao": maior_campeao,
        "recorde_pontos": None if not recorde else {
            "time": recorde["campeao"], "pontos": recorde["pontos_campeao"],
            "liga": recorde["liga_nome"], "temporada": recorde["temporada"]},
        "recorde_aproveitamento": None if not recorde_aprov else {
            "time": recorde_aprov["campeao"], "aproveitamento": recorde_aprov["aproveitamento_campeao"],
            "liga": recorde_aprov["liga_nome"], "temporada": recorde_aprov["temporada"]},
        "ultima_coleta": ultima["fim"] if ultima else None,
    }


def gols_por_jogo(db: Database, liga=None) -> list[dict]:
    """Média de gols por partida em cada temporada, por liga (gráfico de linhas)."""
    filtro = {"liga": liga} if liga else {}
    projecao = {"_id": 0, "liga": 1, "liga_nome": 1, "temporada": 1, "ano_inicio": 1,
                "media_gols_jogo": 1, "partidas": 1, "total_gols": 1, "temporada_encerrada": 1,
                "campeao": 1}
    return list(db[TEMPORADAS].find(filtro, projecao).sort([("ano_inicio", 1), ("liga", 1)]))


def titulos_por_clube(db: Database, liga=None, limite: int = 10) -> list[dict]:
    """Ranking de clubes com mais títulos (agregação $group no MongoDB)."""
    match: dict = {"campeao": {"$ne": None}}
    if liga:
        match["liga"] = liga
    pipeline = [
        {"$match": match},
        {"$sort": {"ano_inicio": 1}},
        {"$group": {"_id": {"time": "$campeao", "liga": "$liga_nome"},
                    "titulos": {"$sum": 1}, "temporadas": {"$push": "$temporada"}}},
        {"$sort": {"titulos": -1, "_id.time": 1}},
        {"$limit": limite},
    ]
    return [{"time": d["_id"]["time"], "liga": d["_id"]["liga"],
             "titulos": d["titulos"], "temporadas": d["temporadas"]}
            for d in db[TEMPORADAS].aggregate(pipeline)]


def disputa_titulo(db: Database, liga=None) -> list[dict]:
    """Diferença de pontos entre 1º e 2º colocados (quanto menor, mais disputado)."""
    filtro = {"liga": liga} if liga else {}
    projecao = {"_id": 0, "liga": 1, "liga_nome": 1, "temporada": 1, "ano_inicio": 1,
                "lider": 1, "vice": 1, "diferenca_lider_vice": 1, "temporada_encerrada": 1, "campeao": 1}
    return list(db[TEMPORADAS].find(filtro, projecao).sort([("ano_inicio", 1), ("liga", 1)]))


def comparativo_ligas(db: Database) -> list[dict]:
    """Uma linha por liga com médias das temporadas já concluídas (com campeão)."""
    pipeline = [
        {"$match": {"campeao": {"$ne": None}}},
        {"$group": {
            "_id": "$liga",
            "liga_nome": {"$first": "$liga_nome"},
            "temporadas": {"$sum": 1},
            "media_gols_jogo": {"$avg": "$media_gols_jogo"},
            "media_pontos_campeao": {"$avg": "$pontos_campeao"},
            "media_diferenca_lider_vice": {"$avg": "$diferenca_lider_vice"},
            "campeoes": {"$addToSet": "$campeao"},
        }},
        {"$sort": {"_id": 1}},
    ]
    saida = []
    for d in db[TEMPORADAS].aggregate(pipeline):
        campeoes = sorted(c for c in d["campeoes"] if c)
        saida.append({
            "liga": d["_id"], "liga_nome": d["liga_nome"], "temporadas": d["temporadas"],
            "media_gols_jogo": round(d["media_gols_jogo"] or 0, 2),
            "media_pontos_campeao": round(d["media_pontos_campeao"] or 0, 1),
            "media_diferenca_lider_vice": round(d["media_diferenca_lider_vice"] or 0, 1),
            "campeoes_diferentes": len(campeoes),
            "campeoes": campeoes,
        })
    return saida


def temporadas_em_andamento(db: Database) -> list[dict]:
    """Temporadas ainda sem campeão definido (a temporada atual de cada liga)."""
    cursor = db[TEMPORADAS].find({"campeao": None}).sort([("liga", 1)])
    return [serializar(d) for d in cursor]


def listar_execucoes(db: Database, limite: int = 20) -> list[dict]:
    cursor = db[EXECUCOES].find({}, {"paginas": 0}).sort("inicio", -1).limit(limite)
    return [serializar(d) for d in cursor]
