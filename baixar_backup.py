"""Baixa o backup oficial, sem substituir um arquivo já existente."""

from http.client import HTTPException
import os
from pathlib import Path
import tempfile
from urllib.request import urlopen

# Endereço oficial fixo; o arquivo final fica na pasta backups do projeto.
URL = "https://github.com/Microsoft/sql-server-samples/releases/download/adventureworks/AdventureWorks2016.bak"
DESTINO = Path(__file__).resolve().parent / "backups" / "AdventureWorks2016.bak"


# Baixa para arquivo temporário e só publica o nome final após completar a transferência.
def main():
    temporario = None
    status = 0
    try:
        # Preserva arquivo existente, sem afirmar que seu conteúdo está íntegro.
        if DESTINO.exists():
            print(f"Arquivo existente preservado: {DESTINO}. Integridade não verificada.")
            return 0
        DESTINO.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(URL, timeout=60) as resposta:
            tipo = resposta.headers.get("Content-Type", "").lower()
            if resposta.status != 200 or "html" in tipo or "json" in tipo:
                raise ValueError("O servidor não retornou o arquivo de backup esperado.")
            tamanho = resposta.headers.get("Content-Length")
            esperado = int(tamanho) if tamanho is not None else None
            recebido = 0
            with tempfile.NamedTemporaryFile(
                dir=DESTINO.parent, prefix="AdventureWorks2016-", suffix=".partial", delete=False
            ) as arquivo:
                temporario = Path(arquivo.name)
                # Streaming em blocos de 1 MiB evita manter todo o backup na memória.
                while bloco := resposta.read(1024 * 1024):
                    arquivo.write(bloco)
                    recebido += len(bloco)
                    print(f"\rBaixados: {recebido / 1024**2:.1f} MiB", end="", flush=True)
            # O tamanho detecta transferência incompleta; não substitui validação do backup.
            if recebido == 0 or (esperado is not None and recebido != esperado):
                raise ValueError("Transferência vazia ou tamanho diferente do informado pelo servidor.")
        # Publica sem sobrescrever um destino criado durante o download por outro processo.
        # Ambas as operações falham se outro processo já criou o destino.
        if os.name == "nt":
            os.rename(temporario, DESTINO)
        else:
            os.link(temporario, DESTINO)
        print(f"\nTransferência concluída: {DESTINO}")
        print("O conteúdo do backup será verificado pelo SQL Server durante a restauração.")
    except KeyboardInterrupt:
        print("\nDownload interrompido.")
        status = 130
    except (OSError, HTTPException, ValueError) as erro:
        print(f"\nNão foi possível concluir o download: {erro}")
        status = 1
    # A limpeza ocorre também em falha ou interrupção; remove apenas o temporário desta execução.
    finally:
        if temporario is not None:
            try:
                temporario.unlink(missing_ok=True)
            except OSError:
                print(f"Não foi possível remover o arquivo temporário: {temporario}")
                status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
