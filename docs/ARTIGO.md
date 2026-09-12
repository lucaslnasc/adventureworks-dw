# Modelagem dimensional de vendas e ETL incremental com AdventureWorks

ANDRÉ ALVES DA SILVA

BRENO DOS SANTOS GUIMARÃES

LUCAS DE LIMA NASCIMENTO

SERGIO PAULO DE ANDRADE

Centro Universitário Salesiano - UniSales

Curso: Sistemas de Informação

Disciplina: Projeto de Análise e Fluxo de Dados - OLAP e ETL

Professor: James Alves

Vitória, 2026

## RESUMO

Este trabalho apresenta a construção de um modelo dimensional de vendas baseado no banco transacional AdventureWorks2016, com destino em PostgreSQL e processo de extração, transformação e carga incremental desenvolvido em Python. O objetivo é demonstrar a relação entre granularidade, definição de indicadores e consistência da integração de dados. O modelo segue o padrão estrela, com uma tabela fato no nível de item de pedido e seis dimensões independentes. Foram definidos dez indicadores relacionados a valores comerciais, volume, clientes, variação mensal e expedição. A estratégia incremental utiliza Change Tracking do SQL Server para identificar chaves inseridas, alteradas ou excluídas, incluindo dependências entre tabelas que formam dimensões desnormalizadas. A leitura ocorre em snapshot consistente e a confirmação dos dados e do checkpoint é atômica no destino. A validação em bases isoladas aprovou 28 testes, incluindo operações reais de Change Tracking. No AdventureWorks restaurado, a reconciliação comparou 121.317 itens na origem e no DW, sem divergências. As consultas retornaram receita líquida de 109.846.381,399888 UM e 31.465 pedidos expedidos; os retornos dos dez indicadores foram incorporados ao artigo. O estudo demonstra como decisões explícitas de granularidade, população analítica e recuperação evitam duplicação de medidas e perda silenciosa de alterações.

Palavras-chave: Data Warehouse; modelagem dimensional; modelo estrela; ETL incremental; AdventureWorks.

## ABSTRACT

This work presents a dimensional sales model based on the AdventureWorks2016 transactional database, using PostgreSQL as the target and Python for incremental extraction, transformation and loading. Its objective is to demonstrate the relationship between fact grain, performance metrics and integration consistency. The design follows a star schema with one fact table at sales order line grain and six independent dimensions. Ten metrics cover commercial amounts, sales volume, customers, monthly change and shipping. SQL Server Change Tracking identifies inserted, updated and deleted keys, including dependencies across source tables used to build denormalized dimensions. Source reads use a consistent snapshot, while target data and synchronization checkpoints are committed atomically. Validation in isolated databases passed 28 tests, including actual Change Tracking operations. Reconciliation against the restored AdventureWorks backup matched 121,317 source and warehouse items with no differences. Queries returned net sales of 109,846,381.399888 source monetary units and 31,465 shipped orders; outputs of all ten metrics are included in this paper. The study illustrates how explicit decisions about grain, analytical scope and failure recovery prevent duplicated measures and silent loss of changes.

Keywords: Data Warehouse; dimensional modeling; star schema; incremental ETL; AdventureWorks.

## 1 INTRODUÇÃO

Sistemas transacionais registram operações como pedidos, produtos e clientes, organizando os dados para preservar integridade durante inclusões e alterações. Perguntas analíticas, entretanto, combinam grandes conjuntos de registros e exigem definições consistentes para períodos, populações e medidas. No contexto de vendas, uma consulta pode produzir valores numericamente plausíveis e ainda assim estar incorreta se somar o total de um pedido para cada um de seus itens.

O problema investigado neste trabalho é como transformar o domínio de vendas do AdventureWorks em uma estrutura multidimensional que suporte dez indicadores e permaneça sincronizada sem recarregar indiscriminadamente todas as tabelas. A modelagem e a integração são tratadas de forma conjunta: o nível de detalhe determina quais medidas podem ser armazenadas, enquanto as dependências entre tabelas determinam quais registros precisam ser reavaliados após uma mudança na origem.

O objetivo geral é implementar um data mart de vendas em PostgreSQL seguindo o padrão Star Schema, alimentado por uma ETL incremental em Python. Os objetivos específicos são analisar as entidades do OLTP, declarar a granularidade, selecionar dimensões, formalizar os indicadores, tratar registros novos e alterados, prever exclusões e demonstrar a recuperação de falhas. A documentação e os testes complementam o código para permitir sua reprodução e defesa técnica.

