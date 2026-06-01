"""
token_logger.py

Modulo auxiliar para gravar e acumular o consumo de tokens da sessao.

Qualquer script externo que chama a API pode importar a funcao registrar()
e somar tokens de forma incremental no arquivo de estado:

  %USERPROFILE%\\.claude_tokens.json

Exemplo de uso a partir de outro script:

    from token_logger import registrar

    # resposta da API contem o objeto usage
    registrar(resposta.usage, model="claude-opus-4")

A acumulacao e incremental: cada chamada soma aos totais existentes.
Os totais so voltam a zero quando resetar_sessao() for chamada
(ou ao usar a opcao Resetar no tray do widget).
"""

import json
import os
from datetime import datetime, timezone

# Caminho do arquivo de estado lido pelo widget.
CAMINHO_ESTADO = os.path.join(
    os.path.expanduser("~"), ".claude_tokens.json"
)

# Estrutura inicial de uma sessao zerada.
ESTADO_PADRAO = {
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_creation_tokens": 0,
    "cache_read_tokens": 0,
    "model": "claude-opus-4",
    "session_started": None,
}


def _agora_iso():
    """Retorna o horario atual em ISO 8601 com fuso local."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def carregar_estado():
    """
    Le o estado atual do disco.

    Se o arquivo nao existir ou estiver corrompido, devolve uma
    estrutura zerada (sem quebrar). Campos faltantes sao completados.
    """
    estado = dict(ESTADO_PADRAO)

    try:
        with open(CAMINHO_ESTADO, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        if isinstance(dados, dict):
            for chave in ESTADO_PADRAO:
                if chave in dados:
                    estado[chave] = dados[chave]
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        pass

    return estado


def salvar_estado(estado):
    """Grava o estado completo no disco em JSON."""
    try:
        with open(CAMINHO_ESTADO, "w", encoding="utf-8") as arquivo:
            json.dump(estado, arquivo, indent=2, ensure_ascii=False)
    except OSError:
        pass


def _extrair_contagens(usage):
    """
    Extrai as quatro contagens de tokens de um objeto ou dicionario usage.

    Aceita tanto um dicionario quanto um objeto com atributos
    (como o usage retornado pelo SDK da Anthropic). Campos ausentes
    contam como zero.
    """
    def pegar(nome):
        # Tenta como dicionario primeiro, depois como atributo de objeto.
        if isinstance(usage, dict):
            valor = usage.get(nome, 0)
        else:
            valor = getattr(usage, nome, 0)
        try:
            return int(valor or 0)
        except (TypeError, ValueError):
            return 0

    entrada = pegar("input_tokens")
    saida = pegar("output_tokens")
    cache_write = pegar("cache_creation_input_tokens")
    cache_read = pegar("cache_read_input_tokens")

    return entrada, saida, cache_write, cache_read


def registrar(usage, model=None):
    """
    Acumula o consumo de tokens informado no arquivo de estado.

    Parametros:
      usage : dicionario ou objeto com os campos
              input_tokens, output_tokens,
              cache_creation_input_tokens, cache_read_input_tokens
      model : nome do modelo usado (opcional). Se informado, atualiza
              o modelo registrado no estado.

    A soma e incremental: os novos valores sao adicionados aos totais
    ja existentes na sessao. Retorna o estado atualizado.
    """
    estado = carregar_estado()

    # Se a sessao ainda nao tinha inicio, marca agora.
    if not estado.get("session_started"):
        estado["session_started"] = _agora_iso()

    entrada, saida, cache_write, cache_read = _extrair_contagens(usage)

    estado["input_tokens"] = int(estado.get("input_tokens", 0)) + entrada
    estado["output_tokens"] = int(estado.get("output_tokens", 0)) + saida
    estado["cache_creation_tokens"] = (
        int(estado.get("cache_creation_tokens", 0)) + cache_write
    )
    estado["cache_read_tokens"] = (
        int(estado.get("cache_read_tokens", 0)) + cache_read
    )

    if model:
        estado["model"] = model

    salvar_estado(estado)
    return estado


def resetar_sessao(model=None):
    """
    Zera todos os contadores e inicia uma nova sessao.

    Mantem o modelo informado (ou o ultimo modelo conhecido) e
    grava o horario atual como inicio da sessao.
    """
    estado_anterior = carregar_estado()
    modelo = model or estado_anterior.get("model") or ESTADO_PADRAO["model"]

    estado = dict(ESTADO_PADRAO)
    estado["model"] = modelo
    estado["session_started"] = _agora_iso()

    salvar_estado(estado)
    return estado


# Permite testar rapidamente pelo terminal: python token_logger.py
if __name__ == "__main__":
    exemplo = {
        "input_tokens": 1200,
        "output_tokens": 350,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 800,
    }
    novo = registrar(exemplo, model="claude-opus-4")
    print("Estado atualizado:")
    print(json.dumps(novo, indent=2, ensure_ascii=False))
