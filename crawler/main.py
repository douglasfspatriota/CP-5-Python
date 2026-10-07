"""
Ponto de entrada do Web Crawler (roda de forma independente da API).

Exemplos:
    python -m crawler.main                         # 6 ligas, temporadas padrão
    python -m crawler.main --ligas brasileirao     # só o Brasileirão
    python -m crawler.main --inicio 2020 --fim 2024
    python -m crawler.main --ligas premier-league la-liga --inicio 2022

Fluxo para cada liga/temporada:
    1. monta o título da página na Wikipédia;
    2. baixa o HTML pela API da Wikipédia;
    3. extrai a tabela de classificação e a de artilheiros;
    4. trata/valida os dados e calcula campos derivados;
    5. grava no MongoDB com upsert (sem duplicar e sem apagar coletas antigas).
"""
import argparse
import logging
import sys
from datetime import datetime, timezone

from pymongo.errors import ServerSelectionTimeoutError

import config
from crawler.ligas import LIGAS
from crawler.parser import extrair_artilheiros, extrair_classificacao
from crawler.tratamento import montar_artilheiros, montar_classificacao, montar_resumo_temporada
from crawler.wikipedia import ClienteWikipedia, PaginaNaoEncontrada
from database import repositorio as repo
from database.conexao import ARTILHEIROS, CLASSIFICACOES, TEMPORADAS, criar_indices, obter_banco

log = logging.getLogger("crawler")


def coletar(ligas: list[str], inicio: int, fim: int | None = None, db=None, cliente=None,
            hoje=None) -> dict:
    """
    fim=None -> coleta até a temporada atual (em andamento) de cada liga.
    Temporadas que ainda não começaram são puladas automaticamente.
    """
    db = obter_banco(db)
    cliente = cliente or ClienteWikipedia()
    criar_indices(db)
    execucao_id = repo.iniciar_execucao(db, {"ligas": ligas, "inicio": inicio, "fim": fim})
    log.info("Execução %s iniciada: %d liga(s), temporadas %d até %s",
             execucao_id, len(ligas), inicio, fim if fim else "a atual")

    for slug in ligas:
        liga = LIGAS[slug]
        atual = liga.temporada_atual(hoje)
        ultimo = min(fim, atual) if fim else atual
        for ano in range(inicio, ultimo + 1):
            titulo = liga.titulo_pagina(ano)
            temporada = liga.rotulo_temporada(ano)
            try:
                pagina = cliente.buscar_pagina(titulo)
                linhas = extrair_classificacao(pagina.html)
                if not linhas:
                    raise ValueError("tabela de classificação não encontrada na página")
                fonte = {
                    "site": "Wikipédia (en)",
                    "url": pagina.url,
                    "titulo_pagina": pagina.titulo,
                    "pageid": pagina.pageid,
                    "revid": pagina.revid,
                    "coletado_em": datetime.now(timezone.utc),
                }
                classificacao = montar_classificacao(liga, ano, linhas, fonte)
                artilheiros = montar_artilheiros(liga, ano, extrair_artilheiros(pagina.html), fonte)
                resumo = montar_resumo_temporada(liga, ano, classificacao, artilheiros, fonte)

                em_andamento = not resumo["temporada_encerrada"] and not resumo["campeao"]
                # Na temporada em andamento, cada coleta guarda um "retrato" (posição,
                # pontos, jogos) no campo historico: nada da coleta anterior se perde.
                retrato = ("posicao", "pontos", "jogos") if em_andamento else None
                r1 = repo.salvar_documentos(db, CLASSIFICACOES, classificacao,
                                            ("liga", "temporada", "time"), execucao_id, retrato)
                r2 = repo.salvar_documentos(db, ARTILHEIROS, artilheiros,
                                            ("liga", "temporada", "jogador"), execucao_id,
                                            ("gols",) if em_andamento else None)
                repo.marcar_fora_do_ranking(db, slug, temporada, [a["jogador"] for a in artilheiros])
                repo.salvar_documentos(db, TEMPORADAS, [resumo], ("liga", "temporada"), execucao_id,
                                       ("lider", "diferenca_lider_vice", "total_gols") if em_andamento else None)

                repo.registrar_pagina(db, execucao_id, {
                    "liga": slug, "temporada": temporada, "url": pagina.url,
                    "times": len(classificacao), "artilheiros": len(artilheiros),
                    "em_andamento": em_andamento,
                    "inseridos": r1["inseridos"] + r2["inseridos"],
                    "atualizados": r1["atualizados"] + r2["atualizados"],
                })
                log.info("OK  %-15s %-8s %2d times, %2d artilheiros | campeão/líder: %s",
                         liga.nome, temporada, len(classificacao), len(artilheiros),
                         resumo["campeao"] or f"{resumo['lider']} (líder, temporada em andamento)")
            except PaginaNaoEncontrada:
                log.warning("--  %-15s %-8s página não existe na Wikipédia: %s", liga.nome, temporada, titulo)
                repo.registrar_erro(db, execucao_id, {"liga": slug, "temporada": temporada,
                                                      "erro": "página não encontrada"})
            except Exception as erro:  # noqa: BLE001 - uma página com erro não derruba a coleta
                log.error("ERRO %-15s %-8s %s", liga.nome, temporada, erro)
                repo.registrar_erro(db, execucao_id, {"liga": slug, "temporada": temporada,
                                                      "erro": str(erro)})

    execucao = repo.finalizar_execucao(db, execucao_id)
    t = execucao["totais"]
    log.info("Fim da execução (%s): %d páginas, %d registros novos, %d atualizados, %d erro(s)",
             execucao["status"], t["paginas_ok"], t["inseridos"], t["atualizados"], len(execucao["erros"]))
    return execucao


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Coleta classificações e artilheiros na Wikipédia.")
    parser.add_argument("--ligas", nargs="+", choices=list(LIGAS), default=list(LIGAS),
                        help="ligas a coletar (padrão: todas)")
    parser.add_argument("--inicio", type=int, default=config.ANO_INICIO_PADRAO,
                        help="ano inicial da temporada (padrão: %(default)s)")
    parser.add_argument("--fim", type=int, default=config.ANO_FIM_PADRAO,
                        help="ano final da temporada (padrão: a temporada atual de cada liga)")
    args = parser.parse_args(argv)
    if args.fim is not None and args.inicio > args.fim:
        parser.error("--inicio deve ser menor ou igual a --fim")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    try:
        execucao = coletar(args.ligas, args.inicio, args.fim)
    except ServerSelectionTimeoutError:
        log.error("Não foi possível conectar ao MongoDB em %s. Ele está rodando?", config.MONGO_URI)
        return 1
    return 0 if execucao["status"] != "falhou" else 1


if __name__ == "__main__":
    sys.exit(main())
