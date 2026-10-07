"""Funções utilitárias compartilhadas entre os módulos."""
import unicodedata


def normalizar_busca(texto: str) -> str:
    """'Grêmio' -> 'gremio' (usado para buscas sem acento e sem maiúsculas)."""
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())
