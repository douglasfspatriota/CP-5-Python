"""
Conexão com o MongoDB e criação dos índices.

Os índices únicos são o que garante que o crawler NÃO cria registros
duplicados: rodar a coleta de novo atualiza o documento existente
(upsert) em vez de inserir outro igual.
"""
from functools import lru_cache

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

import config

# Nomes das coleções
CLASSIFICACOES = "classificacoes"
ARTILHEIROS = "artilheiros"
TEMPORADAS = "temporadas"
EXECUCOES = "execucoes"


@lru_cache
def obter_cliente() -> MongoClient:
    return MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)


def obter_banco(db: Database | None = None) -> Database:
    return db if db is not None else obter_cliente()[config.MONGO_DB]


def criar_indices(db: Database) -> None:
    # Chaves únicas (evitam duplicidade)
    db[CLASSIFICACOES].create_index(
        [("liga", ASCENDING), ("temporada", ASCENDING), ("time", ASCENDING)],
        unique=True, name="uniq_liga_temporada_time")
    db[ARTILHEIROS].create_index(
        [("liga", ASCENDING), ("temporada", ASCENDING), ("jogador", ASCENDING)],
        unique=True, name="uniq_liga_temporada_jogador")
    db[TEMPORADAS].create_index(
        [("liga", ASCENDING), ("temporada", ASCENDING)],
        unique=True, name="uniq_liga_temporada")

    # Índices de apoio às consultas da API
    db[CLASSIFICACOES].create_index([("time_busca", ASCENDING)], name="idx_time_busca")
    db[CLASSIFICACOES].create_index([("ano_inicio", DESCENDING), ("posicao", ASCENDING)], name="idx_ano_posicao")
    db[ARTILHEIROS].create_index([("gols", DESCENDING)], name="idx_gols")
    db[EXECUCOES].create_index([("inicio", DESCENDING)], name="idx_inicio")
