# Modelo de vendas e decisões de projeto

## Escopo e análise OLTP

O processo de negócio escolhido é venda de produtos, do registro do pedido até seu estado atual de expedição. Trata-se de um data mart de vendas que atende ao exercício de Data Warehouse, e não de uma cópia de todos os domínios do AdventureWorks. Compras, fabricação, recursos humanos e estoques não são carregados porque não são necessários aos dez indicadores definidos.

No OLTP, `Sales.SalesOrderHeader` representa o pedido e `Sales.SalesOrderDetail` representa seus itens. O relacionamento é 1:N por `SalesOrderID`; a identificação do item é o par `(SalesOrderID, SalesOrderDetailID)`. Usar somente `SalesOrderID` na fato perderia produtos e descontos distintos dentro do mesmo pedido.

| Caminho no OLTP | Cardinalidade e finalidade | Destino |
|---|---|---|
| Header → Detail | 1:N, cabeçalho e linhas de venda | fato_venda |
| Detail → Product | N:1, produto vendido | dim_produto |
| Product → ProductSubcategory → ProductCategory | N:1 em cada passo, hierarquia de catálogo opcional | Atributos da própria dim_produto |
| Header → Customer → Person ou Store | N:1, cliente pessoa ou loja | dim_cliente |
| Header → SalesTerritory | N:1 opcional, território registrado no pedido | dim_territorio |
| Header → SalesPerson → Person | N:1 opcional, vendedor associado | dim_vendedor |
| OrderDate, DueDate, ShipDate | Datas do pedido, vencimento e expedição | Três FKs para dim_data |
| OnlineOrderFlag | Booleano do canal comercial | dim_canal |

A figura AdventureWorks2008 fornecida pelo professor ajuda a navegar nos domínios. Como a implementação usa o backup 2016, o catálogo do banco restaurado é a fonte de confirmação de colunas e FKs. `002_analise_oltp.sql` materializa essa análise, inclusive a presença de `CurrencyRateID`, as distribuições de status e as divergências entre subtotal e soma de itens.

## Grão e natureza da fato

**Uma linha da fato representa um item de um pedido de venda, identificado pelo par de chaves de negócio da origem, com os atributos e valores mais recentes sincronizados.** É uma fato transacional atualizável: registra a linha do negócio e admite correções; não é uma tabela de eventos imutáveis nem um snapshot periódico. Não promete recuperar todos os estados intermediários que o pedido teve.

`pedido_id` funciona também como dimensão degenerada: identifica o documento sem exigir uma dimensão com apenas seu número. A PK composta preserva diretamente a unicidade do grão e sustenta o upsert. Uma SK adicional na fato seria possível, mas não eliminaria a necessidade de UNIQUE sobre as chaves da origem e não atende a uma necessidade deste escopo.

Não é possível derivar a quantidade de pedidos por `COUNT(*)` na fato. É necessário `COUNT(DISTINCT pedido_id)`. Tampouco se somam contagens distintas de clientes ou pedidos calculadas separadamente por produto: o mesmo cliente ou pedido pode aparecer em vários grupos.

## Por que é estrela

Todas as dimensões apontam diretamente para a fato por PK/FK; não existem FKs entre dimensões. Categoria e subcategoria são colunas de `dim_produto`, em vez de tabelas analíticas relacionadas. Pessoa e loja são resolvidas em `dim_cliente`. O país é um código descritivo dentro de `dim_territorio`. Isso evita que o consumidor precise reproduzir os caminhos normalizados do OLTP.

Uma linha da dimensão pode ser usada por zero, um ou muitos itens. Cada item exige exatamente um produto, um cliente, um canal e datas de pedido/vencimento. A data de envio pode estar ausente. Território e vendedor ausentes usam o membro técnico SK=0, porque o OLTP permite esses nulos. Se uma chave obrigatória não for encontrada, a ETL falha e reverte o lote; não mascara um erro de integração como membro desconhecido.

## Decisões por tabela

