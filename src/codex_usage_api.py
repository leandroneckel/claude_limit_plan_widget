"""
Consulta limites atualizados pelo app-server local do Codex.

O protocolo local expoe account/rateLimits/read. A consulta usa o proprio
binario codex, que gerencia sua autenticacao normalmente. Este modulo nao le
auth.json e nao grava credenciais.
"""

import json
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone


INTERVALO_MIN_FETCH = 60
TIMEOUT_SEG = 8

_cache = {"momento": 0.0, "resultado": None}


def _agora_iso():
    """Retorna o instante atual em ISO 8601 UTC."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parte(secao):
    """Normaliza uma janela retornada pelo protocolo local."""
    if not isinstance(secao, dict) or secao.get("usedPercent") is None:
        return None
    return {
        "utilization": float(secao.get("usedPercent")),
        "resets_at": secao.get("resetsAt"),
        "window_minutes": int(secao.get("windowDurationMins") or 0),
    }


def _normalizar(snapshot):
    """Converte RateLimitSnapshot para o formato compartilhado pela GUI."""
    if not isinstance(snapshot, dict):
        return None
    plano = str(snapshot.get("planType") or "plano").capitalize()
    creditos = snapshot.get("credits")
    if isinstance(creditos, dict):
        creditos = {
            "has_credits": creditos.get("hasCredits"),
            "unlimited": creditos.get("unlimited"),
            "balance": creditos.get("balance"),
        }
    return {
        "ok": True,
        "plano": plano,
        "sessao": _parte(snapshot.get("primary")),
        "semana": _parte(snapshot.get("secondary")),
        "creditos": creditos,
        "snapshot_at": _agora_iso(),
        "origem": "app-server",
    }


def _ler_linha(stream, saida):
    """Le stdout fora da thread chamadora para permitir timeout."""
    try:
        saida.put(stream.readline())
    except OSError:
        saida.put("")


def _consultar():
    """Executa uma consulta JSON-RPC curta contra codex app-server --stdio."""
    executavel = shutil.which("codex")
    if not executavel:
        return {"ok": False, "erro": "codex CLI nao encontrado"}

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    processo = None
    try:
        processo = subprocess.Popen(
            [executavel, "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            creationflags=flags,
        )
        mensagens = (
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": "token-widget",
                        "version": "1.0.0",
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "account/rateLimits/read",
                "params": {},
            },
        )
        for mensagem in mensagens:
            processo.stdin.write(json.dumps(mensagem) + "\n")
            processo.stdin.flush()

        fim = time.monotonic() + TIMEOUT_SEG
        while time.monotonic() < fim:
            saida = queue.Queue()
            leitor = threading.Thread(
                target=_ler_linha,
                args=(processo.stdout, saida),
                daemon=True,
            )
            leitor.start()
            try:
                linha = saida.get(timeout=max(0.1, fim - time.monotonic()))
            except queue.Empty:
                break
            if not linha:
                break
            try:
                resposta = json.loads(linha)
            except (json.JSONDecodeError, ValueError):
                continue
            if resposta.get("id") != 2:
                continue
            resultado = resposta.get("result")
            if not isinstance(resultado, dict):
                break
            normalizado = _normalizar(resultado.get("rateLimits"))
            if normalizado:
                return normalizado
            break
    except (OSError, BrokenPipeError):
        pass
    finally:
        if processo is not None:
            try:
                processo.kill()
            except OSError:
                pass

    return {"ok": False, "erro": "falha ao consultar codex app-server"}


def ler_limites(forcar=False):
    """Consulta limites com cache curto para evitar processos desnecessarios."""
    agora = time.time()
    if (
        not forcar
        and _cache["resultado"] is not None
        and agora - _cache["momento"] < INTERVALO_MIN_FETCH
    ):
        return _cache["resultado"]

    resultado = _consultar()
    if resultado.get("ok") or _cache["resultado"] is None:
        _cache["resultado"] = resultado
    _cache["momento"] = agora
    return _cache["resultado"]


if __name__ == "__main__":
    print(json.dumps(ler_limites(forcar=True), indent=2, ensure_ascii=False))