O AdventureWorks é um conjunto de bases de exemplo disponibilizado pela Microsoft. Para este projeto foi selecionado o backup OLTP completo de 2016, restaurado no SQL Server 2022, evitando utilizar a base AdventureWorksDW já modelada para análise ou a versão LT simplificada (Microsoft, s.d.a). O recorte abrange vendas de produtos; compras, estoque e fabricação não integram o modelo analítico proposto.

## 2 FUNDAMENTAÇÃO TEÓRICA

### 2.1 DATA WAREHOUSE E MODELAGEM DIMENSIONAL

Um Data Warehouse integra dados para consulta analítica com regras de interpretação estáveis. Um data mart delimita essa finalidade a um processo ou domínio, como vendas. A disponibilidade de dados em um banco separado, por si só, não garante qualidade analítica: é necessário definir a origem de cada medida, o evento representado por uma linha e o comportamento de agregação.

Na modelagem dimensional, fatos representam medições e dimensões descrevem os contextos de análise. O grão deve ser declarado antes da escolha de medidas e dimensões, pois registros de níveis diferentes não devem coexistir indistintamente na mesma fato (Kimball Group, s.d.). Neste trabalho, essa orientação significa distinguir item, pedido e cliente: uma linha mede a venda de um produto dentro de um pedido, enquanto pedidos e clientes são contados de forma distinta.

O modelo estrela liga uma fato central diretamente a dimensões descritivas. Hierarquias podem ser armazenadas na própria dimensão, reduzindo a necessidade de o usuário percorrer estruturas relacionais normalizadas (Kimball, 2003). No domínio de produtos, categoria e subcategoria são incorporadas a dim_produto. Não há uma dimensão categoria referenciada por uma dimensão subcategoria: essa opção manteria parte da hierarquia em floco de neve, contrariando o padrão escolhido para o trabalho.

### 2.2 ADITIVIDADE E ALTERAÇÕES DE DIMENSÕES

Uma medida aditiva pode ser somada nos eixos pertinentes ao seu grão. Quantidade e valor de itens são exemplos no recorte de vendas. Taxas, preços e médias exigem outra abordagem: a soma de percentuais não expressa a taxa global e a média simples de tickets de grupos com tamanhos diferentes pode distorcer o resultado. Por isso, os indicadores derivados são calculados a partir de numeradores e denominadores agregados.

Chaves substitutas permitem identificar membros dimensionais independentemente da codificação operacional. Nas dimensões de produto, cliente, território e vendedor, a chave de negócio permanece única para apoiar o lookup e o upsert, enquanto a chave substituta é referenciada pela fato. A dimensão data usa uma chave determinística no formato YYYYMMDD e a dimensão canal possui dois membros estáticos.

Descrições de dimensões podem mudar com o tempo. A estratégia Slowly Changing Dimension tipo 1 sobrescreve o atributo, enquanto a tipo 2 cria versões para preservar sua vigência histórica (Kimball, 2008). Adotou-se SCD1 porque os indicadores propostos usam descrições atuais. A consequência é explícita: renomear uma categoria altera a classificação exibida também para vendas antigas. Isso não deve ser interpretado como histórico completo da classificação no momento da venda.

### 2.3 EXTRAÇÃO TRANSFORMAÇÃO E CARGA INCREMENTAL

A ETL extrai dados da origem, aplica regras de transformação e os carrega no destino. A incrementalidade delimita cada ciclo aos registros novos, alterados, excluídos e às dependências necessárias para manter o modelo consistente. Um mecanismo de detecção é insuficiente sem uma política de checkpoint, pois uma falha entre a escrita dos dados e a atualização do marcador pode causar perda ou repetição de trabalho.

O Change Tracking do SQL Server permite consultar chaves modificadas desde uma versão conhecida. Para uma leitura consistente, a documentação orienta validar a versão mínima, obter a versão atual e consultar as mudanças dentro de uma transação com isolamento snapshot (Microsoft, s.d.b). O mecanismo fornece o estado necessário à sincronização, sem representar um histórico completo de todas as versões intermediárias.

No PostgreSQL, a instrução INSERT com ON CONFLICT permite resolver a presença de uma chave já existente por atualização (PostgreSQL Global Development Group, s.d.). Neste projeto, o upsert é condicionado à diferença material entre os valores, e a confirmação ocorre na mesma transação que grava o checkpoint. A integração admite repetição de leitura após falha, mas preserva a unicidade do estado final por item.

