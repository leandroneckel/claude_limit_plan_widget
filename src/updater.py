"""
updater.py

Verifica se ha uma versao mais nova do widget publicada no GitHub.

A "versao instalada" e a constante __version__ embutida no executavel
(arquivo version.py). A "versao mais recente" e lida do mesmo arquivo
version.py no branch main do repositorio, via raw.githubusercontent.

Fluxo:
  - GET https://raw.githubusercontent.com/<repo>/main/src/version.py
  - extrai __version__ por regex
  - compara as duas versoes (formato X.Y.Z)

Nao envia nada: e apenas um GET publico do arquivo de versao. A consulta
roda numa thread no main.py para nunca travar a interface.
"""

import re
import time
import urllib.error
import urllib.request

from version import __version__ as VERSAO_LOCAL

# Arquivo de versao no repositorio (branch main).
URL_VERSAO_REMOTA = (
    "https://raw.githubusercontent.com/"
    "leandroneckel/claude_limit_plan_widget/main/src/version.py"
)

# Pagina do projeto, para o usuario abrir e baixar a nova versao.
URL_PROJETO = "https://github.com/leandroneckel/claude_limit_plan_widget"

# Intervalo minimo entre verificacoes reais (segundos). 6 horas e suficiente:
# a checagem nao precisa ser frequente e assim nao incomoda o GitHub.
INTERVALO_MIN_CHECK = 6 * 3600

# Cache em memoria do ultimo resultado.
_cache = {"momento": 0.0, "resultado": None}


def _parse_versao(texto):
    """Extrai '1.2.3' de um trecho de version.py. Retorna str ou None."""
    achado = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', texto or "")
    return achado.group(1).strip() if achado else None


def _tupla(versao):
    """
    Converte '1.2.3' em (1, 2, 3) para comparar numericamente.
    Partes nao numericas viram 0 para nao quebrar a comparacao.
    """
    partes = []
    for p in str(versao).split("."):
        try:
            partes.append(int(p))
        except ValueError:
            partes.append(0)
    return tuple(partes)


def _mais_nova(remota, local):
    """True se 'remota' for estritamente maior que 'local'."""
    return _tupla(remota) > _tupla(local)


def verificar_atualizacao(forcar=False):
    """
    Verifica se ha versao mais nova no GitHub.

    Em sucesso:
      {"ok": True, "local": "1.1.0", "remota": "1.2.0",
       "tem_atualizacao": True/False}

    Em falha:
      {"ok": False, "local": "1.1.0", "erro": "<mensagem curta>"}

    Usa cache (INTERVALO_MIN_CHECK) para nao consultar a rede com frequencia.
    Passe forcar=True para ignorar o cache (ex.: item de menu "Verificar").
    """
    agora = time.time()
    if (not forcar and _cache["resultado"] is not None
            and agora - _cache["momento"] < INTERVALO_MIN_CHECK):
        return _cache["resultado"]

    req = urllib.request.Request(
        URL_VERSAO_REMOTA,
        headers={"User-Agent": "ClaudeUsageWidget"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            texto = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError):
        # Falha de rede passageira: nao apaga um bom resultado anterior.
        if _cache["resultado"] is not None and _cache["resultado"].get("ok"):
            return _cache["resultado"]
        resultado = {"ok": False, "local": VERSAO_LOCAL, "erro": "sem conexao"}
        _cache["resultado"] = resultado
        _cache["momento"] = agora
        return resultado

    remota = _parse_versao(texto)
    if not remota:
        resultado = {
            "ok": False,
            "local": VERSAO_LOCAL,
            "erro": "versao remota ilegivel",
        }
        _cache["resultado"] = resultado
        _cache["momento"] = agora
        return resultado

    resultado = {
        "ok": True,
        "local": VERSAO_LOCAL,
        "remota": remota,
        "tem_atualizacao": _mais_nova(remota, VERSAO_LOCAL),
    }
    _cache["resultado"] = resultado
    _cache["momento"] = agora
    return resultado


# Teste rapido: python updater.py
if __name__ == "__main__":
    import json
    print(json.dumps(verificar_atualizacao(forcar=True), indent=2,
                     ensure_ascii=False))
