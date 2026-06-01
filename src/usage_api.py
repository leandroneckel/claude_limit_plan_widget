"""
usage_api.py

Le os limites de uso do plano direto do backend da Anthropic, o mesmo
dado que aparece em Configuracoes > Uso e no comando /usage do Claude Code:

  - Sessao atual (janela de 5 horas) : % usado e quando reinicia
  - Limite semanal (todos os modelos): % usado e quando reinicia
  - Limite semanal (somente Sonnet)  : % usado e quando reinicia
  - Creditos de uso (extra usage)    : habilitado, limite e gasto

Como funciona:
  - O token OAuth do Claude Code fica em %USERPROFILE%\\.claude\\.credentials.json
  - Chamamos GET https://api.anthropic.com/api/oauth/usage com
      Authorization: Bearer <accessToken>
      anthropic-beta: oauth-2025-04-20
  - Se o token estiver expirado, fazemos refresh no endpoint de token
    e gravamos o novo token de volta no arquivo de credenciais (igual ao
    que o proprio Claude Code faz), para nao deslogar o usuario.

Observacao: este modulo usa as credenciais locais da sua propria conta,
apenas para exibir o seu proprio uso. Nada e enviado para terceiros.
"""

import json
import os
import time
import urllib.error
import urllib.request

# Caminho do arquivo de credenciais do Claude Code.
CAMINHO_CRED = os.path.join(
    os.path.expanduser("~"), ".claude", ".credentials.json"
)

# Endpoints e constantes extraidas do proprio Claude Code.
URL_USAGE = "https://api.anthropic.com/api/oauth/usage"
URL_TOKEN = "https://platform.claude.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
ANTHROPIC_BETA = "oauth-2025-04-20"

# Intervalo minimo entre chamadas reais a rede (segundos).
# A tela de Uso da Anthropic tambem atualiza de poucos em poucos minutos.
INTERVALO_MIN_FETCH = 60

# Mapeia o rateLimitTier para um rotulo amigavel do plano.
ROTULOS_PLANO = {
    "default_claude_max_5x": "Max (5x)",
    "default_claude_max_20x": "Max (20x)",
    "default_claude_pro": "Pro",
}

# Cache em memoria para nao bater na rede a cada atualizacao do widget.
_cache = {"momento": 0.0, "resultado": None}