## 3 DESENVOLVIMENTO E MÉTODO

### 3.1 ANÁLISE DO ADVENTUREWORKS OLTP

Sales.SalesOrderHeader contém os atributos do pedido, incluindo cliente, vendedor, território, status e datas. Sales.SalesOrderDetail contém produto, quantidade, preço, desconto e LineTotal. Um cabeçalho pode possuir vários detalhes. A ligação entre essas tabelas fornece a base transacional da fato, com identificação composta por SalesOrderID e SalesOrderDetailID.

Production.Product relaciona-se a ProductSubcategory, que se relaciona a ProductCategory. Sales.Customer identifica clientes vinculados a Person.Person ou Sales.Store. O vendedor utiliza Sales.SalesPerson e Person.Person, enquanto Sales.SalesTerritory fornece nome, código de país e grupo comercial. Campos opcionais são tratados deliberadamente, evitando que joins internos indevidos removam vendas sem vendedor ou território associado.

O catálogo real do backup deve confirmar os relacionamentos e tipos utilizados. Para isso, foram implementadas consultas a sys.tables, sys.columns, sys.foreign_keys e propriedades descritivas, além de perfis de status, datas e medidas. A figura relacional de 2008 disponibilizada no enunciado serve como apoio à leitura, mas não substitui a inspeção da versão 2016. O script de análise também compara subtotais e soma de itens, distinguindo arredondamento de erro de agregação.

### 3.2 MODELO ESTRELA E GRANULARIDADE

A fato_venda possui uma linha por item de pedido no estado mais recente sincronizado. Sua chave primária composta é pedido_id e item_id. O pedido_id também funciona como dimensão degenerada, permitindo localizar o documento comercial sem criar uma tabela descritiva de apenas um identificador. A fato armazena status, quantidade, preço, taxa de desconto e receita líquida, além das chaves das dimensões.

São utilizadas seis dimensões: dim_data, dim_produto, dim_cliente, dim_territorio, dim_vendedor e dim_canal. A dimensão data participa pelos papéis pedido, vencimento e envio, com três FKs independentes. As outras cinco dimensões possuem uma FK cada, totalizando oito relacionamentos dimensionais na fato. Não há FKs entre dimensões, preservando o padrão estrela. O diagrama apresenta essa organização.

{{DIAGRAMA}}

Produto e cliente são obrigatórios. Vendedor e território ausentes na origem utilizam membros técnicos com SK zero. A data de envio permanece nula se não informada; inventar uma data alteraria o indicador de prazo. Se uma chave obrigatória não for encontrada no lookup, o lote falha e é revertido. O dicionário completo de colunas, tipos, origens e regras encontra-se no Apêndice A.

### 3.3 REGRAS COMERCIAIS E INDICADORES

Os dez indicadores adotam a população de pedidos expedidos, identificada por Status igual a 5, e usam a data do pedido como eixo temporal padrão. A fato mantém os demais status para refletir alterações posteriores. Esse recorte representa uma convenção comercial didática e não uma política contábil de reconhecimento de receita.

Receita bruta é quantidade multiplicada pelo preço unitário; receita líquida comercial é LineTotal; o desconto monetário corresponde à diferença entre ambas. Frete, tributos e TotalDue pertencem ao grão pedido e não são repetidos como medidas aditivas nos itens. Não se calcula lucro com StandardCost atual, pois isso não demonstraria o custo histórico efetivo da venda.

{{DEFINICOES_KPIS}}

Os valores monetários são conservados em unidades monetárias da fonte, sem nova conversão cambial. A agregação pressupõe a convenção homogênea de UnitPrice e LineTotal no conjunto didático, que deve ser confirmada na análise do backup. Se uma fonte mantiver valores em moedas locais heterogêneas, será necessária uma modelagem adicional de moeda e conversão antes de utilizar os totais monetários.

As razões usam NULLIF no denominador para representar situações indefinidas sem erro de divisão por zero. A série mensal inclui meses intermediários sem venda antes de aplicar LAG; assim, março não é comparado diretamente com janeiro quando fevereiro está vazio. Contagens de clientes e pedidos distintos não podem ser somadas indiscriminadamente entre categorias ou períodos.

