"""
Tratamento dos dados extraídos: validação, campos calculados e montagem
dos documentos que serão gravados no MongoDB.
"""
from crawler.ligas import Liga
from utils import normalizar_busca


def _arred(valor: float, casas: int = 2) -> float:
    return round(valor, casas)


def montar_classificacao(liga: Liga, ano: int, linhas: list[dict], fonte: dict) -> list[dict]:
    temporada = liga.rotulo_temporada(ano)
    total_times = len(linhas)
    jogos_temporada = 2 * (total_times - 1)  # turno e returno
    encerrada = all(l["jogos"] == jogos_temporada for l in linhas)
    tem_marcador_campeao = any("C" in l["marcadores"] for l in linhas)

    documentos = []
    for l in linhas:
        if tem_marcador_campeao:
            campeao = "C" in l["marcadores"]
        else:
            campeao = encerrada and l["posicao"] == 1
        jogos = l["jogos"] or 0
        documentos.append({
            "liga": liga.slug,
            "liga_nome": liga.nome,
            "pais": liga.pais,
            "temporada": temporada,
            "ano_inicio": ano,
            "posicao": l["posicao"],
            "time": l["time"],
            "time_busca": normalizar_busca(l["time"]),
            "jogos": jogos,
            "vitorias": l["vitorias"],
            "empates": l["empates"],
            "derrotas": l["derrotas"],
            "gols_pro": l["gols_pro"],
            "gols_contra": l["gols_contra"],
            "saldo": l["saldo"],
            "pontos": l["pontos"],
            "aproveitamento": _arred(100 * l["pontos"] / (3 * jogos), 1) if jogos else 0.0,
            "media_gols_pro": _arred(l["gols_pro"] / jogos) if jogos and l["gols_pro"] is not None else None,
            "media_gols_contra": _arred(l["gols_contra"] / jogos) if jogos and l["gols_contra"] is not None else None,
            "campeao": campeao,
            "rebaixado": "R" in l["marcadores"],
            "marcadores": l["marcadores"],
            "total_times": total_times,
            "temporada_encerrada": encerrada,
            "fonte": fonte,
        })
    return documentos


def montar_artilheiros(liga: Liga, ano: int, linhas: list[dict], fonte: dict) -> list[dict]:
    temporada = liga.rotulo_temporada(ano)
    return [{
        "liga": liga.slug,
        "liga_nome": liga.nome,
        "temporada": temporada,
        "ano_inicio": ano,
        "posicao": a["posicao"],
        "jogador": a["jogador"],
        "jogador_busca": normalizar_busca(a["jogador"]),
        "time": a["time"],
        "gols": a["gols"],
        "fonte": fonte,
    } for a in linhas]


def montar_resumo_temporada(liga: Liga, ano: int, classificacao: list[dict],
                            artilheiros: list[dict], fonte: dict) -> dict:
    """Um documento por liga/temporada com os números consolidados."""
    ordenada = sorted(classificacao, key=lambda d: d["posicao"])
    primeiro, segundo = ordenada[0], ordenada[1]
    campeao = next((d for d in ordenada if d["campeao"]), None)
    total_gols = sum(d["gols_pro"] or 0 for d in ordenada)
    partidas = sum(d["jogos"] for d in ordenada) // 2
    top = artilheiros[0] if artilheiros else None
    return {
        "liga": liga.slug,
        "liga_nome": liga.nome,
        "pais": liga.pais,
        "temporada": liga.rotulo_temporada(ano),
        "ano_inicio": ano,
        "total_times": len(ordenada),
        "temporada_encerrada": ordenada[0]["temporada_encerrada"],
        "partidas": partidas,
        "total_gols": total_gols,
        "media_gols_jogo": _arred(total_gols / partidas) if partidas else 0.0,
        "campeao": campeao["time"] if campeao else None,
        "pontos_campeao": campeao["pontos"] if campeao else None,
        "aproveitamento_campeao": campeao["aproveitamento"] if campeao else None,
        "lider": primeiro["time"],
        "vice": segundo["time"],
        "diferenca_lider_vice": primeiro["pontos"] - segundo["pontos"],
        "melhor_ataque": max(ordenada, key=lambda d: d["gols_pro"] or 0)["time"],
        "melhor_defesa": min(ordenada, key=lambda d: d["gols_contra"] if d["gols_contra"] is not None else 999)["time"],
        "rebaixados": [d["time"] for d in ordenada if d["rebaixado"]],
        "artilheiro": top["jogador"] if top else None,
        "gols_artilheiro": top["gols"] if top else None,
        "fonte": fonte,
    }
