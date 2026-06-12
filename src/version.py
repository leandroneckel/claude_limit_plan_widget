"""
version.py

Fonte unica da versao do widget.

Esta constante e embutida no executavel no momento do build (PyInstaller
inclui este modulo automaticamente). O proprio widget tambem le este mesmo
arquivo no GitHub (via raw.githubusercontent) para descobrir se ha uma
versao mais nova publicada -- ver updater.py.

Para publicar uma atualizacao:
  1. Incremente __version__ aqui (formato X.Y.Z).
  2. Faca commit e push para o branch main.
  3. Reconstrua o executavel (build.bat) e distribua.

Quem estiver com um .exe antigo vera "atualizacao disponivel" assim que
este numero no GitHub ficar maior que o embutido no exe dele.
"""

__version__ = "1.3.0"
