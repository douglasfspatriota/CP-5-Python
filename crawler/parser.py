"""
Extração e tratamento dos dados a partir do HTML das páginas da Wikipédia.

A página de cada temporada traz duas tabelas que interessam ao projeto:
  1. a tabela de classificação ("League table"):
       Pos | Team | Pld | W | D | L | GF | GA | GD | Pts | Qualification...
  2. a tabela de artilheiros ("Top scorers"):
       Rank | Player | Club | Goals

Em vez de depender da posição exata da tabela na página (que muda de uma
temporada para outra), o parser procura entre todas as tabelas "wikitable"
aquela cujo cabeçalho tem as colunas esperadas.
"""
import re
import unicodedata

from bs4 import BeautifulSoup, Tag

# Sinônimos de cabeçalho -> nome padronizado da coluna
COLUNAS_CLASSIFICACAO = {
    "pos": "posicao", "position": "posicao", "#": "posicao", "rank": "posicao",
    "team": "time", "club": "time", "teams": "time",
    "pld": "jogos", "p": "jogos", "played": "jogos", "mp": "jogos", "gp": "jogos",
    "w": "vitorias", "won": "vitorias",
    "d": "empates", "drawn": "empates", "draw": "empates",
    "l": "derrotas", "lost": "derrotas",
    "gf": "gols_pro", "f": "gols_pro", "goals for": "gols_pro",
    "ga": "gols_contra", "a": "gols_contra", "goals against": "gols_contra",
    "gd": "saldo", "+/-": "saldo", "goal difference": "saldo",
    "pts": "pontos", "points": "pontos",
}
COLUNAS_ARTILHEIROS = {
    "rank": "posicao", "pos": "posicao", "#": "posicao", "rk": "posicao",
    "player": "jogador", "name": "jogador",
    "club": "time", "team": "time", "club(s)": "time", "clubs": "time",
    "goals": "gols", "gls": "gols",
}

# Marcadores que a Wikipédia coloca ao lado do nome do time:
# (C) campeão, (R) rebaixado, (Q) classificado, (X), (E), (O), (P), (T), (A)...
RE_MARCADOR = re.compile(r"\s*\(([A-Z](?:\s*,\s*[A-Z])*)\)\s*$")


# ---------------------------------------------------------------------------
# Funções de limpeza
# ---------------------------------------------------------------------------
def limpar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFC", texto or "")
    texto = texto.replace("\xa0", " ").replace("​", "")
    texto = re.sub(r"\[[^\]]{1,6}\]", "", texto)  # restos de notas: [1], [a], [nota 2]
    return re.sub(r"\s+", " ", texto).strip()


def para_inteiro(texto: str) -> int | None:
    """Converte '+62', '−3' (sinal de menos unicode), '1,234' ou '91[a]' em int."""
    if texto is None:
        return None
    t = limpar_texto(texto).replace("−", "-").replace("–", "-").replace(",", "")
    m = re.search(r"[+-]?\d+", t)
    return int(m.group()) if m else None


def separar_marcadores(nome: str) -> tuple[str, list[str]]:
    """'Manchester City (C)' -> ('Manchester City', ['C'])"""
    marcadores: list[str] = []
    nome = limpar_texto(nome)
    while True:
        m = RE_MARCADOR.search(nome)
        if not m:
            break
        marcadores = [x.strip() for x in m.group(1).split(",")] + marcadores
        nome = nome[: m.start()].strip()
    return nome, marcadores


def _normalizar_cabecalho(texto: str) -> str:
    return limpar_texto(texto).lower().rstrip(".").strip()


# ---------------------------------------------------------------------------
# Leitura de tabelas HTML respeitando rowspan/colspan
# ---------------------------------------------------------------------------
def _remover_ruido(soup: BeautifulSoup) -> None:
    """Remove notas de rodapé, chaves de ordenação ocultas e bandeiras."""
    seletores = ["sup", ".sortkey", ".flagicon", "img", "style", "script",
                 "[style*='display:none']", "[style*='display: none']"]
    for sel in seletores:
        for el in soup.select(sel):
            el.decompose()


def tabela_para_grade(tabela: Tag) -> list[list[str]]:
    """
    Converte uma <table> em matriz de textos. Células com rowspan/colspan
    são repetidas nas linhas/colunas que ocupam. Isso é importante na
    tabela de artilheiros, onde jogadores empatados compartilham a mesma
    célula de posição e de gols.
    """
    grade: list[list[str]] = []
    pendentes: dict[tuple[int, int], str] = {}  # (linha, coluna) -> texto herdado
    linhas = [tr for tr in tabela.find_all("tr") if tr.find_parent("table") is tabela]
    for i, tr in enumerate(linhas):
        linha: list[str] = []
        col = 0
        celulas = tr.find_all(["th", "td"], recursive=False)
        for cel in celulas:
            while (i, col) in pendentes:
                linha.append(pendentes.pop((i, col)))
                col += 1
            texto = limpar_texto(cel.get_text(" "))
            rowspan = para_inteiro(cel.get("rowspan", "1")) or 1
            colspan = para_inteiro(cel.get("colspan", "1")) or 1
            for c in range(colspan):
                linha.append(texto)
                for r in range(1, rowspan):
                    pendentes[(i + r, col + c)] = texto
            col += colspan
        while (i, col) in pendentes:
            linha.append(pendentes.pop((i, col)))
            col += 1
        grade.append(linha)
    return grade


