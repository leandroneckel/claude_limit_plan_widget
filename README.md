# Widget de Uso do Claude

Widget de desktop para Windows que mostra os **limites de uso do plano**
do Claude (os mesmos numeros da tela Configuracoes > Uso e do comando
`/usage`): sessao atual (janela de 5h), limites semanais e creditos de uso.
Fica sempre no topo, visivel em todos os desktops virtuais, fora da taskbar,
com icone no system tray.

App nativo em Python + PySide6, compilado em um executavel unico com PyInstaller.
Sem Docker, sem servico externo, sem dependencias web.

## Recursos

- Janela pequena, sem borda, cantos arredondados, caixa escura solida com borda.
- Sempre no topo, em qualquer desktop virtual, fora da taskbar.
- Mostra os limites do plano com barras de progresso coloridas:
  - **Sessao atual** (janela de 5h): % usado e quando reinicia.
  - **Semanal (todos os modelos)**: % usado e quando reinicia.
  - **Semanal (somente Sonnet)**: % usado.
  - **Creditos de uso**: gasto x limite (quando habilitado).
- Atualiza o tempo restante a cada 2 segundos e busca os dados na rede a
  cada 60 segundos (em uma thread, para nao travar a interface).
- Arrastavel com o mouse. A posicao persiste entre execucoes.
- Icone no system tray com menu: Mostrar/Ocultar, Atualizar agora,
  alternar Fonte, Resetar (modo tokens), Sair.
- Tratamento de erro: se nao houver login ou conexao, mostra "sem dados"
  com o motivo, em vez de quebrar.

## Instalacao em outra maquina Windows (usuario final)

O programa e um executavel unico. Voce nao precisa instalar Python nem nada
para usar: basta o arquivo `TokenWidget.exe`.

### Requisitos

- Windows 10 ou 11, 64 bits (x64). Nao e testado em Windows ARM.
- Para o modo padrao (limites do plano): ter o **Claude Code instalado e
  logado** nessa maquina, com uma conta Claude (assinatura). O widget
  reaproveita esse login (le `%USERPROFILE%\.claude\.credentials.json`).
  O limite e da sua conta, entao os numeros sao os mesmos em qualquer PC
  onde voce esteja logado.
- Acesso a internet (a `api.anthropic.com`).

Sem o login do Claude Code, o widget abre normalmente, mas o modo limites
mostra "sem dados (sem login do Claude Code)". As fontes em tokens tambem
dependem do Claude Code naquele PC; so a fonte "arquivo manual" funciona
sem ele.

### Passos

1. Baixe o `TokenWidget.exe` (veja a secao Releases do projeto no GitHub,
   ou compile voce mesmo conforme a secao "Como compilar o .exe").
