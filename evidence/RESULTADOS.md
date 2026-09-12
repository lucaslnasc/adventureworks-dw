# Resultados verificados em 12/09/2026

Responsável pela execução registrada: revisão automatizada realizada pelo Codex a pedido do grupo. Não é registro de execução manual de um integrante.

A revisão executou o código atual em uma cópia isolada e consultou os bancos existentes. Os hashes dos arquivos testados estão em [validacao.json](validacao.json), campo `files_sha256`. A correção do erro 3964 e seu teste de regressão estão incluídos nesses hashes. O HEAD anterior `2f0bccb74bff032362fd02c9ea1657a844712fad` não contém essa correção e não identifica sozinho o código validado.

| Verificação | Resultado observado | Evidência |
|---|---|---|
| Suíte completa | 28 passed, 0 failed, 0 skipped; 9,90 s | [testes.txt](testes.txt) |
| Reconciliação | PASS; 121.317 itens em cada banco; zero divergências | [reconciliation.json](reconciliation.json) |
| Receita de todos os status | 109846381.399888 UM na origem; 109846381.39988800 UM no DW | reconciliation.json |
| Dimensões descritivas | Zero diferenças em produto, cliente, território e vendedor | validacao.json |
| Qualidade | Zero linhas nas três primeiras consultas | validacao.json |
| FKs da fato | Oito referências, todas validadas | validacao.json |
| Dez indicadores | Dez views; série mensal com 38 linhas | [kpis.json](kpis.json) |
| Carga inicial histórica | 121.317 extraídos/escritos; duração 0:00:02.609691 | validacao.json, audit |
| Incremental histórico bem-sucedido | Zero extraídos/escritos/excluídos; duração 0:00:00.045465 | validacao.json, audit |
| Checkpoint principal | Versão CT 0 | validacao.json |
| Extração incremental desta revisão | Zero fatos, pedidos afetados e membros dimensionais | validacao.json, incremental_read |
| Atualização, exclusão, SCD1 e rollback | Aprovados nas bases sintéticas dos testes | testes.txt |
| Demonstração manual no backup | Não executada nesta revisão | Cenários automatizados não substituem esta demonstração |

As novas exportações foram feitas às 15h41min53s (reconciliação) e 15h41min54s (indicadores), horário de Brasília/UTC-3. O artigo corrigido utiliza esses arquivos; as transcrições anteriores de 12h57 não são apresentadas como se fossem as mesmas exportações.

Ambiente: Python 3.13.5/Windows, pytest 9.1.1, psycopg 3.3.5, pymssql 2.4.1, PostgreSQL 17.11 e SQL Server 2022 16.0.4275.2/Linux. O Dockerfile declara Python 3.12. Build, nova restauração e digests das imagens não foram revalidados porque a API Docker ficou inacessível ao agente; o Compose passou em `config --quiet`. Os testes usaram bases novas isoladas, removidas ao término.

O histórico da instalação conserva falhas anteriores, seguidas de incremental bem-sucedido. A reconciliação real e os testes sintéticos são evidências distintas. A extração vazia desta revisão foi somente leitura; a estatística de escrita zero vem do histórico e dos testes.

O backup identificado em [origem.json](origem.json) tem 48.749.568 bytes e SHA-256 `e67fc550d4edd762b8f56c6904a68f5f552224fc375f65768eecc3a47e986315`. A origem estava ONLINE, snapshot ON, CT em dez tabelas e retenção de sete dias. Os dados foram lidos da instalação existente; a revisão não restaurou o arquivo novamente.

Para reproduzir, siga [GUIA_TESTES.md](../docs/GUIA_TESTES.md). Registre separadamente qualquer nova execução, preservando estas evidências até atualizar o artigo e sua identificação de revisão.
