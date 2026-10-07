"""
Cliente HTTP para a Wikipédia.

Usa a API oficial (action=parse), que devolve o HTML renderizado do artigo.
Continua sendo extração de HTML, mas de forma mais estável e educada
com o servidor do que baixar a página completa com menus e scripts.

Boas práticas aplicadas:
  * User-Agent identificando o projeto (exigência da Wikipédia);
  * intervalo fixo entre requisições;
  * novas tentativas com espera crescente em caso de erro temporário;
  * parâmetro maxlag, que faz a API recusar pedidos quando está sobrecarregada.
"""
import logging
import time
from dataclasses import dataclass

import requests

import config

log = logging.getLogger(__name__)


@dataclass
class PaginaWiki:
    titulo: str
    pageid: int
    revid: int
    html: str

    @property
    def url(self) -> str:
        return "https://en.wikipedia.org/wiki/" + self.titulo.replace(" ", "_")


class PaginaNaoEncontrada(Exception):
    pass


class ClienteWikipedia:
    def __init__(self, intervalo: float = config.INTERVALO_REQUISICOES):
        self.sessao = requests.Session()
        self.sessao.headers.update({"User-Agent": config.USER_AGENT})
        self.intervalo = intervalo
        self._ultima = 0.0

    def _esperar_vez(self) -> None:
        decorrido = time.monotonic() - self._ultima
        if decorrido < self.intervalo:
            time.sleep(self.intervalo - decorrido)
        self._ultima = time.monotonic()

    def buscar_pagina(self, titulo: str) -> PaginaWiki:
        params = {
            "action": "parse",
            "page": titulo,
            "prop": "text|revid",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
            "maxlag": "5",
        }
        ultimo_erro: Exception | None = None
        for tentativa in range(1, config.TENTATIVAS + 1):
            self._esperar_vez()
            try:
                resp = self.sessao.get(config.WIKI_API, params=params, timeout=config.TIMEOUT)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {resp.status_code}")
                resp.raise_for_status()
                dados = resp.json()
                if "error" in dados:
                    codigo = dados["error"].get("code")
                    if codigo == "missingtitle":
                        raise PaginaNaoEncontrada(titulo)
                    if codigo == "maxlag":
                        raise requests.HTTPError("servidor sobrecarregado (maxlag)")
                    raise RuntimeError(f"Erro da API: {dados['error']}")
                p = dados["parse"]
                return PaginaWiki(p["title"], p["pageid"], p.get("revid", 0), p["text"])
            except PaginaNaoEncontrada:
                raise
            except (requests.RequestException, ValueError) as erro:
                ultimo_erro = erro
                espera = 2 ** tentativa
                log.warning("Falha ao buscar '%s' (%s). Tentando de novo em %ss...", titulo, erro, espera)
                time.sleep(espera)
        raise RuntimeError(f"Não foi possível buscar '{titulo}': {ultimo_erro}")