| Tabela | Decisão e justificativa |
|---|---|
| dim_data | Uma linha por dia; chave YYYYMMDD estável. Ano, trimestre, mês, dia, dia da semana ISO e início do mês facilitam filtros e séries. A mesma dimensão participa três vezes por papéis diferentes; não são três dimensões físicas nem relações entre dimensões. |
| dim_produto | SK identity e NK ProductID única. Nome, número, cor, subcategoria e categoria ficam juntos. Não incluímos StandardCost atual como custo histórico da venda. |
| dim_cliente | SK identity e NK CustomerID única. Prioriza nome da loja quando StoreID existe; caso contrário usa a pessoa. Evita multiplicação de linhas por endereços, telefones ou e-mails multivalorados. |
| dim_territorio | Usa o TerritoryID do pedido. O território atual do cliente ou vendedor poderia ser diferente e não deve substituir a associação registrada na transação. |
| dim_vendedor | Vendedor histórico associado ao pedido por SalesPersonID; o nome é a descrição atual. Não mistura vendedor com cliente mesmo que ambos se relacionem a Person. |
| dim_canal | Dois membros estáticos para OnlineOrderFlag: online e revendedor. Uma dimensão curta torna a segmentação legível; a chave 0 aqui significa revendedor, não desconhecido. |
| fato_venda | Concentra FKs, IDs do documento, status e medidas de item. Índices em dimensões de maior uso favorecem filtros e verificações das FKs. A PK já indexa pedido_id; não foi criado outro índice redundante nessa coluna. |
| etl.controle | Uma linha para o pipeline de vendas guarda a versão confirmada e a identidade da fonte. Não é dimensão. |
| etl.execucao | Uma linha por execução registra modo, versões, contagens e resultado. Permite defender a incrementalidade com evidência, sem interferir no modelo estrela. |

## Medidas e população analítica

As views dos KPIs consideram somente `Status=5` (expedido) e atribuem a venda à data do pedido. Trata-se de uma definição comercial didática, não de política de reconhecimento contábil. A fato carrega todos os status conhecidos (1 em processo, 2 aprovado, 3 em atraso, 4 rejeitado, 5 expedido e 6 cancelado), de modo que uma alteração posterior de status entra ou sai da população sem deixar dados antigos incorretos.

Receita bruta = quantidade × preço unitário. Receita líquida comercial = `LineTotal` da origem, isto é, quantidade × preço × (1 − taxa de desconto). Desconto monetário = bruta − líquida. `UnitPriceDiscount` é usado como fração conforme a expressão computada de LineTotal: 0,10 corresponde a 10%. Não se soma a taxa de desconto entre linhas.

Os valores são apresentados em **UM (unidade monetária da fonte)**. O projeto conserva UnitPrice e LineTotal e não executa conversão cambial. A comparabilidade monetária pressupõe a convenção homogênea desses campos no conjunto didático; confirme-a na análise do backup. A presença de CurrencyRateID, isoladamente, não autoriza reaplicar conversões. Se a fonte real mantiver valores em moedas locais diferentes, este modelo deverá receber moeda e uma medida convertida com data/regra de câmbio antes de agregar valores monetários.

Não são carregados `SubTotal`, `TaxAmt`, `Freight` nem `TotalDue` como medidas aditivas da fato de itens. Esses valores pertencem ao cabeçalho: um pedido de três itens faria seu frete aparecer três vezes. Se esses indicadores fossem exigidos, seria necessário um rateio documentado ou outra fato no grão pedido, fora desta entrega. Receita líquida aqui não significa lucro, pois custos e despesas não são descontados.

As medidas monetárias e quantidade são aditivas nas dimensões deste recorte. Preço e taxas não são aditivos. Ticket e percentuais são calculados como razão de totais, sem média simples de médias. Crescimento mensal não deve ser somado entre meses. A métrica de prazo usa um pedido uma única vez e compara expedição com vencimento, sem afirmar que o produto foi entregue ao cliente.

## Histórico e desempenho

As dimensões descritivas usam SCD1: atualizam a descrição preservando SK e NK. Ao renomear uma categoria, vendas antigas passam a exibir o nome atual. A escolha simplifica a carga e atende aos indicadores propostos, que não pedem segmentação pelos atributos vigentes no passado. SCD2 exigiria vigências, múltiplas versões da NK e lookup pela data do evento; não foi anunciado nem parcialmente implementado.

`ativo_origem` significa que o membro ainda existe no OLTP, não que o produto está comercialmente disponível nem que o cliente comprou recentemente. Um membro excluído é marcado inativo para preservar referências já existentes. Ressincronização mantém as SKs e elimina fatos que não existem mais na fonte. Não há captura de todas as versões de uma venda; CT sincroniza estado atual.

Os índices iniciais atendem às chaves e filtros principais. Em produção, sua utilidade deve ser confirmada com `EXPLAIN (ANALYZE, BUFFERS)` sobre consultas representativas: índices também aumentam o custo de escrita. Não se afirma ganho de desempenho sem medição. A carga inicial mantém os registros extraídos em memória, adequado ao porte didático; lotes em disco e COPY por páginas seriam a evolução para volumes maiores.

## Referências técnicas

[Grão — Kimball Group](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/grain/), [fatos e dimensões — Kimball Group](https://www.kimballgroup.com/2003/01/fact-tables-and-dimension-tables/), [SCD — Kimball Group](https://www.kimballgroup.com/2008/08/slowly-changing-dimensions/) e [repositório oficial AdventureWorks](https://github.com/microsoft/sql-server-samples/tree/master/samples/databases/adventure-works).
