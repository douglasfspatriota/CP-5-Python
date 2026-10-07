"""
Testes automatizados do projeto (não precisam de internet nem de MongoDB:
usam HTML de exemplo e o mongomock, um MongoDB simulado em memória).

Rodar:  python -m pytest -q
"""
from datetime import date

import mongomock
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.rotas import obter_db
from crawler import main as crawler_main
from crawler.parser import extrair_artilheiros, extrair_classificacao, para_inteiro, separar_marcadores
from crawler.wikipedia import PaginaNaoEncontrada, PaginaWiki
from tests.html_exemplo import gerar_pagina


def times_exemplo(n=20, jogos=None, prefixo="Clube", campeao=True):
    jogos = jogos if jogos is not None else 2 * (n - 1)
    lista = []
    for i in range(n):
        v = max(jogos - 8 - i * 1, 2) if i < n else 0
        v = min(v, jogos)
        e = min(5, jogos - v)
        d = jogos - v - e
        marc = "C" if (i == 0 and campeao) else ("R" if i >= n - 3 else "")
        lista.append((f"{prefixo} {chr(65 + i)}", v, e, d, 60 - i * 2, 20 + i, marc))
    return lista


ARTILHEIROS = [("Atacante Um", "Clube A", 27), ("Atacante Dois", "Clube B", 22),
               ("Atacante Três", "Clube C", 22), ("Atacante Quatro", "Clube A", 19)]


# ---------------------------------------------------------------- parser
def test_limpeza_basica():
    assert para_inteiro("+62") == 62
    assert para_inteiro("−13") == -13
    assert para_inteiro("91[a]") == 91
    assert separar_marcadores("Manchester City (C)") == ("Manchester City", ["C"])
    assert separar_marcadores("Bayern Munich (C, Q)") == ("Bayern Munich", ["C", "Q"])
    assert separar_marcadores("Paris Saint-Germain") == ("Paris Saint-Germain", [])


def test_extrai_classificacao_ignorando_outras_tabelas():
    html = gerar_pagina(times_exemplo(20), ARTILHEIROS)
    linhas = extrair_classificacao(html)
    assert len(linhas) == 20
    primeiro = linhas[0]
    assert primeiro["time"] == "Clube A"
    assert primeiro["marcadores"] == ["C"]
    assert primeiro["jogos"] == 38
    assert primeiro["pontos"] == 3 * primeiro["vitorias"] + primeiro["empates"]
    assert linhas[-1]["marcadores"] == ["R"]
    assert linhas[19]["saldo"] == linhas[19]["gols_pro"] - linhas[19]["gols_contra"]


def test_extrai_artilheiros_com_empate_rowspan():
    html = gerar_pagina(times_exemplo(20), ARTILHEIROS)
    art = extrair_artilheiros(html)
    assert [a["jogador"] for a in art] == ["Atacante Um", "Atacante Dois", "Atacante Três", "Atacante Quatro"]
    assert art[2]["gols"] == 22 and art[2]["posicao"] == 2  # herdou a célula com rowspan
    assert art[3]["posicao"] == 4
    assert art[0]["time"] == "Clube A"


# ---------------------------------------------------------------- crawler + banco
class ClienteFalso:
    """Substitui a Wikipédia: devolve HTML gerado localmente."""

    def __init__(self):
        self.chamadas = []

    def buscar_pagina(self, titulo):
        self.chamadas.append(titulo)
        if "2099" in titulo:
            raise PaginaNaoEncontrada(titulo)
        n = 18 if "Bundesliga" in titulo else 20
        em_andamento = titulo.startswith("2026")
        times = times_exemplo(n, jogos=10 if em_andamento else None,
                              prefixo=titulo.split()[-1], campeao=not em_andamento)
        artilheiros = ARTILHEIROS[1:] if getattr(self, "sem_primeiro", False) else ARTILHEIROS
        return PaginaWiki(titulo, 1, 123, gerar_pagina(times, artilheiros))


@pytest.fixture
def db():
    return mongomock.MongoClient()["teste"]


def test_titulos_de_pagina():
    from crawler.ligas import LIGAS
    assert LIGAS["premier-league"].titulo_pagina(2023) == "2023–24 Premier League"
    assert LIGAS["brasileirao"].titulo_pagina(2023) == "2023 Campeonato Brasileiro Série A"
    assert LIGAS["la-liga"].rotulo_temporada(1999) == "1999-2000"


def test_coleta_sem_duplicar_e_sem_apagar(db):
    cliente = ClienteFalso()
    exe1 = crawler_main.coletar(["premier-league", "bundesliga"], 2022, 2023, db=db, cliente=cliente)
    assert exe1["status"] == "concluida"
    assert db.classificacoes.count_documents({}) == 2 * 20 + 2 * 18
    doc = db.classificacoes.find_one({"liga": "premier-league", "temporada": "2023-24", "posicao": 1})
    primeira = doc["coleta"]["primeira_coleta"]
    assert doc["campeao"] is True and doc["coleta"]["total_coletas"] == 1
    assert doc["fonte"]["url"].startswith("https://en.wikipedia.org/wiki/")

    # Segunda coleta: mesmos dados -> nada duplicado, histórico preservado
    exe2 = crawler_main.coletar(["premier-league", "bundesliga"], 2022, 2023, db=db, cliente=cliente)
    assert db.classificacoes.count_documents({}) == 76
    assert db.artilheiros.count_documents({}) == 4 * 4
    assert db.temporadas.count_documents({}) == 4
    assert db.execucoes.count_documents({}) == 2
    doc2 = db.classificacoes.find_one({"_id": doc["_id"]})
    assert doc2["coleta"]["total_coletas"] == 2
    assert doc2["coleta"]["primeira_coleta"] == primeira
    assert doc2["coleta"]["ultima_coleta"] >= primeira
    assert exe2["totais"]["inseridos"] == 0


