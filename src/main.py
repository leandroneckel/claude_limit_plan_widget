"""
main.py

Aplicacao principal: widget flutuante de uso + icone no system tray.

O widget fica sempre no topo, em todos os desktops virtuais e fora da
taskbar, com fundo escuro semitransparente e cantos arredondados.

Tem tres fontes de dados, alternaveis pelo menu do tray:

  1. "limites" (padrao): limites de uso do plano, igual a tela
     Configuracoes > Uso e ao /usage do Claude Code. Mostra:
       - Sessao atual (janela de 5h): % usado e quando reinicia
       - Semanal (todos os modelos): % usado e quando reinicia
       - Semanal (somente Sonnet): % usado
       - Creditos de uso (gasto extra)
     A chamada de rede roda em uma thread separada para nao travar a UI.

  2. "claude": consumo em tokens da sessao ativa do Claude Code
     (somado dos transcripts) com custo estimado em USD e BRL.

  3. "arquivo": consumo do arquivo manual %USERPROFILE%\\.claude_tokens.json
     alimentado por token_logger.registrar().

Para rodar em modo dev:
    python src/main.py
"""

import sys
import threading
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer, QPoint, QSharedMemory, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtGui import (
    QAction,
    QColor,
    QGuiApplication,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMenu,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

import claude_session
import config
import pricing
import token_logger
import updater
import usage_api
import version

# Ordem de alternancia das fontes no menu do tray.
FONTES = ["limites", "claude", "arquivo"]

# Rotulos amigaveis das fontes.
ROTULO_FONTE = {
    "limites": "Limites do plano",
    "claude": "Tokens da sessao Claude",
    "arquivo": "Arquivo manual",
}


def gerar_icone():
    """
    Gera um icone simples por codigo (sem precisar de arquivo .ico).

    Desenha um quadrado arredondado azul com tres barrinhas brancas de
    larguras diferentes, lembrando um medidor de uso. Retorna um QIcon.
    """
    tamanho = 64
    pixmap = QPixmap(tamanho, tamanho)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Fundo arredondado.
    painter.setBrush(QColor(30, 120, 200))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(4, 4, tamanho - 8, tamanho - 8, 12, 12)

    # Tres barras de uso, larguras diferentes.
    painter.setBrush(QColor(255, 255, 255))
    larguras = [40, 28, 34]
    y = 18
    for largura in larguras:
        painter.drawRoundedRect(14, y, largura, 7, 3, 3)
        y += 13

    painter.end()
    return QIcon(pixmap)


class TokenWidget(QWidget):
    """Janela flutuante que exibe o uso conforme a fonte configurada."""

    # Emitido (na main thread) quando a checagem de versao no GitHub termina.
    # Carrega o dict de updater.verificar_atualizacao() acrescido de "_manual".
    versao_verificada = Signal(dict)

    def __init__(self):
        super().__init__()

        # Carrega config (posicao, cotacao, fonte).
        self.config = config.carregar_config()

        # Controle de arrasto da janela com o mouse.
        self._arrastando = False
        self._offset_arrasto = QPoint()

        # Ultimo resultado de limites obtido pela thread de rede.
        self._ultimo_limites = None
        # Ultimo resultado da checagem de versao no GitHub.
        self._info_versao = None
        self._lock = threading.Lock()
        self._parar = threading.Event()

        self._montar_janela()
        self._montar_layout()
        self._iniciar_thread_limites()
        self._iniciar_timer()

        # Primeira atualizacao imediata.
        self.atualizar_dados()

    def _montar_janela(self):
        """Configura flags, transparencia e posicao da janela."""
        # WindowStaysOnTopHint: sempre no topo.
        # FramelessWindowHint: sem borda.
        # Tool: nao aparece na taskbar e ajuda a estar em todos os desktops.
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint
            | Qt.FramelessWindowHint
            | Qt.Tool
        )
        # Fundo translucido para desenharmos os cantos arredondados.
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.setFixedWidth(250)

        # Posicao persistida, mas garantindo que caia em uma tela visivel
        # (a posicao salva pode ter ficado fora da area apos trocar de
        # monitor ou resolucao).
        x, y = self._posicao_visivel(
            int(self.config.get("pos_x", 80)),
            int(self.config.get("pos_y", 80)),
        )
        self.move(x, y)

    def _posicao_visivel(self, x, y):
        """
        Ajusta (x, y) para que a janela fique dentro da area visivel de
        algum monitor. Se a posicao salva estiver fora de qualquer tela
        (ex.: monitor removido), reposiciona na tela primaria.

        Retorna a tupla (x, y) ja corrigida.
        """
        # Tamanho estimado da janela. Antes de mostrar, sizeHint() ja da
        # uma boa referencia; usamos a largura fixa de 250 como minimo.
        larg = max(self.width(), self.sizeHint().width(), 250)
        alt = max(self.height(), self.sizeHint().height(), 80)

        # Procura uma tela que contenha o canto superior esquerdo.
        tela = QGuiApplication.screenAt(QPoint(x, y))
        if tela is None:
            tela = QGuiApplication.primaryScreen()
        if tela is None:
            return x, y

        area = tela.availableGeometry()

        # Garante que a janela inteira caiba dentro da area disponivel.
        max_x = area.right() - larg + 1
        max_y = area.bottom() - alt + 1
        x = min(max(x, area.left()), max(area.left(), max_x))
        y = min(max(y, area.top()), max(area.top(), max_y))
        return x, y

    def _montar_layout(self):
        """Cria o titulo e o corpo (texto rico) do widget."""
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        self.label_titulo = QLabel("Uso")
        self.label_titulo.setStyleSheet(
            "color: #9ad0ff; font-weight: bold; font-size: 12px;"
        )

        # Corpo em texto rico (HTML), fonte monoespacada para alinhar barras.
        self.label_corpo = QLabel("carregando...")
        self.label_corpo.setTextFormat(Qt.RichText)
        self.label_corpo.setWordWrap(True)
        self.label_corpo.setStyleSheet(
            "color: #e6e6e6; font-family: Consolas, 'Courier New', monospace;"
            " font-size: 11px;"
        )

        # Rodape com a versao instalada (e aviso de atualizacao, se houver).
        self.label_versao = QLabel("")
        self.label_versao.setTextFormat(Qt.RichText)
        self.label_versao.setStyleSheet("font-size: 9px;")

        layout.addWidget(self.label_titulo)
        layout.addWidget(self.label_corpo)
        layout.addWidget(self.label_versao)
        self.setLayout(layout)

    def _iniciar_timer(self):
        """Atualiza o display a cada 2 segundos (so leitura local/cache)."""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.atualizar_dados)
        self.timer.start(2000)

    def _iniciar_thread_limites(self):
        """
        Inicia uma thread que busca os limites na rede periodicamente.

        Assim a chamada HTTP nunca trava a interface. O resultado fica
        guardado e o display apenas le esse valor (recalculando o tempo
        para reiniciar localmente a cada 2s).
        """
        def loop():
            while not self._parar.is_set():
                try:
                    resultado = usage_api.ler_limites(forcar=True)
                except Exception:
                    resultado = {"ok": False, "erro": "falha interna"}
                with self._lock:
                    self._ultimo_limites = resultado
                # Espera o intervalo, mas acorda na hora se for encerrar.
                self._parar.wait(usage_api.INTERVALO_MIN_FETCH)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def verificar_versao(self, forcar=False):
        """
        Verifica em background se ha versao mais nova no GitHub.

        A consulta HTTP roda numa thread para nao travar a UI; ao terminar,
        guarda o resultado e emite o sinal versao_verificada (entregue na
        main thread, onde e seguro mexer no tray e mostrar balao).
        """
        def tarefa():
            try:
                info = dict(updater.verificar_atualizacao(forcar=forcar))
            except Exception:
                info = {"ok": False, "erro": "falha interna",
                        "local": version.__version__}
            info["_manual"] = forcar
            with self._lock:
                self._info_versao = info
            self.versao_verificada.emit(info)

        threading.Thread(target=tarefa, daemon=True).start()

    def _texto_versao(self):
        """Monta o texto do rodape com a versao e o aviso de atualizacao."""
        with self._lock:
            info = self._info_versao
        rotulo = "v%s" % version.__version__
        if (isinstance(info, dict) and info.get("ok")
                and info.get("tem_atualizacao")):
            return (
                '<span style="color:#FFD27C">%s &#8226; atualizacao %s '
                'disponivel</span>' % (rotulo, info.get("remota"))
            )
        return '<span style="color:#6a6f7a">%s</span>' % rotulo

    def parar(self):
        """Sinaliza para a thread de rede encerrar."""
        self._parar.set()

    def paintEvent(self, event):
        """
        Desenha a caixa de fundo com cantos arredondados e uma borda sutil.

        Como a janela usa fundo translucido, e aqui que o cartao e
        efetivamente pintado. Usamos um fundo bem opaco para o texto de
        tras (outras janelas) nao vazar e atrapalhar a leitura.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Recua 1px para a borda nao ser cortada nas bordas da janela.
        area = self.rect().adjusted(1, 1, -1, -1)
        caminho = QPainterPath()
        caminho.addRoundedRect(area, 14, 14)

        # Fundo escuro quase opaco (alpha alto = caixa solida).
        painter.fillPath(caminho, QColor(24, 26, 32, 250))

        # Borda fina para delimitar bem o cartao.
        caneta = QPen(QColor(80, 90, 110))
        caneta.setWidth(1)
        painter.setPen(caneta)
        painter.drawPath(caminho)
        painter.end()

    # ----- Helpers de formatacao -----

    def _barra_html(self, pct, largura=16):
        """Monta uma barra de progresso em blocos coloridos (HTML)."""
        try:
            pct = max(0.0, min(100.0, float(pct)))
        except (TypeError, ValueError):
            pct = 0.0
        cheios = int(round(pct / 100.0 * largura))
        vazios = largura - cheios

        if pct < 50:
            cor = "#4CAF50"   # verde
        elif pct < 80:
            cor = "#FFC107"   # amarelo
        else:
            cor = "#FF5252"   # vermelho

        return (
            '<span style="color:%s">%s</span>'
            '<span style="color:#444">%s</span>'
            % (cor, "&#9608;" * cheios, "&#9608;" * vazios)
        )

    def _tempo_restante(self, iso):
        """Converte um instante ISO em texto tipo 'reinicia em 1h 23min'."""
        if not iso:
            return ""
        try:
            dt = datetime.fromisoformat(iso)
        except (ValueError, TypeError):
            return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        seg = int((dt - datetime.now(timezone.utc)).total_seconds())
        if seg <= 0:
            return "reinicia agora"

        dias = seg // 86400
        horas = (seg % 86400) // 3600
        mins = (seg % 3600) // 60
        if dias > 0:
            return "reinicia em %dd %dh" % (dias, horas)
        if horas > 0:
            return "reinicia em %dh %dmin" % (horas, mins)
        return "reinicia em %dmin" % mins

    def _formatar(self, numero):
        """Formata inteiros com separador de milhar (ponto, estilo BR)."""
        try:
            return f"{int(numero):,}".replace(",", ".")
        except (TypeError, ValueError):
            return "0"

    # ----- Renderizacao por fonte -----

    def _render_limites(self):
        """Monta titulo e corpo para a fonte de limites do plano."""
        with self._lock:
            dados = self._ultimo_limites

        if dados is None:
            return "Limites de uso", "carregando..."

        if not dados.get("ok"):
            return (
                "Limites de uso",
                '<span style="color:#FFB0B0">sem dados<br>(%s)</span>'
                % dados.get("erro", "indisponivel"),
            )

        titulo = "Limites de uso  %s" % dados.get("plano", "")
        linhas = []

        def bloco(rotulo, secao, mostrar_reset=True):
            if not secao:
                linhas.append(
                    '<b>%s</b><br><span style="color:#888">sem dados</span>'
                    % rotulo
                )
                return
            pct = secao.get("utilization", 0)
            reset = (
                self._tempo_restante(secao.get("resets_at"))
                if mostrar_reset else ""
            )
            # Qt rich text nao suporta float:right, entao a % fica inline.
            cabecalho = (
                '<b>%s</b>&nbsp;&nbsp;'
                '<span style="color:#ffffff"><b>%d%%</b></span>'
                % (rotulo, round(pct))
            )
            linha_barra = self._barra_html(pct)
            if reset:
                linha_barra += (
                    '<br><span style="color:#9a9a9a; font-size:10px">%s</span>'
                    % reset
                )
            linhas.append("%s<br>%s" % (cabecalho, linha_barra))

        bloco("Sessao atual", dados.get("sessao"))
        bloco("Semanal (todos)", dados.get("semana"))
        bloco("Semanal Sonnet", dados.get("semana_sonnet"), mostrar_reset=False)

        # Creditos de uso, se habilitados.
        creditos = dados.get("creditos")
        if creditos and creditos.get("is_enabled"):
            moeda = creditos.get("currency", "")
            usado = creditos.get("used_credits", 0) or 0
            limite = creditos.get("monthly_limit", 0) or 0
            linhas.append(
                '<b>Creditos</b><br>'
                '<span style="color:#FFD27C">%s %s / %s</span>'
                % (moeda, self._num(usado), self._num(limite))
            )

        corpo = '<div style="line-height:135%">' + "<br><br>".join(linhas) + "</div>"
        return titulo, corpo

    def _num(self, valor):
        """Formata numero monetario simples (sem casas se inteiro)."""
        try:
            f = float(valor)
        except (TypeError, ValueError):
            return "0"
        if f == int(f):
            return self._formatar(int(f))
        return ("%.2f" % f)

    def _render_tokens(self, estado):
        """Monta titulo e corpo para as fontes em tokens (claude/arquivo)."""
        entrada = int(estado.get("input_tokens", 0))
        saida = int(estado.get("output_tokens", 0))
        cache_write = int(estado.get("cache_creation_tokens", 0))
        cache_read = int(estado.get("cache_read_tokens", 0))
        modelo = estado.get("model", "?")
        total = entrada + saida + cache_write + cache_read

        usd_brl = float(self.config.get("usd_brl", 5.40))
        custo_usd, custo_brl = pricing.calcular_custos(
            modelo, entrada, saida, cache_write, cache_read, usd_brl
        )

        corpo = (
            'modelo: %s<br>'
            'entrada: %s<br>'
            'saida: %s<br>'
            'cache: %s<br>'
            '<b>total: %s</b><br>'
            '<span style="color:#7CFC9B"><b>USD: %.4f</b></span><br>'
            '<span style="color:#FFD27C"><b>BRL: %.4f</b></span>'
            % (
                modelo,
                self._formatar(entrada),
                self._formatar(saida),
                self._formatar(cache_write + cache_read),
                self._formatar(total),
                custo_usd,
                custo_brl,
            )
        )
        return "Consumo de tokens", corpo

    def _ler_estado_tokens(self):
        """Le o estado de tokens conforme a fonte (claude ou arquivo)."""
        fonte = self.config.get("fonte", "limites")

        if fonte == "claude":
            estado = claude_session.ler_sessao_ativa()
            if estado is None:
                return dict(token_logger.ESTADO_PADRAO)
            baseline = self.config.get("baseline")
            if (
                isinstance(baseline, dict)
                and baseline.get("session_id")
                and baseline.get("session_id") == estado.get("session_id")
            ):
                for chave in (
                    "input_tokens", "output_tokens",
                    "cache_creation_tokens", "cache_read_tokens",
                ):
                    estado[chave] = max(
                        0,
                        int(estado.get(chave, 0)) - int(baseline.get(chave, 0)),
                    )
            return estado

        return token_logger.carregar_estado()

    def atualizar_dados(self):
        """Le a fonte atual e atualiza titulo e corpo do widget."""
        fonte = self.config.get("fonte", "limites")

        if fonte == "limites":
            titulo, corpo = self._render_limites()
        else:
            estado = self._ler_estado_tokens()
            sem_dados = (
                not estado.get("session_started")
                and int(estado.get("input_tokens", 0)) == 0
                and int(estado.get("output_tokens", 0)) == 0
                and int(estado.get("cache_creation_tokens", 0)) == 0
                and int(estado.get("cache_read_tokens", 0)) == 0
            )
            if sem_dados:
                titulo, corpo = "Consumo de tokens", (
                    '<span style="color:#FFB0B0">sem dados</span>'
                )
            else:
                titulo, corpo = self._render_tokens(estado)

        self.label_titulo.setText(titulo)
        self.label_corpo.setText(corpo)
        self.label_versao.setText(self._texto_versao())

        # Ajusta a altura ao conteudo, mantendo largura fixa.
        self.adjustSize()
        self.setFixedWidth(250)

    # ----- Arrasto da janela com o mouse -----

    def mousePressEvent(self, event):
        """Inicia o arrasto ao clicar com o botao esquerdo."""
        if event.button() == Qt.LeftButton:
            self._arrastando = True
            self._offset_arrasto = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event):
        """Move a janela enquanto o botao esquerdo estiver pressionado."""
        if self._arrastando and (event.buttons() & Qt.LeftButton):
            nova_pos = event.globalPosition().toPoint() - self._offset_arrasto
            self.move(nova_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        """Finaliza o arrasto e salva a nova posicao na config."""
        if event.button() == Qt.LeftButton and self._arrastando:
            self._arrastando = False
            config.salvar_posicao(self.x(), self.y())
            event.accept()


class Aplicacao:
    """Junta o widget, o tray e o menu em uma unica aplicacao."""

    def __init__(self):
        self.app = QApplication(sys.argv)
        # Nao encerra quando a janela e ocultada (so pelo menu Sair).
        self.app.setQuitOnLastWindowClosed(False)

        # Instancia unica: se ja houver um widget rodando, sai.
        # Evita varias instancias consultando o endpoint e tomando 429.
        self._shm = QSharedMemory("ClaudeUsageWidget_SingleInstance")
        if not self._shm.create(1):
            # Outra instancia ja segura o segmento de memoria.
            sys.exit(0)

        self.icone = gerar_icone()

        # Para nao repetir o balao de "atualizacao disponivel" a cada checagem.
        self._avisou_atualizacao = False

        self.widget = TokenWidget()
        self.widget.setWindowIcon(self.icone)
        self.widget.versao_verificada.connect(self._on_versao)
        self.widget.show()

        self._montar_tray()

        # Checagem de versao no startup (roda em background).
        self.widget.verificar_versao()

    def _montar_tray(self):
        """Cria o icone do system tray com o menu de acoes."""
        self.tray = QSystemTrayIcon(self.icone)
        self.tray.setToolTip("Widget de Uso do Claude")

        menu = QMenu()

        acao_mostrar = QAction("Mostrar/Ocultar", menu)
        acao_mostrar.triggered.connect(self.alternar_visibilidade)
        menu.addAction(acao_mostrar)

        acao_atualizar = QAction("Atualizar agora", menu)
        acao_atualizar.triggered.connect(self.atualizar_agora)
        menu.addAction(acao_atualizar)

        self.acao_fonte = QAction("Fonte: ...", menu)
        self.acao_fonte.triggered.connect(self.alternar_fonte)
        menu.addAction(self.acao_fonte)
        self._atualizar_rotulo_fonte()

        acao_resetar = QAction("Resetar (modo tokens)", menu)
        acao_resetar.triggered.connect(self.resetar)
        menu.addAction(acao_resetar)

        menu.addSeparator()

        acao_atualizacao = QAction("Verificar atualizacao", menu)
        acao_atualizacao.triggered.connect(self.verificar_atualizacao_agora)
        menu.addAction(acao_atualizacao)

        acao_projeto = QAction("Abrir pagina do projeto", menu)
        acao_projeto.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl(updater.URL_PROJETO))
        )
        menu.addAction(acao_projeto)

        menu.addSeparator()

        acao_sair = QAction("Sair", menu)
        acao_sair.triggered.connect(self.sair)
        menu.addAction(acao_sair)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, motivo):
        """Alterna a janela ao clicar no icone (fora do menu de contexto)."""
        if motivo == QSystemTrayIcon.Trigger:
            self.alternar_visibilidade()

    def _atualizar_rotulo_fonte(self):
        """Atualiza o texto do item de menu com a fonte atual e a proxima."""
        fonte = self.widget.config.get("fonte", "limites")
        idx = FONTES.index(fonte) if fonte in FONTES else 0
        proxima = FONTES[(idx + 1) % len(FONTES)]
        self.acao_fonte.setText(
            "Fonte: %s (trocar p/ %s)"
            % (ROTULO_FONTE[fonte], ROTULO_FONTE[proxima])
        )

    def alternar_fonte(self):
        """Cicla entre as fontes: limites, claude, arquivo."""
        fonte = self.widget.config.get("fonte", "limites")
        idx = FONTES.index(fonte) if fonte in FONTES else 0
        nova = FONTES[(idx + 1) % len(FONTES)]
        self.widget.config["fonte"] = nova
        config.salvar_config(self.widget.config)
        self._atualizar_rotulo_fonte()
        self.widget.atualizar_dados()

    def atualizar_agora(self):
        """Forca uma releitura imediata (inclui rede no modo limites)."""
        fonte = self.widget.config.get("fonte", "limites")
        if fonte == "limites":
            resultado = usage_api.ler_limites(forcar=True)
            with self.widget._lock:
                self.widget._ultimo_limites = resultado
        self.widget.atualizar_dados()

    def resetar(self):
        """
        Reseta a sessao nas fontes em tokens.

        - "claude": grava um baseline (nao da para apagar o transcript) e
          o widget passa a mostrar o consumo a partir desse ponto.
        - "arquivo": zera o arquivo de estado manual.
        - "limites": nao se aplica (o uso do plano e controlado pela Anthropic).
        """
        fonte = self.widget.config.get("fonte", "limites")

        if fonte == "claude":
            atual = claude_session.ler_sessao_ativa()
            if atual:
                self.widget.config["baseline"] = {
                    "session_id": atual.get("session_id"),
                    "input_tokens": int(atual.get("input_tokens", 0)),
                    "output_tokens": int(atual.get("output_tokens", 0)),
                    "cache_creation_tokens": int(
                        atual.get("cache_creation_tokens", 0)
                    ),
                    "cache_read_tokens": int(atual.get("cache_read_tokens", 0)),
                }
                config.salvar_config(self.widget.config)
        elif fonte == "arquivo":
            token_logger.resetar_sessao()

        self.widget.atualizar_dados()

    def verificar_atualizacao_agora(self):
        """Forca uma checagem de versao no GitHub (item de menu)."""
        self.widget.verificar_versao(forcar=True)

    def _on_versao(self, info):
        """
        Reage ao resultado da checagem de versao (rodando na main thread).

        Atualiza o tooltip do tray e mostra um balao quando ha atualizacao
        (uma vez no modo automatico; sempre quando o usuario pede pelo menu).
        """
        if not isinstance(info, dict):
            return
        manual = info.get("_manual")

        if info.get("ok"):
            if info.get("tem_atualizacao"):
                self.tray.setToolTip(
                    "Widget de Uso do Claude - atualizacao %s disponivel"
                    % info.get("remota")
                )
                if manual or not self._avisou_atualizacao:
                    self.tray.showMessage(
                        "Atualizacao disponivel",
                        "Versao %s no GitHub (voce tem %s). Abra a pagina do "
                        "projeto para baixar."
                        % (info.get("remota"), info.get("local")),
                        QSystemTrayIcon.Information,
                        8000,
                    )
                    self._avisou_atualizacao = True
            else:
                self.tray.setToolTip(
                    "Widget de Uso do Claude - v%s (atualizado)"
                    % info.get("local")
                )
                if manual:
                    self.tray.showMessage(
                        "Tudo certo",
                        "Voce ja esta na versao mais recente (%s)."
                        % info.get("local"),
                        QSystemTrayIcon.Information,
                        5000,
                    )
        elif manual:
            self.tray.showMessage(
                "Nao foi possivel verificar",
                info.get("erro", "erro desconhecido"),
                QSystemTrayIcon.Warning,
                5000,
            )

    def alternar_visibilidade(self):
        """Mostra ou oculta o widget."""
        if self.widget.isVisible():
            self.widget.hide()
        else:
            # Reposiciona em tela visivel antes de mostrar, para o caso de
            # a janela ter ficado fora da area (monitor removido etc.).
            x, y = self.widget._posicao_visivel(self.widget.x(), self.widget.y())
            self.widget.move(x, y)
            self.widget.show()
            self.widget.raise_()
            self.widget.activateWindow()

    def sair(self):
        """Encerra a aplicacao."""
        self.widget.parar()
        self.tray.hide()
        self.app.quit()

    def executar(self):
        """Inicia o loop de eventos do Qt."""
        return self.app.exec()


def main():
    aplicacao = Aplicacao()
    sys.exit(aplicacao.executar())


if __name__ == "__main__":
    main()
