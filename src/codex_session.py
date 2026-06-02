"""
Le limites e tokens da sessao mais recente do Codex a partir dos rollouts locais.

O Codex grava transcripts JSONL em:
  %USERPROFILE%\\.codex\\sessions\\AAAA\\MM\\DD\\rollout-*.jsonl

Os eventos token_count incluem o consumo acumulado da thread e os limites
primario e secundario exibidos pelo proprio Codex. Este modulo nao le
credenciais e nao faz chamadas de rede.
"""

import json
import os
from datetime import datetime


PASTA_SESSOES = os.path.join(os.path.expanduser("~"), ".codex", "sessions")

# Guarda (caminho, mtime, tamanho) -> resultado para evitar reler o rollout
# inteiro a cada atualizacao visual.
_cache = {"chave": None, "resultado": None}
_cache_limites = {"chave": None, "resultado": None}


def localizar_sessao_ativa():
    """Retorna o rollout JSONL modificado mais recentemente, ou None."""
    if not os.path.isdir(PASTA_SESSOES):
        return None

    mais_recente = None
    mtime_recente = -1.0
    try:
        for raiz, _dirs, arquivos in os.walk(PASTA_SESSOES):
            for nome in arquivos:
                if not nome.endswith(".jsonl"):
                    continue
                caminho = os.path.join(raiz, nome)
                try:
                    mtime = os.path.getmtime(caminho)
                except OSError:
                    continue
                if mtime > mtime_recente:
                    mais_recente = caminho
                    mtime_recente = mtime
    except OSError:
        return None

    return mais_recente


def _inteiro(valor):
    """Converte valores numericos para inteiro sem interromper o widget."""
    try:
        return int(valor or 0)
    except (TypeError, ValueError):
        return 0


def _normalizar_tokens(info):
    """Converte total_token_usage para o formato usado pela interface."""
    if not isinstance(info, dict):
        info = {}
    uso = info.get("total_token_usage")
    if not isinstance(uso, dict):
        uso = {}

    return {
        "input_tokens": _inteiro(uso.get("input_tokens")),
        "cached_input_tokens": _inteiro(uso.get("cached_input_tokens")),
        "output_tokens": _inteiro(uso.get("output_tokens")),
        "reasoning_output_tokens": _inteiro(uso.get("reasoning_output_tokens")),
        "total_tokens": _inteiro(uso.get("total_tokens")),
        "model_context_window": _inteiro(info.get("model_context_window")),
    }


def _agregar(caminho):
    """
    Le o rollout e devolve o ultimo token_count com metadados da thread.

    Linhas invalidas e eventos desconhecidos sao ignorados para tolerar
    mudancas futuras no formato local do Codex.
    """
    resultado = {
        "session_id": None,
        "session_started": None,
        "model": None,
        "tokens": None,
        "rate_limits": None,
        "snapshot_at": None,
    }

    try:
        with open(caminho, "r", encoding="utf-8") as arquivo:
            for linha in arquivo:
                try:
                    evento = json.loads(linha)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(evento, dict):
                    continue

                payload = evento.get("payload")
                if not isinstance(payload, dict):
                    continue

                if evento.get("type") == "session_meta":
                    resultado["session_id"] = payload.get("id")
                    resultado["session_started"] = payload.get("timestamp")
                elif evento.get("type") == "turn_context":
                    if payload.get("model"):
                        resultado["model"] = payload.get("model")
                elif (
                    evento.get("type") == "event_msg"
                    and payload.get("type") == "token_count"
                ):
                    resultado["tokens"] = _normalizar_tokens(payload.get("info"))
                    resultado["snapshot_at"] = evento.get("timestamp")
                    limites = payload.get("rate_limits")
                    resultado["rate_limits"] = (
                        limites if isinstance(limites, dict) else None
                    )
    except OSError:
        return None

    return resultado


def ler_sessao_ativa():
    """Retorna os dados locais da thread Codex mais recente, ou None."""
    caminho = localizar_sessao_ativa()
    if not caminho:
        return None

    try:
        chave = (caminho, os.path.getmtime(caminho), os.path.getsize(caminho))
    except OSError:
        return None

    if _cache["chave"] == chave:
        return _cache["resultado"]

    resultado = _agregar(caminho)
    _cache["chave"] = chave
    _cache["resultado"] = resultado
    return resultado


