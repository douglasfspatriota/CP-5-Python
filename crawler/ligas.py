"""
Definição das ligas coletadas e de como montar o título da página
de cada temporada na Wikipédia (em inglês).

Exemplos de títulos reais:
    "2023–24 Premier League"
    "2023 Campeonato Brasileiro Série A"
"""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Liga:
    slug: str          # identificador usado no banco e na API
    nome: str          # nome exibido no dashboard
    pais: str
    titulo_wiki: str   # sufixo do título da página na Wikipédia
    calendario: str    # "europeu" (2023–24) ou "anual" (2023)
    mes_inicio: int    # mês aproximado em que a temporada começa

    def temporada_atual(self, hoje: date | None = None) -> int:
        """
        Ano de início da temporada mais recente que já começou.
        Ex.: em outubro/2026 -> Europa 2026 (2026-27) e Brasileirão 2026.
             em fevereiro/2027 -> Europa ainda 2026 (2026-27) e Brasileirão 2026.
        """
        hoje = hoje or date.today()
        return hoje.year if hoje.month >= self.mes_inicio else hoje.year - 1

    def rotulo_temporada(self, ano_inicio: int) -> str:
        """Rótulo da temporada no formato salvo no banco: '2023-24' ou '2023'."""
        if self.calendario == "anual":
            return str(ano_inicio)
        fim = ano_inicio + 1
        # 1999-2000 é escrito por extenso; os demais usam só os 2 últimos dígitos.
        sufixo = str(fim) if fim % 100 == 0 else f"{fim % 100:02d}"
        return f"{ano_inicio}-{sufixo}"

    def titulo_pagina(self, ano_inicio: int) -> str:
        """Título exato do artigo na Wikipédia (usa travessão '–', não hífen)."""
        rotulo = self.rotulo_temporada(ano_inicio).replace("-", "–")
        return f"{rotulo} {self.titulo_wiki}"


LIGAS: dict[str, Liga] = {
    liga.slug: liga
    for liga in [
        Liga("premier-league", "Premier League", "Inglaterra", "Premier League", "europeu", 8),
        Liga("la-liga", "La Liga", "Espanha", "La Liga", "europeu", 8),
        Liga("serie-a", "Serie A", "Itália", "Serie A", "europeu", 8),
        Liga("bundesliga", "Bundesliga", "Alemanha", "Bundesliga", "europeu", 8),
        Liga("ligue-1", "Ligue 1", "França", "Ligue 1", "europeu", 8),
        Liga("brasileirao", "Brasileirão", "Brasil", "Campeonato Brasileiro Série A", "anual", 4),
    ]
}