O décimo indicador deduplica pedidos e compara ShipDate com DueDate. Ele é denominado expedição até o vencimento, pois os campos não comprovam a entrega ao cliente. Pedidos expedidos sem data de envio são informados separadamente e não entram no denominador. Os scripts completos estão no Apêndice B e o documento KPIS.md do projeto detalha objetivos, relevância, linhagem, interpretação e argumentos de defesa para cada indicador.

### 3.4 IMPLEMENTAÇÃO DO DW E DA ETL

O PostgreSQL implementa PKs, FKs, unicidade das chaves de negócio e verificações de domínio. As medidas monetárias usam numeric e a transformação Python usa Decimal. Colunas geradas calculam receita bruta e desconto monetário, evitando que diferentes escritores mantenham fórmulas incompatíveis. Índices apoiam os principais filtros dimensionais, sem afirmar ganho de desempenho que ainda não foi medido no backup real.

No início de cada carga, uma trava de sessão no PostgreSQL impede concorrência entre execuções do pipeline. A tabela etl.execucao registra a tentativa e etl.controle fornece a última versão confirmada. A origem inicia uma transação snapshot, verifica a validade do checkpoint em todas as tabelas monitoradas e captura a versão superior. Mudanças confirmadas depois desse snapshot ficam para a próxima execução. A tabela temporária de pedidos afetados e seu índice são criados antes do início do snapshot, enquanto a leitura das mudanças ocorre dentro da transação consistente; essa organização corrige o erro SQL Server 3964.

As chaves retornadas pelo CT formam conjuntos de dependências. Uma alteração no cabeçalho exige reavaliar os itens do pedido; uma alteração de categoria exige reavaliar os produtos associados. Mudanças em Person alcançam tanto clientes quanto vendedores. Dessa forma, a desnormalização do modelo é acompanhada por regras explícitas de propagação, sem depender apenas do ModifiedDate da entidade principal.

O lote é materializado em memória e a transação de leitura da origem é encerrada antes da escrita no destino. Dentro de uma única transação PostgreSQL, a ETL atualiza dimensões por SCD1, completa o calendário, resolve chaves e faz COPY dos itens para staging temporário. Valida as medidas e identifica itens ausentes nos pedidos afetados para tratar exclusões. O upsert grava somente linhas novas ou materialmente diferentes; linhas inalteradas reavaliadas por dependência não são regravadas.

Por fim, a ETL compara os itens do staging com o destino, grava o checkpoint e marca sucesso na mesma transação. Se ocorrer falha antes do COMMIT, dados e marcador são revertidos. Se a confirmação ocorrer antes de uma interrupção do processo, o checkpoint já corresponde aos dados. Não há transação distribuída porque a origem é somente lida; a garantia necessária concentra-se na confirmação conjunta dos dados e do marcador no destino.

### 3.5 RETENÇÃO RECUPERAÇÃO E REPRODUTIBILIDADE

O CT é preparado com retenção de sete dias. Quando o checkpoint é inferior à versão mínima válida, o programa interrompe a carga e exige ressincronização explícita por run --resync. A leitura completa de recuperação preserva as chaves substitutas, atualiza dimensões, elimina fatos ausentes e confirma um novo marcador. Essa exceção não substitui os ciclos incrementais regulares.

A identidade da origem combina um identificador criado na preparação da base e versões de habilitação do CT. O recurso ajuda a detectar troca de origem, mas não garante identificar toda restauração de backup. Após restauração ou alteração administrativa do rastreamento, o procedimento determina ressincronização completa. CT sincroniza o estado atual e não preserva todas as mudanças intermediárias.

Docker Compose descreve SQL Server, PostgreSQL e a aplicação Python, com volumes persistentes e verificações de prontidão. A preparação restaura o backup sem sobrescrever bases existentes. O repositório inclui scripts de análise, criação do DW, indicadores, demonstração, testes e documentação. O DBeaver é utilizado para consultar catálogos, visualizar relações e exportar resultados, sem desenvolvimento de dashboard.

Projeto da ETL no GitHub: https://github.com/lucaslnasc/adventureworks-dw. A revisão do código executado é identificada pelos hashes SHA-256 de cada arquivo no campo files_sha256 de evidence/validacao.json. O registro permite comparar os arquivos avaliados com o código disponibilizado no repositório, independentemente do commit que vier a reunir a documentação. O README apresenta o roteiro de instalação e a documentação técnica detalha modelagem, dicionário e estratégia incremental.

