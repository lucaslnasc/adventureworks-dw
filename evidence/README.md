# Evidências da execução

Esta pasta inclui as evidências revisadas que sustentam o artigo. Consulte [RESULTADOS.md](RESULTADOS.md) para contexto, horário, ambiente e limites dos testes.

- `reconciliation.json`: comparação item a item da origem e do DW.
- `kpis.json`: os dez indicadores e a série mensal completa.
- `validacao.json`: histórico, qualidade, FKs, comparação dimensional e hashes do código avaliado.
- `origem.json`: perfil do SQL Server, CT e identificação do backup.
- `catalogo_colunas.json`: catálogo usado para conferir o dicionário.
- `testes.txt`: saída dos 28 testes aprovados.

Esses JSONs possuem exceções explícitas no `.gitignore` para acompanhar a entrega. Os comandos `verify` e `report` sobrescrevem seus respectivos arquivos; preserve uma cópia antes de registrar outra execução. Atualize a identificação da evidência no artigo quando substituir os arquivos. Não publique `.env`, credenciais ou o backup.

O [guia de testes](../docs/GUIA_TESTES.md) descreve reprodução e demonstração opcional. Resultados sintéticos e reconciliação do AdventureWorks real têm escopos diferentes.