def _mapear_cabecalho(cabecalho: list[str], sinonimos: dict[str, str]) -> dict[str, int]:
    mapa: dict[str, int] = {}
    for idx, nome in enumerate(cabecalho):
        chave = sinonimos.get(_normalizar_cabecalho(nome))
        if chave and chave not in mapa:
            mapa[chave] = idx
    return mapa


def _titulo_secao_anterior(tabela: Tag) -> str:
    cab = tabela.find_previous(["h2", "h3", "h4"])
    return limpar_texto(cab.get_text(" ")).lower() if cab else ""


# ---------------------------------------------------------------------------
# Extração principal
# ---------------------------------------------------------------------------
def extrair_classificacao(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    _remover_ruido(soup)
    obrigatorias = {"time", "jogos", "vitorias", "empates", "derrotas", "pontos"}

    for tabela in soup.select("table.wikitable"):
        grade = tabela_para_grade(tabela)
        if len(grade) < 11:
            continue
        mapa = _mapear_cabecalho(grade[0], COLUNAS_CLASSIFICACAO)
        if not obrigatorias.issubset(mapa):
            continue

        registros = []
        for linha in grade[1:]:
            def valor(campo):
                idx = mapa.get(campo)
                return linha[idx] if idx is not None and idx < len(linha) else None

            nome, marcadores = separar_marcadores(valor("time") or "")
            jogos = para_inteiro(valor("jogos"))
            if not nome or jogos is None:
                continue  # linha de rodapé ou separador
            reg = {
                "posicao": para_inteiro(valor("posicao")),
                "time": nome,
                "jogos": jogos,
                "vitorias": para_inteiro(valor("vitorias")) or 0,
                "empates": para_inteiro(valor("empates")) or 0,
                "derrotas": para_inteiro(valor("derrotas")) or 0,
                "gols_pro": para_inteiro(valor("gols_pro")),
                "gols_contra": para_inteiro(valor("gols_contra")),
                "saldo": para_inteiro(valor("saldo")),
                "pontos": para_inteiro(valor("pontos")) or 0,
                "marcadores": marcadores,
            }
            registros.append(reg)

        if 10 <= len(registros) <= 30:
            for i, reg in enumerate(registros, start=1):
                if reg["posicao"] is None:
                    reg["posicao"] = i
                if reg["saldo"] is None and None not in (reg["gols_pro"], reg["gols_contra"]):
                    reg["saldo"] = reg["gols_pro"] - reg["gols_contra"]
            return registros
    return []


def extrair_artilheiros(html: str, limite: int = 20) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    _remover_ruido(soup)

    candidatas = []
    for tabela in soup.select("table.wikitable"):
        grade = tabela_para_grade(tabela)
        if len(grade) < 2:
            continue
        mapa = _mapear_cabecalho(grade[0], COLUNAS_ARTILHEIROS)
        if {"jogador", "gols"}.issubset(mapa):
            candidatas.append((tabela, grade, mapa))
    if not candidatas:
        return []

    # Prefere a tabela que está logo abaixo de um título com "scorer"
    preferidas = [c for c in candidatas if "scorer" in _titulo_secao_anterior(c[0])]
    _, grade, mapa = (preferidas or candidatas)[0]

    artilheiros = []
    for linha in grade[1:]:
        def valor(campo):
            idx = mapa.get(campo)
            return linha[idx] if idx is not None and idx < len(linha) else None

        jogador = limpar_texto(valor("jogador") or "")
        gols = para_inteiro(valor("gols"))
        if not jogador or gols is None or gols <= 0:
            continue
        time_nome, _ = separar_marcadores(valor("time") or "")
        artilheiros.append({
            "posicao": para_inteiro(valor("posicao")),
            "jogador": jogador,
            "time": time_nome or None,
            "gols": gols,
        })
        if len(artilheiros) >= limite:
            break

    # Posição ausente -> calcula com empate (mesmo número de gols = mesma posição)
    for i, art in enumerate(artilheiros):
        if art["posicao"] is None:
            if i > 0 and artilheiros[i - 1]["gols"] == art["gols"]:
                art["posicao"] = artilheiros[i - 1]["posicao"]
            else:
                art["posicao"] = i + 1
    return artilheiros
