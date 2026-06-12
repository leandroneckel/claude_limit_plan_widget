"""
config.py

Leitura e escrita da configuracao do widget.

A config guarda:
  - pos_x, pos_y : posicao da janela na tela (persistida entre execucoes)
  - usd_brl      : cotacao fixa USD para BRL (default 5.40)
  - provedor     : "claude" ou "codex"

O arquivo de config fica em:
  %USERPROFILE%\\.claude_token_widget.json

Observacao: a cotacao usd_brl e fixa e lida apenas da config.
Para atualizar, edite o arquivo de config ou troque o valor aqui no default
e apague a config existente. Nao e buscada cotacao online.
"""

import json
import os

# Caminho do arquivo de config dentro do diretorio do usuario.
CAMINHO_CONFIG = os.path.join(
    os.path.expanduser("~"), ".claude_token_widget.json"
)

# Valores padrao usados quando a config nao existe ou esta incompleta.
CONFIG_PADRAO = {
    "pos_x": 80,
    "pos_y": 80,
    "usd_brl": 5.40,  # cotacao fixa, ajuste manualmente quando precisar
    # Provedor dos limites e dos tokens da sessao. Claude continua sendo
    # o padrao para preservar o comportamento das versoes anteriores.
    "provedor": "claude",
    # Fonte dos dados:
    #   "limites" : limites de uso do plano (sessao 5h, semanal, creditos),
    #               igual a Configuracoes > Uso e ao /usage. E o padrao.
    #   "claude"  : consumo em tokens da sessao ativa do Claude Code
    #               (transcripts em %USERPROFILE%\.claude\projects)
    #   "arquivo" : le do arquivo manual %USERPROFILE%\.claude_tokens.json
    #               (alimentado por token_logger.registrar())
    "fonte": "limites",
    # Modo de exibicao:
    #   "widget"  : janela flutuante sempre no topo (padrao).
    #   "bandeja" : sem janela; o proprio icone do system tray mostra a
    #               % da sessao atual desenhada nele. Mais discreto.
    "exibicao": "widget",
    # Ponto de partida (baseline) para o botao Resetar no modo "claude".
    # Como nao da para apagar o transcript, guardamos aqui o consumo
    # no momento do reset e o widget passa a mostrar o delta a partir dai.
    # Estrutura: {"session_id": ..., "input_tokens": ..., ...}
    "baseline": None,
    # Baseline separado para os tokens da thread Codex.
    "baseline_codex": None,
}


def carregar_config():
    """
    Le a config do disco e devolve um dicionario completo.

    Se o arquivo nao existir ou estiver corrompido, devolve uma copia
    dos valores padrao, sem quebrar o app. Campos faltantes sao
    preenchidos com o padrao.
    """
    config = dict(CONFIG_PADRAO)

    try:
        with open(CAMINHO_CONFIG, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        if isinstance(dados, dict):
            # Sobrescreve apenas as chaves conhecidas e validas.
            for chave in CONFIG_PADRAO:
                if chave in dados:
                    config[chave] = dados[chave]
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        # Qualquer falha de leitura cai no padrao silenciosamente.
        pass

    return config


def salvar_config(config):
    """
    Grava o dicionario de config no disco em formato JSON.

    Em caso de erro de escrita, falha silenciosamente para nao
    derrubar o app (a posicao simplesmente nao sera persistida).
    """
    try:
        with open(CAMINHO_CONFIG, "w", encoding="utf-8") as arquivo:
            json.dump(config, arquivo, indent=2, ensure_ascii=False)
    except OSError:
        pass


def salvar_posicao(x, y):
    """
    Atalho para atualizar somente a posicao da janela, preservando
    o restante da config (como a cotacao).
    """
    config = carregar_config()
    config["pos_x"] = int(x)
    config["pos_y"] = int(y)
    salvar_config(config)