def test_temporada_atual_em_andamento(db):
    hoje = date(2026, 10, 7)
    from crawler.ligas import LIGAS
    assert LIGAS["premier-league"].temporada_atual(hoje) == 2026          # 2026-27 já começou
    assert LIGAS["premier-league"].temporada_atual(date(2026, 5, 1)) == 2025
    assert LIGAS["brasileirao"].temporada_atual(hoje) == 2026

    cliente = ClienteFalso()
    exe = crawler_main.coletar(["serie-a"], 2025, None, db=db, cliente=cliente, hoje=hoje)
    assert cliente.chamadas == ["2025\u201326 Serie A", "2026\u201327 Serie A"]
    assert exe["status"] == "concluida"
    resumo = db.temporadas.find_one({"liga": "serie-a", "temporada": "2026-27"})
    assert resumo["temporada_encerrada"] is False and resumo["campeao"] is None

    # Segunda coleta da temporada atual: o histórico guarda um retrato por coleta
    cliente.sem_primeiro = True  # o artilheiro 1 "saiu" do ranking
    crawler_main.coletar(["serie-a"], 2026, None, db=db, cliente=cliente, hoje=hoje)
    lider = db.classificacoes.find_one({"temporada": "2026-27", "posicao": 1})
    assert len(lider["historico"]) == 2 and {"pontos", "posicao", "jogos"} <= set(lider["historico"][0])
    encerrada = db.classificacoes.find_one({"temporada": "2025-26", "posicao": 1})
    assert "historico" not in encerrada
    fora = db.artilheiros.find_one({"temporada": "2026-27", "jogador": "Atacante Um"})
    assert fora is not None and fora["no_ranking_atual"] is False   # não foi apagado


def test_pagina_inexistente(db):
    exe = crawler_main.coletar(["serie-a"], 2099, 2099, db=db, cliente=ClienteFalso(), hoje=date(2100, 1, 1))
    assert exe["status"] == "falhou" and len(exe["erros"]) == 1


# ---------------------------------------------------------------- API
@pytest.fixture
def api(db):
    crawler_main.coletar(["premier-league", "brasileirao", "bundesliga"], 2021, 2024, db=db, cliente=ClienteFalso())
    crawler_main.coletar(["brasileirao"], 2026, None, db=db, cliente=ClienteFalso(), hoje=date(2026, 10, 7))
    app.dependency_overrides[obter_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_endpoints_listagem_detalhe_filtro(api):
    r = api.get("/api/classificacoes", params={"liga": "brasileirao", "por_pagina": 5})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["total"] == 100 and len(corpo["itens"]) == 5
    id_ = corpo["itens"][0]["id"]
    assert api.get(f"/api/classificacoes/{id_}").json()["id"] == id_
    assert api.get("/api/classificacoes/123").status_code == 404
    assert api.get("/api/classificacoes", params={"liga": "invalida"}).status_code == 422

    busca = api.get("/api/classificacoes", params={"busca": "LIGA A", "campeao": True}).json()
    assert busca["total"] >= 1 and all(i["campeao"] for i in busca["itens"])
    ordenado = api.get("/api/classificacoes", params={"ordenar": "-pontos", "por_pagina": 3}).json()["itens"]
    assert ordenado[0]["pontos"] >= ordenado[1]["pontos"] >= ordenado[2]["pontos"]

    assert len(api.get("/api/ligas").json()) == 3
    assert len(api.get("/api/temporadas", params={"liga": "bundesliga"}).json()) == 4
    times = api.get("/api/times", params={"busca": "bundesliga"}).json()
    assert times and api.get(f"/api/times/{times[0]}/historico").status_code == 200
    art = api.get("/api/artilheiros", params={"busca": "um"}).json()
    assert art["total"] >= 1


def test_endpoints_estatisticas(api):
    resumo = api.get("/api/estatisticas/resumo").json()
    assert resumo["total_registros"] == 20 * 4 + 20 * 5 + 18 * 4
    assert resumo["total_temporadas"] == 13 and resumo["media_gols_jogo"] > 0
    assert resumo["maior_campeao"]["titulos"] == 4
    assert resumo["ultima_coleta"] is not None
    assert len(api.get("/api/estatisticas/gols-por-jogo").json()) == 13
    atuais = api.get("/api/temporadas/em-andamento").json()
    assert [t["temporada"] for t in atuais] == ["2026"]
    assert api.get("/api/estatisticas/titulos", params={"limite": 2}).json()[0]["titulos"] == 4
    assert len(api.get("/api/estatisticas/disputa", params={"liga": "brasileirao"}).json()) == 5
    comp = api.get("/api/estatisticas/ligas").json()
    assert {c["liga"] for c in comp} == {"premier-league", "brasileirao", "bundesliga"}
    assert api.get("/api/execucoes").json()[0]["status"] == "concluida"


def test_dashboard_servido(api):
    r = api.get("/dashboard/")
    assert r.status_code == 200 and "<html" in r.text.lower()