## 4 RESULTADOS E DISCUSSÃO

### 4.1 EVIDÊNCIAS DA CARGA E RECONCILIAÇÃO

A revisão automatizada executada em 12 de setembro de 2026 produziu novas exportações: evidence/reconciliation.json às 15h41min53s e evidence/kpis.json às 15h41min54s, horário de Brasília (UTC-3). Esses arquivos acompanham o projeto e substituem, como referência documental desta edição, as transcrições anteriores de 12h57. Ambas as exportações registram a versão CT 0; esse número representa o checkpoint de mudanças, e não a quantidade de linhas carregadas.

O comando verify comparou 121.317 itens na origem e 121.317 no destino, sem divergências de chaves ou atributos de fato. A diferença de zeros finais na representação da receita decorre da escala decimal. A Tabela 1 apresenta os campos exportados.

{{RECONCILIACAO}}

A reconciliação considera todos os status, enquanto as views dos indicadores filtram status 5. O perfil da origem mostrou 31.465 pedidos, todos expedidos, explicando a coincidência numérica entre os dois recortes nesta execução. A comparação adicional das descrições de produto, cliente, território e vendedor encontrou zero diferenças. As três primeiras consultas de qualidade retornaram zero linhas.

### 4.2 RETORNOS DOS DEZ INDICADORES

As dez views foram executadas pelo comando report. A Tabela 2 resume os resultados; o Apêndice C associa cada consulta ao retorno, incluindo a série completa de 38 meses. Os valores provêm do AdventureWorks restaurado, e não da massa sintética dos testes.

{{RESUMO_KPIS}}

A receita bruta de 110.373.889,31340000 UM menos 527.507,91351200 UM de descontos resulta em receita líquida de 109.846.381,39988800 UM. A divisão pelos 31.465 pedidos distintos produz ticket médio de 3.491,0656729664071190 UM. A taxa de desconto global, aproximadamente 0,4779%, é calculada sobre valores agregados.

A série mensal vai de maio de 2011 a junho de 2014. O primeiro mês não tem base anterior e retorna NULL. Março de 2014 apresenta receita de 7.217.531,091974 UM e crescimento de aproximadamente 439,5377%; junho de 2014 apresenta 49.005,840000 UM e variação de -99,0868%. A cobertura e a composição dos dados devem ser examinadas antes de atribuir essas variações a causas de negócio.

O indicador de expedição retorna 31.465 pedidos com data, zero sem data e 31.465 expedidos até o vencimento, totalizando 100%. A comparação entre ShipDate e DueDate não comprova recebimento pelo cliente.

### 4.3 INTEGRIDADE REFERENCIAL E TESTES DA ETL

O catálogo PostgreSQL confirmou oito chaves estrangeiras com convalidated igual a true. São cinco referências não temporais e três papéis da dimensão data. A Tabela 3 apresenta a consulta registrada em evidence/validacao.json.

{{CHAVES_ESTRANGEIRAS}}

A suíte aprovou 28 testes em 9,90 segundos, sem falhas e sem testes pulados: 13 casos de transformação, 12 de PostgreSQL e três de SQL Server/Change Tracking. Foram verificados indicadores, meses sem venda, denominadores vazios, idempotência, inserção, atualização, exclusão, alteração de cabeçalho, SCD1, rollback, recuperação, auditoria, concorrência e mudanças confirmadas durante snapshot. O teste de regressão do erro 3964 confirmou o ciclo vazio, a deduplicação de pedidos afetados e a exclusão do último item.

A execução utilizou Python 3.13.5 no Windows, pytest 9.1.1, psycopg 3.3.5, pymssql 2.4.1, PostgreSQL 17.11 e SQL Server 2022 16.0.4275.2. As bases sintéticas de teste foram criadas isoladamente e removidas ao final. A imagem declarada no Dockerfile usa Python 3.12; o build Docker e uma nova restauração não foram reexecutados nesta revisão. Os resultados não devem ser apresentados como teste de uma instalação Docker nova.

O histórico da base principal registra carga inicial de 121.317 fatos, falhas incrementais anteriores e depois um ciclo incremental bem-sucedido com zero fatos extraídos, escritos e excluídos. A extração adicional desta revisão, a partir do checkpoint 0, retornou zero fatos, pedidos afetados e membros dimensionais. Essa última checagem foi de leitura, sem nova escrita de lote no DW principal.