def ler_tokens():
    """Retorna os tokens da thread mais recente no formato da interface."""
    sessao = ler_sessao_ativa()
    if not sessao or not isinstance(sessao.get("tokens"), dict):
        return None

    estado = dict(sessao["tokens"])
    estado["session_id"] = sessao.get("session_id")
    estado["session_started"] = sessao.get("session_started")
    estado["snapshot_at"] = sessao.get("snapshot_at")
    estado["model"] = sessao.get("model") or "Codex"
    return estado


def _parte(secao):
    """Normaliza uma janela de limite local do Codex."""
    if not isinstance(secao, dict):
        return None
    if secao.get("used_percent") is None:
        return None
    return {
        "utilization": float(secao.get("used_percent")),
        "resets_at": secao.get("resets_at"),
        "window_minutes": _inteiro(secao.get("window_minutes")),
    }


def _timestamp(iso):
    """Converte timestamp ISO para comparacao, tolerando valores ausentes."""
    if not iso:
        return 0.0
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _snapshot_limites_mais_recente():
    """
    Encontra o token_count mais novo entre todos os rollouts.

    Os limites sao globais da conta. Uma thread pode continuar recebendo
    eventos locais sem emitir outro token_count enquanto outra thread grava um
    snapshot mais novo. Por isso a escolha nao pode depender apenas do rollout
    modificado mais recentemente.
    """
    if not os.path.isdir(PASTA_SESSOES):
        return None

    arquivos = []
    try:
        for raiz, _dirs, nomes in os.walk(PASTA_SESSOES):
            for nome in nomes:
                if not nome.endswith(".jsonl"):
                    continue
                caminho = os.path.join(raiz, nome)
                try:
                    arquivos.append((
                        caminho,
                        os.path.getmtime(caminho),
                        os.path.getsize(caminho),
                    ))
                except OSError:
                    continue
    except OSError:
        return None

    chave = tuple((caminho, mtime, tamanho) for caminho, mtime, tamanho in arquivos)
    if _cache_limites["chave"] == chave:
        return _cache_limites["resultado"]

    mais_recente = None
    momento_recente = 0.0
    for caminho, _mtime, _tamanho in arquivos:
        try:
            with open(caminho, "r", encoding="utf-8") as arquivo:
                for linha in arquivo:
                    try:
                        evento = json.loads(linha)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    payload = evento.get("payload")
                    if (
                        evento.get("type") != "event_msg"
                        or not isinstance(payload, dict)
                        or payload.get("type") != "token_count"
                        or not isinstance(payload.get("rate_limits"), dict)
                    ):
                        continue
                    momento = _timestamp(evento.get("timestamp"))
                    if momento >= momento_recente:
                        momento_recente = momento
                        mais_recente = {
                            "snapshot_at": evento.get("timestamp"),
                            "rate_limits": payload.get("rate_limits"),
                        }
        except OSError:
            continue

    _cache_limites["chave"] = chave
    _cache_limites["resultado"] = mais_recente
    return mais_recente


def ler_limites():
    """Retorna os limites presentes no rollout local mais recente."""
    snapshot = _snapshot_limites_mais_recente()
    if not snapshot:
        return {"ok": False, "erro": "nenhuma sessao local do Codex"}

    limites = snapshot.get("rate_limits")
    if not isinstance(limites, dict):
        return {"ok": False, "erro": "sessao ainda sem dados de limites"}

    plano = str(limites.get("plan_type") or "plano").capitalize()
    return {
        "ok": True,
        "plano": plano,
        "sessao": _parte(limites.get("primary")),
        "semana": _parte(limites.get("secondary")),
        "creditos": limites.get("credits"),
        "snapshot_at": snapshot.get("snapshot_at"),
    }


if __name__ == "__main__":
    print(json.dumps({
        "limites": ler_limites(),
        "tokens": ler_tokens(),
    }, indent=2, ensure_ascii=False))
