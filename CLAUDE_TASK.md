# Diretriz para o Claude Code: Widget de Consumo de Tokens

## Objetivo

Construir um app desktop para Windows que mostre o consumo de tokens da sessao atual, sempre visivel em primeiro plano em qualquer desktop virtual do Windows, com icone no system tray. O app deve ser compilado em um executavel unico (.exe) e desenvolvido em um virtualenv (venv), sem container.

## Stack obrigatoria

- Python 3.11+ em venv local (`.venv`)
- PySide6 para a GUI e tray
- PyInstaller para compilar o .exe
- Sem Docker, sem container, sem servico externo

## Comportamento do widget

1. Janela pequena, sem borda, cantos arredondados, fundo escuro semitransparente.
2. Flags de janela: `WindowStaysOnTopHint | FramelessWindowHint | Tool`, para ficar sempre no topo, aparecer em todos os desktops virtuais e nao ocupar a taskbar.
3. Mostra: tokens de entrada, tokens de saida, total da sessao e custo estimado em USD e BRL.
4. Atualiza a cada 2 segundos lendo um arquivo JSON de estado.
5. Arrastavel com o mouse (clicar e segurar para mover).
6. Posicao da janela persiste entre execucoes (salvar x, y em config).
7. Icone no system tray com menu: Mostrar/Ocultar, Resetar sessao, Sair.

## Fonte de dados

O widget le de um arquivo JSON em `%USERPROFILE%\.claude_tokens.json` com este formato:

```json
{
  "input_tokens": 0,
  "output_tokens": 0,
  "cache_creation_tokens": 0,
  "cache_read_tokens": 0,
  "model": "claude-opus-4",
  "session_started": "2026-06-01T13:30:00-03:00"
}
```

Crie tambem um modulo auxiliar `token_logger.py` com uma funcao `registrar(usage, model)` que qualquer script externo possa importar para gravar/acumular tokens nesse arquivo. A funcao deve somar de forma incremental (acumular na sessao), nao sobrescrever, exceto quando a sessao for resetada.

## Custos

Implemente uma tabela de precos por modelo (USD por milhao de tokens) em um dicionario configuravel, separando input, output, cache write e cache read. Use cotacao USD/BRL fixa lida de config (campo `usd_brl`, default 5.40) e deixe comentado que pode ser atualizada. Nao buscar cotacao online.

## Estrutura de arquivos esperada

```
token-widget/
  .venv/
  src/
    main.py            # app, widget, tray
    token_logger.py    # funcao registrar() para uso externo
    pricing.py         # tabela de precos por modelo + calculo
    config.py          # leitura/escrita de config (posicao, usd_brl)
  requirements.txt
  build.bat            # script que compila com PyInstaller
  README.md            # como rodar em dev e como compilar
  .gitignore
```

## Passos que o Claude Code deve executar

1. Criar a estrutura de pastas.
2. Criar e ativar o venv: `python -m venv .venv` e ativar.
3. Instalar dependencias: `pip install PySide6 pyinstaller` e gerar `requirements.txt`.
4. Escrever todo o codigo nos modulos acima, separando responsabilidades.
5. Testar rodando em modo dev: `python src/main.py`.
6. Criar `build.bat` que roda o PyInstaller com as flags corretas:
   - `--onefile` (executavel unico)
   - `--noconsole` / `--windowed` (sem janela de terminal preto)
   - `--name TokenWidget`
   - icone proprio se houver, senao gerar um icone simples por codigo
7. Rodar o build e confirmar que gera `dist/TokenWidget.exe`.
8. Validar que o .exe abre, fica em primeiro plano, mostra dados do JSON e o tray funciona.

## Requisitos de qualidade

- Codigo comentado em portugues nos pontos chave.
- Tratamento de erro se o JSON nao existir ou estiver corrompido (mostrar "sem dados", nao quebrar).
- Nada de `localStorage` ou dependencias web. App nativo puro.
- Sem em dashes (travessoes) em nenhum texto, comentario ou string. Usar virgulas, pontos ou dois pontos.
- README com instrucoes de:
  - como rodar em dev
  - como compilar
  - como colocar para iniciar com o Windows (atalho do .exe em `shell:startup`)
  - como integrar o `token_logger.registrar()` no script que chama a API

## Criterio de pronto

- `dist/TokenWidget.exe` existe e abre com dois cliques.
- Widget fica sempre no topo, visivel em todos os desktops virtuais, fora da taskbar.
- Tray funciona com Mostrar/Ocultar, Resetar, Sair.
- Valores e custos atualizam ao alterar o JSON manualmente.
- README permite reproduzir build e integracao do zero.