2. Copie o `.exe` para qualquer pasta (ex.: `C:\Users\<voce>\Apps\`).
3. De dois cliques para abrir. O widget aparece no canto da tela e um icone
   surge no system tray.
4. Opcional: coloque para iniciar com o Windows (veja "Como iniciar junto
   com o Windows" mais abaixo).

Nao e preciso copiar a pasta `src`, o `.venv` nem mais nada: o `.exe` ja
contem tudo. Os arquivos de config e estado sao criados sozinhos no
`%USERPROFILE%` da maquina nova.

### Aviso do Windows na primeira execucao

Como o `.exe` nao tem assinatura digital, o Windows SmartScreen pode mostrar
"O Windows protegeu o seu computador". Clique em **Mais informacoes** e depois
em **Executar assim mesmo**. Alguns antivirus tambem podem alertar por se
tratar de um executavel empacotado com PyInstaller; e um falso positivo
comum desse tipo de empacotamento.

## De onde vem o numero

No modo padrao, o widget le os limites direto do backend da Anthropic,
o mesmo endpoint que o Claude Code usa no `/usage`:

- Usa o token OAuth ja salvo pelo Claude Code em
  `%USERPROFILE%\.claude\.credentials.json`.
- Chama `GET https://api.anthropic.com/api/oauth/usage`.
- Se o token estiver expirado, faz o refresh (igual ao Claude Code) e
  grava o token renovado de volta no arquivo de credenciais, para nao
  deslogar voce.

Tudo usa apenas as suas proprias credenciais locais, so para exibir o seu
proprio uso. Nada e enviado para terceiros. Para o modo limites funcionar,
voce precisa estar logado no Claude Code com uma conta Claude (assinatura).

## Fontes de dados

O widget tem tres fontes, alternaveis pelo menu do tray (item "Fonte: ...",
que cicla entre elas). A fonte fica salva na config (campo `fonte`).

1. **Limites do plano (`limites`, padrao)**: os limites de uso descritos
   acima. E o que aparece na imagem das Configuracoes.

2. **Tokens da sessao Claude (`claude`)**: le os transcripts que o Claude
   Code grava em `%USERPROFILE%\.claude\projects\...\*.jsonl`, soma o consumo
   de todas as mensagens do assistente da sessao ativa e mostra total de
   tokens e custo estimado em USD e BRL.

3. **Arquivo manual (`arquivo`)**: le de `%USERPROFILE%\.claude_tokens.json`,
   alimentado pela funcao `token_logger.registrar()` a partir do seu proprio
   script que chama a API.

> Observacao sobre "Resetar": so se aplica aos modos em tokens. No modo
> `claude` grava um ponto de partida (baseline) e o widget passa a mostrar o
> consumo a partir desse momento, na mesma sessao. No modo `arquivo` zera o
> arquivo. No modo `limites` nao se aplica (o uso do plano e controlado pela
> Anthropic e reinicia sozinho nas janelas de 5h e semanal).

## Estrutura

```
claude_token_win_tray/
  .venv/                 ambiente virtual (nao versionado)
  src/
    main.py              app, widget e tray
    usage_api.py         le os limites do plano (token OAuth + /api/oauth/usage)
    claude_session.py    le o consumo em tokens da sessao do Claude Code
    token_logger.py      funcao registrar() para uso externo (fonte manual)
    pricing.py           tabela de precos por modelo + calculo
    config.py            leitura/escrita de config (posicao, usd_brl, fonte)
  requirements.txt
  build.bat              compila com PyInstaller
  README.md
  .gitignore
```

## Arquivos de dados (no perfil do usuario)

- `%USERPROFILE%\.claude_tokens.json` : estado da sessao (contagens de tokens).
- `%USERPROFILE%\.claude_token_widget.json` : config do widget (posicao, cotacao).

Formato do estado:

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

## Como rodar em modo dev

1. Criar e ativar o venv:

   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   ```

2. Instalar dependencias:

   ```bat
   pip install -r requirements.txt
   ```

3. Rodar:

   ```bat
   python src\main.py
   ```

Para testar valores, edite manualmente `%USERPROFILE%\.claude_tokens.json`.
O widget reflete as mudancas em ate 2 segundos.

## Como compilar o .exe

Com o venv criado e as dependencias instaladas, rode:

```bat
build.bat
```

Isso gera `dist\TokenWidget.exe` (executavel unico, sem janela de terminal).
O `build.bat` usa o PyInstaller com as flags:

- `--onefile` : um unico arquivo .exe
- `--windowed` : sem janela de console preta
- `--name TokenWidget` : nome do executavel
- `--paths src` : para achar os modulos locais

O icone e gerado por codigo (um medidor com tres barras), nao precisa de
arquivo .ico.

## Como publicar no GitHub (para quem mantem o projeto)

O `.gitignore` ja exclui `dist/`, `build/`, `.venv/` e os arquivos locais de
config e credenciais. Isso e proposital: artefatos de build e dados pessoais
nao devem ir para o repositorio.

Para distribuir o executavel para outras pessoas:

1. Compile com `build.bat` (gera `dist\TokenWidget.exe`).
2. No GitHub, crie um **Release** e anexe o `TokenWidget.exe` como binario do
   release (em vez de commitar dentro do repositorio).
3. No README, aponte os usuarios para a pagina de Releases para baixar o
   `.exe` pronto.

Assim o codigo-fonte fica versionado e o binario fica disponivel para
download sem inchar o historico do git.

## Como iniciar junto com o Windows

1. Pressione `Win + R`, digite `shell:startup` e tecle Enter.
   Isso abre a pasta de inicializacao do usuario.
2. Crie um atalho para `dist\TokenWidget.exe` dentro dessa pasta
   (clique direito no .exe, Enviar para, Area de trabalho, e depois
   mova o atalho para a pasta de inicializacao, ou cole o atalho direto la).
3. No proximo login, o widget abre sozinho.

Para remover da inicializacao, apague o atalho dessa pasta.

## Como integrar com o seu script que chama a API

O modulo `token_logger.py` expoe a funcao `registrar(usage, model)`, que
acumula os tokens de forma incremental no arquivo de estado. Importe-o
no seu script:

```python
import sys
sys.path.insert(0, r"C:\Projetos\claude_token_win_tray\src")

from token_logger import registrar

# ... voce chama a API e recebe uma resposta ...
resposta = client.messages.create(...)

# Acumula o consumo desta chamada na sessao atual.
# Aceita o objeto usage do SDK ou um dicionario com os mesmos campos.
registrar(resposta.usage, model="claude-opus-4")
```

Campos esperados em `usage` (faltantes contam como zero):

- `input_tokens`
- `output_tokens`
- `cache_creation_input_tokens`
- `cache_read_input_tokens`

Tambem da para passar um dicionario direto:

```python
registrar({
    "input_tokens": 1200,
    "output_tokens": 350,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 800,
}, model="claude-opus-4")
```

Para zerar a sessao por codigo, use `token_logger.resetar_sessao()`
(o mesmo que a opcao Resetar no menu do tray).

## Precos e cotacao

A tabela de precos por modelo fica em `src\pricing.py`, em USD por milhao de
tokens, separada em input, output, cache write e cache read. Ajuste conforme a
tabela oficial vigente.

A cotacao USD para BRL e fixa, lida do campo `usd_brl` da config
(default 5.40). Nao e buscada online. Para mudar, edite
`%USERPROFILE%\.claude_token_widget.json` ou ajuste o default em
`src\config.py`.

## Menu do tray

- **Mostrar/Ocultar** : alterna a visibilidade do widget (clicar no icone
  do tray tambem alterna).
- **Atualizar agora** : forca uma releitura imediata (no modo limites,
  consulta a rede na hora).
- **Fonte: ...** : cicla entre as fontes (limites do plano, tokens da sessao
  Claude, arquivo manual).
- **Resetar (modo tokens)** : reseta as fontes em tokens (baseline no modo
  `claude`, zera o arquivo no modo `arquivo`). Nao se aplica ao modo limites.
- **Sair** : encerra o app.

## Aviso e privacidade

- Este projeto nao e oficial e nao tem vinculo com a Anthropic. Os nomes
  Claude e Anthropic pertencem aos seus donos.
- O modo limites usa um endpoint interno do Claude Code
  (`/api/oauth/usage`), que nao e uma API publica documentada. Ele pode
  mudar ou parar de funcionar em versoes futuras do Claude Code. Se isso
  acontecer, basta atualizar as constantes em `src\usage_api.py` (os outros
  modos continuam funcionando).
- O widget le as credenciais locais do Claude Code apenas na sua propria
  maquina, para exibir o seu proprio uso. Nada e enviado para terceiros: a
  unica comunicacao de rede e direto com os servidores da Anthropic
  (`api.anthropic.com` e `platform.claude.com`), exatamente como o Claude
  Code ja faz.
- Quando o token OAuth expira, o widget faz o refresh e grava o token
  renovado de volta em `%USERPROFILE%\.claude\.credentials.json`, igual ao
  proprio Claude Code, para nao deslogar voce. Esse arquivo nunca e copiado
  nem versionado.
- Use por sua conta e risco. Recomenda-se adicionar uma licenca de codigo
  aberto (por exemplo MIT) antes de publicar, criando um arquivo `LICENSE`
  na raiz do projeto.