Na massa sintética, a receita bruta foi 310 UM, os descontos 20 UM e a receita líquida 290 UM. O mês intermediário sem vendas foi preenchido com zero e a divisão por base anterior zero permaneceu indefinida. Um dos dois pedidos estava no prazo, resultando em 50%. Esses exemplos controlados são distintos dos valores reais apresentados nas tabelas e no Apêndice C.

### 4.4 LIMITAÇÕES E INTERPRETAÇÃO

SCD1 apresenta as descrições atuais para vendas antigas; CT sincroniza o estado atual, sem fornecer todos os eventos intermediários. A seleção incremental pode reler itens inalterados dos pedidos afetados, mas o upsert só regrava fatos materialmente diferentes. A extração inicial em memória é adequada ao porte didático, podendo exigir staging persistente em maior escala. Não foram realizados benchmarks comparativos de desempenho.

O perfil da origem identificou 13.976 pedidos com CurrencyRateID. O projeto conserva UnitPrice e LineTotal em UM, sem reaplicar câmbio apenas pela existência dessa referência. A reconciliação demonstra fidelidade aos campos da fonte, mas não demonstra, isoladamente, sua convenção monetária; a comparabilidade permanece uma premissa explícita. Expedição até o vencimento também não equivale a entrega ao cliente. Novas fontes ou perguntas de negócio podem exigir moeda, medidas convertidas e novos marcos logísticos.

## 5 CONSIDERAÇÕES FINAIS

O trabalho apresentou um modelo estrela de vendas, implementado em PostgreSQL e alimentado por ETL incremental em Python. A definição do grão item preserva produtos, quantidades e descontos, exigindo contagem distinta de pedidos e exclusão de medidas repetidas de cabeçalho. A desnormalização foi acompanhada de regras de dependência para atualizar descrições de categorias, lojas e pessoas.

A integração combina versão de mudanças, snapshot consistente, upserts por chaves únicas e checkpoint transacional. Os 28 testes aprovados incluem Change Tracking real e recuperação de falha. No AdventureWorks restaurado, 121.317 itens foram reconciliados sem divergências, e os dez indicadores tiveram seus retornos registrados. O repositório é identificado na seção 3.5 e as evidências anexas identificam os arquivos de código avaliados.

Como evolução, o modelo pode receber SCD2 para descrições históricas, tratamento explícito de múltiplas moedas e processamento em lotes para maior escala. Essas mudanças devem decorrer de novas necessidades e preservar o grão, a consistência e as garantias de recuperação.

## REFERÊNCIAS

CENTRO UNIVERSITÁRIO SALESIANO. Guia de elaboração e normalização de trabalhos acadêmicos e de pesquisa. Vitória: UniSales, 2024. Disponível em: https://unisales.br/wp-content/uploads/2024/07/NOVO-GUIA-DE-ELABORACAO-E-NORMALIZACAO-DE-TRABALHOS-ACADEMICOS-E-DE-PESQUISA-29.05.pdf. Acesso em: 12 set. 2026.

KIMBALL, Ralph. Fact tables and dimension tables. Kimball Group, 2003. Disponível em: https://www.kimballgroup.com/2003/01/fact-tables-and-dimension-tables/. Acesso em: 12 set. 2026.

KIMBALL, Ralph. Slowly changing dimensions. Kimball Group, 2008. Disponível em: https://www.kimballgroup.com/2008/08/slowly-changing-dimensions/. Acesso em: 12 set. 2026.

KIMBALL GROUP. Grain. [S. l.], [s. d.]. Disponível em: https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/grain/. Acesso em: 12 set. 2026.

MICROSOFT. AdventureWorks sample databases. Microsoft Learn, [s. d.a]. Disponível em: https://learn.microsoft.com/en-us/sql/samples/adventureworks-install-configure. Acesso em: 12 set. 2026.

MICROSOFT. Work with Change Tracking. Microsoft Learn, [s. d.b]. Disponível em: https://learn.microsoft.com/en-us/sql/relational-databases/track-changes/work-with-change-tracking-sql-server. Acesso em: 12 set. 2026.

POSTGRESQL GLOBAL DEVELOPMENT GROUP. INSERT. PostgreSQL 17 documentation, [s. d.]. Disponível em: https://www.postgresql.org/docs/17/sql-insert.html. Acesso em: 12 set. 2026.
