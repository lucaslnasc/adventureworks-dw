# AdventureWorks DW de vendas

Projeto acadêmico de modelagem dimensional e ETL incremental: **AdventureWorks2016 completo no SQL Server 2022 → Python 3.12 com Change Tracking → modelo estrela no PostgreSQL 17**.

Repositório: https://github.com/lucaslnasc/adventureworks-dw

[Artigo final em PDF](docs/artigo_unisales_adventureworks.pdf) | [Resultados verificados](evidence/RESULTADOS.md)

## Comece aqui

**[Passo a passo completo: do zero ao resultado final](docs/PASSO_A_PASSO.md)**

O roteiro explica instalação, configuração de senhas, backup, subida dos bancos, restauração, preparação do Change Tracking, criação do DW, primeira carga, reconciliação, incremental, consultas, testes e evidências. Cada etapa informa onde executar o comando e qual resultado conferir antes de continuar. Serve para o aluno e para o professor em uma instalação nova.

Não há site ou dashboard: o resultado é consultado pelo terminal e pelo DBeaver. Python, SQL Server e PostgreSQL rodam em containers; não precisam ser instalados separadamente no Windows.

## Executar com Docker no Windows

Siga o [passo a passo](docs/PASSO_A_PASSO.md), começando na etapa 1. Quem já possui as ferramentas instaladas pode começar na etapa 2. O reset da etapa 3 é somente para quem quer apagar uma instalação anterior. A inicialização normal começa na etapa 4, com o backup.

**Não confunda servidor iniciado com backup restaurado:** o banco `AdventureWorks2016` só fica disponível após o comando `restore`. O roteiro confirma `ONLINE` antes de preparar ou executar a ETL.

Para uma retomada normal, com bancos já preparados:

```powershell
docker compose up -d --wait --wait-timeout 300 postgres sqlserver
```

Depois execute `run`, `verify` e `report`, um por vez, conforme necessário. Para pausar preservando os dados, use `docker compose stop`. A ETL executa um ciclo por comando; não roda continuamente.

## DBeaver

A etapa 7 do [passo a passo](docs/PASSO_A_PASSO.md) configura o SQL Server, primeiro em `master` para confirmar o estado do banco; a etapa 8 configura o PostgreSQL. Os valores padrão são:

| Campo | SQL Server | PostgreSQL |
|---|---|---|
| Host | localhost | localhost |
| Porta externa | 14330 | 54330 |
| Banco | AdventureWorks2016, após restauração | adventureworks_dw |
| Usuário | sa | dw |
| Senha do .env | MSSQL_SA_PASSWORD | PGPASSWORD |

As propriedades dos drivers e os diagnósticos dos erros 18456 estão no roteiro. Use as portas configuradas no `.env` caso tenham sido alteradas.

## Implementação e documentação técnica

Uma fato no grão item de pedido, seis dimensões independentes, três papéis da dimensão data, oito FKs, dez indicadores SQL, SCD1, upsert, exclusões, checkpoint transacional, trava de concorrência, auditoria e reconciliação.

- [Modelagem dimensional](docs/MODELAGEM.md)
- [Dez indicadores e suas regras](docs/KPIS.md)
- [Estratégia da ETL e limitações](docs/ETL.md)
- [Dicionário de dados](docs/DICIONARIO.md)
- [Diagrama do modelo estrela](docs/modelo_estrela.png)

## Testes e resultado esperado

As etapas 10 a 14 do [passo a passo](docs/PASSO_A_PASSO.md) levam à reconciliação `PASS`, incremental sem mudanças com zero fatos extraídos/escritos/excluídos, dez KPIs consultáveis e suíte completa aprovada em bases isoladas.

O [guia de testes detalhado](docs/GUIA_TESTES.md) complementa o roteiro com demonstração opcional de alterações, SCD1, falha injetada e recuperação. Registre resultados efetivamente observados em [evidence/RESULTADOS.md](evidence/RESULTADOS.md); os JSONs de `verify` e `report` ficam em `evidence/` e são sobrescritos a cada execução.

Testes com massa sintética e validação do AdventureWorks real são evidências diferentes. Não considere a instalação validada apenas porque os containers estão ativos.

## Conteúdo da entrega

Código da ETL, Compose, Dockerfile, dependências, scripts SQL, testes, documentação técnica, diagramas e roteiros de execução. A entrega inclui evidências reais da revisão de 12/09/2026: 28 testes aprovados e 121.317 itens reconciliados sem divergências. Consulte o escopo e as limitações em evidence/RESULTADOS.md.

O material do grupo fica em `apoio-interno/`, ignorado pelo Git e pelo contexto de build do Docker. `.env`, backups e caches também ficam fora do versionamento. Ao entregar por ZIP, selecione os arquivos de entrega: compactar toda a raiz manualmente não respeita o `.gitignore`.

## Regerar o artigo

O texto editável está em [ARTIGO.md](docs/ARTIGO.md). O [guia de edição](docs/ARTIGO_EDICAO.md) explica como gerar o PDF a partir do texto, dicionário, SQL e evidências.
