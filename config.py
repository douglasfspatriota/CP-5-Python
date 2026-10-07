"""
Configurações centrais do projeto.

Todas as configurações podem ser alteradas por variáveis de ambiente
(ou por um arquivo .env na raiz do projeto), sem mexer no código.
"""
import os
from pathlib import Path

# Carrega o arquivo .env (se existir) de forma simples, sem dependências extras.
_ENV = Path(__file__).resolve().parent / ".env"
if _ENV.exists():
    for linha in _ENV.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip())

# --- MongoDB ---
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "futebol_dados")

# --- Crawler ---
# A Wikipédia pede que todo robô se identifique com um User-Agent descritivo
# e um contato. Troque o e-mail abaixo pelo e-mail do grupo no arquivo .env.
USER_AGENT = os.getenv(
    "USER_AGENT",
    "FutebolDadosCrawler/1.0 (projeto academico; contato: grupo@exemplo.com)",
)
WIKI_API = os.getenv("WIKI_API", "https://en.wikipedia.org/w/api.php")
INTERVALO_REQUISICOES = float(os.getenv("INTERVALO_REQUISICOES", "1.0"))  # segundos
TIMEOUT = float(os.getenv("TIMEOUT", "20"))
TENTATIVAS = int(os.getenv("TENTATIVAS", "3"))

# Temporadas padrão (ano de início). Ex.: 2015 = "2015-16" na Europa / "2015" no Brasil.
ANO_INICIO_PADRAO = int(os.getenv("ANO_INICIO", "2015"))
# Vazio = até a temporada atual (em andamento) de cada liga.
ANO_FIM_PADRAO = int(os.getenv("ANO_FIM")) if os.getenv("ANO_FIM") else None
