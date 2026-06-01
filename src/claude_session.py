"""
claude_session.py

Le o consumo real da sessao atual do Claude Code, direto dos transcripts.

O Claude Code grava cada sessao em um arquivo .jsonl dentro de:
  %USERPROFILE%\\.claude\\projects\\<projeto-codificado>\\<sessao>.jsonl

Cada linha e um evento JSON. As mensagens do assistente trazem
message.usage com:
  - input_tokens
  - output_tokens
  - cache_creation_input_tokens
  - cache_read_input_tokens
e message.model com o nome do modelo.

Este modulo localiza a sessao ativa (o .jsonl modificado mais recentemente)
e soma o consumo de todas as mensagens do assistente, devolvendo o total
no mesmo formato do arquivo de estado usado pelo widget.

Assim o widget mostra o consumo da sessao atual automaticamente, sem
precisar que um script externo chame registrar().
"""

import json
import os

# Pasta onde o Claude Code guarda os transcripts por projeto.
PASTA_PROJETOS = os.path.join(os.path.expanduser("~"), ".claude", "projects")

# Cache simples para nao reprocessar o arquivo inteiro a cada 2s.
# Guarda (caminho, mtime, tamanho) -> agregado ja calculado.
_cache = {"chave": None, "resultado": None}


def localizar_sessao_ativa(idade_maxima_seg=None):
    """
    Encontra o transcript .jsonl modificado mais recentemente.

    Esse arquivo corresponde a sessao do Claude Code que esta sendo
    escrita agora (a sessao ativa).

    Se idade_maxima_seg for informado, ignora arquivos mais antigos que
    isso (ajuda a nao mostrar uma sessao velha quando nada esta rodando).
    Como nao podemos usar relogio aqui de forma confiavel no widget,
    o padrao e None (sempre pega o mais recente).

    Retorna o caminho do arquivo, ou None se nao houver nenhum.
    """
    if not os.path.isdir(PASTA_PROJETOS):
        return None

    mais_recente = None
    mtime_recente = -1.0

    try:
        for raiz, _dirs, arquivos in os.walk(PASTA_PROJETOS):
            for nome in arquivos:
                if not nome.endswith(".jsonl"):
                    continue
                caminho = os.path.join(raiz, nome)
                try:
                    mtime = os.path.getmtime(caminho)
                except OSError:
                    continue
                if mtime > mtime_recente:
                    mtime_recente = mtime
                    mais_recente = caminho
    except OSError:
        return None

    return mais_recente


def _agregar(caminho):
    """
    Le o arquivo .jsonl e soma o consumo de todas as mensagens do assistente.

    Retorna um dicionario no formato do estado do widget. Linhas
    invalidas ou sem usage sao ignoradas (nao quebram a leitura).
    """
    totais = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "model": None,
        "session_started": None,
        "session_id": None,
    }

    try:
        with open(caminho, "r", encoding="utf-8") as arquivo:
            for linha in arquivo:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    evento = json.loads(linha)
                except (json.JSONDecodeError, ValueError):
                    continue

                if not isinstance(evento, dict):
                    continue

                # Marca o inicio da sessao com o primeiro timestamp visto.
                if totais["session_started"] is None and evento.get("timestamp"):
                    totais["session_started"] = evento["timestamp"]

                if totais["session_id"] is None and evento.get("sessionId"):
                    totais["session_id"] = evento["sessionId"]

                if evento.get("type") != "assistant":
                    continue

                mensagem = evento.get("message")
                if not isinstance(mensagem, dict):
                    continue

                if mensagem.get("model"):
                    totais["model"] = mensagem["model"]

                uso = mensagem.get("usage")
                if not isinstance(uso, dict):
                    continue

                totais["input_tokens"] += int(uso.get("input_tokens", 0) or 0)
                totais["output_tokens"] += int(uso.get("output_tokens", 0) or 0)
                totais["cache_creation_tokens"] += int(
                    uso.get("cache_creation_input_tokens", 0) or 0
                )
                totais["cache_read_tokens"] += int(
                    uso.get("cache_read_input_tokens", 0) or 0
                )
    except OSError:
        return None

    if totais["model"] is None:
        totais["model"] = "claude-opus-4"

    return totais


def ler_sessao_ativa():
    """
    Devolve o consumo agregado da sessao ativa do Claude Code.

    Usa cache baseado em (caminho, mtime, tamanho) para so reprocessar
    o arquivo quando ele muda. Retorna None se nenhuma sessao for
    encontrada.
    """
    caminho = localizar_sessao_ativa()
    if not caminho:
        return None

    try:
        mtime = os.path.getmtime(caminho)
        tamanho = os.path.getsize(caminho)
    except OSError:
        return None

    chave = (caminho, mtime, tamanho)
    if _cache["chave"] == chave and _cache["resultado"] is not None:
        return _cache["resultado"]

    resultado = _agregar(caminho)
    _cache["chave"] = chave
    _cache["resultado"] = resultado
    return resultado


# Teste rapido pelo terminal: python claude_session.py
if __name__ == "__main__":
    dados = ler_sessao_ativa()
    if dados is None:
        print("Nenhuma sessao ativa encontrada.")
    else:
        print(json.dumps(dados, indent=2, ensure_ascii=False))