def _ler_credenciais():
    """Le o JSON de credenciais. Retorna o dict completo ou None."""
    try:
        with open(CAMINHO_CRED, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return None


def _gravar_token(novo_access, novo_refresh, novo_expires_ms):
    """
    Grava o token renovado de volta no arquivo de credenciais.

    Preserva toda a estrutura existente e atualiza apenas os tres campos
    dentro de claudeAiOauth. Escreve de forma atomica (arquivo temporario
    e replace) para evitar corromper o arquivo.
    """
    cred = _ler_credenciais()
    if not isinstance(cred, dict) or "claudeAiOauth" not in cred:
        return
    cred["claudeAiOauth"]["accessToken"] = novo_access
    if novo_refresh:
        cred["claudeAiOauth"]["refreshToken"] = novo_refresh
    if novo_expires_ms:
        cred["claudeAiOauth"]["expiresAt"] = novo_expires_ms

    temp = CAMINHO_CRED + ".tmp"
    try:
        with open(temp, "w", encoding="utf-8") as arquivo:
            json.dump(cred, arquivo, indent=2)
        os.replace(temp, CAMINHO_CRED)
    except OSError:
        # Se a gravacao falhar, segue usando o token em memoria mesmo assim.
        try:
            if os.path.exists(temp):
                os.remove(temp)
        except OSError:
            pass


def _expirado(expires_ms, margem_seg=120):
    """Diz se o token ja expirou ou esta perto de expirar."""
    try:
        return (float(expires_ms) / 1000.0) - time.time() < margem_seg
    except (TypeError, ValueError):
        return True


def _refresh(refresh_token, scopes):
    """
    Renova o token OAuth usando o refresh_token.

    Retorna (access_token, refresh_token, expires_ms) ou None em caso de
    falha. O refresh_token rotaciona, por isso o novo precisa ser gravado.
    """
    if not refresh_token:
        return None

    corpo = json.dumps({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "scope": " ".join(scopes or []),
    }).encode("utf-8")

    req = urllib.request.Request(
        URL_TOKEN,
        data=corpo,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            dados = json.load(resp)
    except (urllib.error.URLError, json.JSONDecodeError, ValueError, OSError):
        return None

    access = dados.get("access_token")
    refresh = dados.get("refresh_token", refresh_token)
    expires_in = dados.get("expires_in")
    if not access:
        return None

    expires_ms = None
    if expires_in:
        expires_ms = int((time.time() + float(expires_in)) * 1000)

    return access, refresh, expires_ms


def _obter_token_valido():
    """
    Devolve um access token valido, renovando se necessario.

    Retorna (access_token, plano) ou (None, None) se nao for possivel.
    """
    cred = _ler_credenciais()
    if not isinstance(cred, dict):
        return None, None

    oauth = cred.get("claudeAiOauth")
    if not isinstance(oauth, dict):
        return None, None

    access = oauth.get("accessToken")
    plano = ROTULOS_PLANO.get(
        oauth.get("rateLimitTier"),
        (oauth.get("subscriptionType") or "").capitalize() or "Plano",
    )

    # Se o token esta valido, usa direto.
    if access and not _expirado(oauth.get("expiresAt")):
        return access, plano

    # Caso contrario, tenta renovar.
    resultado = _refresh(oauth.get("refreshToken"), oauth.get("scopes"))
    if resultado:
        novo_access, novo_refresh, novo_expires = resultado
        _gravar_token(novo_access, novo_refresh, novo_expires)
        return novo_access, plano

    # Refresh falhou: tenta o token atual mesmo (pode ainda funcionar).
    if access:
        return access, plano

    return None, plano


def _parte(secao):
    """Normaliza uma secao (five_hour, seven_day, ...) do retorno da API."""
    if not isinstance(secao, dict):
        return None
    util = secao.get("utilization")
    if util is None:
        return None
    return {
        "utilization": float(util),
        "resets_at": secao.get("resets_at"),
    }


def ler_limites(forcar=False):
    """
    Devolve os limites de uso do plano.

    Usa cache para nao chamar a rede com frequencia (ver INTERVALO_MIN_FETCH).
    Passe forcar=True para ignorar o cache (ex.: botao Atualizar).

    Estrutura retornada:
      {
        "ok": True,
        "plano": "Max (5x)",
        "sessao": {"utilization": 41.0, "resets_at": "..."} ou None,
        "semana": {...} ou None,
        "semana_sonnet": {...} ou None,
        "creditos": {"is_enabled":..., "monthly_limit":..., "used_credits":...,
                     "currency":...} ou None,
      }

    Em caso de falha:
      {"ok": False, "erro": "<mensagem curta>"}
    """
    agora = time.time()
    if (not forcar and _cache["resultado"] is not None
            and agora - _cache["momento"] < INTERVALO_MIN_FETCH):
        return _cache["resultado"]

    access, plano = _obter_token_valido()
    if not access:
        resultado = {
            "ok": False,
            "erro": "sem login do Claude Code",
        }
        _cache["resultado"] = resultado
        _cache["momento"] = agora
        return resultado

    req = urllib.request.Request(
        URL_USAGE,
        headers={
            "Authorization": "Bearer " + access,
            "anthropic-beta": ANTHROPIC_BETA,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            dados = json.load(resp)
    except urllib.error.HTTPError as erro:
        resultado = {"ok": False, "erro": "HTTP %s" % erro.code}
        _cache["resultado"] = resultado
        _cache["momento"] = agora
        return resultado
    except (urllib.error.URLError, OSError):
        resultado = {"ok": False, "erro": "sem conexao"}
        # Nao sobrescreve um resultado bom anterior por falha de rede passageira.
        if _cache["resultado"] is None:
            _cache["resultado"] = resultado
        _cache["momento"] = agora
        return _cache["resultado"]
    except (json.JSONDecodeError, ValueError):
        resultado = {"ok": False, "erro": "resposta invalida"}
        _cache["resultado"] = resultado
        _cache["momento"] = agora
        return resultado

    extra = dados.get("extra_usage")
    creditos = None
    if isinstance(extra, dict):
        creditos = {
            "is_enabled": extra.get("is_enabled"),
            "monthly_limit": extra.get("monthly_limit"),
            "used_credits": extra.get("used_credits"),
            "currency": extra.get("currency"),
        }

    resultado = {
        "ok": True,
        "plano": plano,
        "sessao": _parte(dados.get("five_hour")),
        "semana": _parte(dados.get("seven_day")),
        "semana_sonnet": _parte(dados.get("seven_day_sonnet")),
        "creditos": creditos,
    }
    _cache["resultado"] = resultado
    _cache["momento"] = agora
    return resultado


# Teste rapido: python usage_api.py
if __name__ == "__main__":
    print(json.dumps(ler_limites(forcar=True), indent=2, ensure_ascii=False))
