"""
pricing.py

Tabela de precos por modelo e funcao de calculo de custo.

Os precos estao em USD por milhao de tokens (1.000.000), separados em:
  - input        : tokens de entrada normais
  - output       : tokens de saida (geracao)
  - cache_write  : tokens gravados no cache (cache creation)
  - cache_read   : tokens lidos do cache (cache read)

Os valores abaixo sao aproximacoes publicas e podem ficar desatualizados.
Ajuste conforme a tabela oficial vigente do provedor.
"""

# Precos em USD por 1 milhao de tokens.
# Chave: nome (ou prefixo) do modelo. A busca tenta casar pelo inicio do nome.
PRECOS_POR_MODELO = {
    # Familia Opus
    "claude-opus-4": {
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50,
    },
    # Familia Sonnet
    "claude-sonnet-4": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    # Familia Haiku
    "claude-haiku-4": {
        "input": 1.00,
        "output": 5.00,
        "cache_write": 1.25,
        "cache_read": 0.10,
    },
}

# Preco usado quando o modelo informado nao casa com nenhuma entrada acima.
# Por seguranca, usamos o preco do Opus (mais alto) para nao subestimar custo.
PRECO_PADRAO = {
    "input": 15.00,
    "output": 75.00,
    "cache_write": 18.75,
    "cache_read": 1.50,
}


def obter_precos(model):
    """
    Retorna o dicionario de precos para o modelo informado.

    Faz uma busca por prefixo: se o nome do modelo comecar com uma das
    chaves conhecidas, usa aquela tabela. Caso contrario, usa PRECO_PADRAO.
    """
    if not model:
        return PRECO_PADRAO

    nome = str(model).lower()
    for prefixo, precos in PRECOS_POR_MODELO.items():
        if nome.startswith(prefixo):
            return precos

    return PRECO_PADRAO


def calcular_custo_usd(model, input_tokens, output_tokens,
                       cache_creation_tokens=0, cache_read_tokens=0):
    """
    Calcula o custo total em USD a partir das contagens de tokens.

    Cada categoria de token e multiplicada pelo seu preco por milhao
    e dividida por 1.000.000.
    """
    precos = obter_precos(model)

    custo = (
        input_tokens * precos["input"]
        + output_tokens * precos["output"]
        + cache_creation_tokens * precos["cache_write"]
        + cache_read_tokens * precos["cache_read"]
    ) / 1_000_000.0

    return custo


def calcular_custos(model, input_tokens, output_tokens,
                    cache_creation_tokens=0, cache_read_tokens=0, usd_brl=5.40):
    """
    Retorna uma tupla (custo_usd, custo_brl) ja convertida pela cotacao.

    A cotacao usd_brl vem da config e nao e buscada online.
    """
    usd = calcular_custo_usd(
        model, input_tokens, output_tokens,
        cache_creation_tokens, cache_read_tokens,
    )
    brl = usd * usd_brl
    return usd, brl
