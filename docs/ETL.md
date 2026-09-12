# Estratégia incremental e garantias

## Escolha do mecanismo

O projeto usa **Change Tracking (CT)** no SQL Server. Em cada transação confirmada, o mecanismo associa versões a mudanças nas tabelas monitoradas. `CHANGETABLE(CHANGES tabela, versão_anterior)` permite obter as chaves alteradas desde a última sincronização. A ETL consulta essas chaves nas tabelas de negócio para obter o estado atual, incluindo os casos de exclusão em que a chave existe no CT, mas não existe mais na tabela.

CT não fornece todas as imagens anteriores e posteriores de cada registro. Se um preço mudou três vezes entre ciclos, a carga recebe seu estado final no snapshot. Essa característica é compatível com a fato atualizável e as dimensões SCD1 adotadas. CDC seria uma alternativa para integração orientada a eventos e histórico de alterações, mas ampliaria a complexidade sem ser necessário aos KPIs deste projeto.

Uma estratégia baseada só em `MAX(ModifiedDate)` seria mais curta, porém dependeria de todos os escritores atualizarem a coluna, de tratamento correto de empates e transações tardias e de uma política separada para exclusões. O DEFAULT de uma coluna não prova que todo UPDATE modifica sua data. CT foi escolhido para retirar essa dependência e detectar também alterações sem mudança de ModifiedDate.

Pré-condição: o grupo controla a instância SQL Server didática e pode habilitar CT e snapshot isolation. Em fonte corporativa sem essa permissão, a decisão precisaria ser renegociada com o responsável pela origem. A ETL normal só lê o OLTP; `prepare-source` é uma preparação administrativa separada.

## Tabelas rastreadas e propagação

| Alteração observada no CT | Registros que precisam ser reavaliados | Motivo |
|---|---|---|
| SalesOrderHeader | Todos os itens dos pedidos alterados | Cliente, território, vendedor, status, canal e datas são atributos do cabeçalho replicados no grão item. |
| SalesOrderDetail | Itens dos pedidos envolvidos nas chaves CT | Permite reconstruir o estado do pedido e detectar itens excluídos; as linhas inalteradas não são regravadas. |
| Product | Produtos com ProductID alterado | Atualiza atributos do produto ou sua nova subcategoria. |
| ProductSubcategory | Produtos associados às subcategorias alteradas | Nome e vínculo de categoria estão achatados na dimensão. |
| ProductCategory | Produtos das subcategorias das categorias alteradas | A categoria é atributo de dim_produto, mesmo sem UPDATE em Product. |
| Customer | Clientes alterados | Identidade e tipo de cliente, PersonID ou StoreID podem mudar. |
| Person | Clientes ligados por PersonID e vendedores ligados por BusinessEntityID | Uma pessoa participa de dois papéis distintos; ambos recebem seu nome atual. |
| Store | Clientes ligados por StoreID | O nome da loja é incorporado à dimensão cliente. |
| SalesTerritory | Territórios alterados | Nome, país e grupo da dimensão recebem estado atual. |
| SalesPerson | Vendedores alterados | Identifica novos/excluídos vendedores; nome vem de Person. |

O grafo de dependências é implementado em `etl/source.py`, em consultas `UNION` de chaves distintas. Não há leitura completa de Product, Customer ou fato em um ciclo incremental normal: as consultas retornam somente membros afetados ou registros necessários para reconstruir os pedidos afetados. O otimizador ainda pode escolher varreduras físicas; a promessa de incrementalidade se refere ao conjunto lógico extraído e escrito, não à ausência absoluta de qualquer scan no plano de execução.

Se uma categoria for removida, os relacionamentos do OLTP precisam continuar válidos. Alterações nos produtos/subcategorias que desfazem esses relacionamentos também são capturadas. Uma dimensão removida da origem recebe `ativo_origem=false` no DW. Não há apagamento em cascata de fatos causado por exclusão de dimensão.

## Ciclo completo

1. **Trava de execução.** O PostgreSQL adquire uma advisory lock de sessão. Outra carga ou reconciliação não pode executar simultaneamente o mesmo pipeline. A trava cobre extração, escrita e checkpoint; não é adquirida somente no final.
2. **Auditoria inicial.** A ETL cria uma execução `running`. Com a trava obtida, um registro `running` de processo anterior interrompido pode ser marcado como falha sem concluir que houve carga confirmada.
3. **Leitura do checkpoint.** O controle fornece `versao` e `identidade_origem`. Ausência de controle significa primeira carga; `--resync` é uma decisão explícita de leitura completa.
4. **Snapshot da origem.** Uma única conexão inicia transação `SNAPSHOT`. Todas as validações de versão, chaves CT, dimensões e itens são lidas nessa mesma transação.
5. **Validação da retenção.** A versão anterior precisa ser maior ou igual a `CHANGE_TRACKING_MIN_VALID_VERSION` de todas as dez tabelas e menor ou igual à versão atual. CT desabilitado também causa falha. Igualdade com a mínima é aceita.
6. **Limite superior consistente.** Depois da validação, a transação lê `CHANGE_TRACKING_CURRENT_VERSION`. Ela será o próximo checkpoint. Mudanças confirmadas depois do snapshot serão vistas no ciclo seguinte. Não basta filtrar versões por teto com leituras comuns: isso poderia combinar estados de momentos distintos.
7. **Extração.** Na carga inicial, lê dimensões e todos os itens. Na incremental, materializa chaves CT em tabelas temporárias SQL Server, calcula dependências e lê somente os conjuntos afetados. Uma transação que ainda não confirmou não aparece no CT do snapshot.
8. **Encerramento da leitura.** Após materializar o lote em memória, confirma a transação de leitura e fecha a conexão de origem. O lote transporta versão, identidade, membros, pedidos afetados, itens e contagens. Reduz-se assim o tempo de snapshot aberto durante a escrita no PostgreSQL.
9. **Dimensões antes da fato.** Dentro de uma única transação PostgreSQL, faz upserts SCD1 por NK única, preservando SK. Gera calendário contínuo cobrindo as datas necessárias e carrega mapas NK→SK. Uma NK obrigatória ausente gera erro.
10. **Staging e qualidade.** Faz COPY dos itens para staging temporário PostgreSQL. Valida quantidade, preço, desconto, status, datas e a reconciliação da fórmula com LineTotal. PK temporária detecta duplicação do grão. Constraints e FKs da fato complementam as validações.
11. **Exclusões e upsert.** Apaga apenas itens dos pedidos afetados que não existem no snapshot. Insere itens novos e atualiza itens cujos dados materiais diferem. Linhas inalteradas reavaliadas por dependência preservam `carregado_em`. Na ressincronização, a comparação de exclusões abrange a fato inteira.
12. **Checkpoint e sucesso.** Confere quantidade e receita dos itens do staging contra a fato, grava o checkpoint e marca a execução como sucesso na mesma transação dos dados. Só então ocorre COMMIT. Por fim, fecha a sessão e libera a trava.

Cada etapa tem uma função verificável: identificar mudanças, garantir consistência, resolver relações, validar, gravar sem duplicação ou permitir recuperação. Não há `TRUNCATE` da fato em cada carga e não se avança a versão antes de confirmar os dados.

## Exemplo de versões

Suponha checkpoint 100 e snapshot atual 105. A ETL extrai as chaves mudadas após 100 visíveis nesse snapshot e confirma o DW junto com 105. Uma alteração confirmada na origem com versão 106 enquanto o lote é escrito não é perdida: entra no próximo ciclo, iniciado de 105. Não se usa a data atual do computador nem a data do maior pedido como controle.

Se o PostgreSQL falhar antes do COMMIT, todos os upserts e exclusões do lote e a gravação de 105 são revertidos. O checkpoint permanece 100; o próximo ciclo reaplica as mudanças necessárias. Se o COMMIT acontecer, mas o processo cair antes de imprimir a mensagem, dados e checkpoint já estão confirmados. A próxima leitura do controle evita duplicação. Não é necessária transação distribuída porque a origem é somente lida e o marcador de consumo reside no mesmo banco da escrita.

O transporte tem possibilidade de repetição de mudanças; o estado final do destino é idempotente por chaves únicas e upserts condicionais. Isso não deve ser anunciado como entrega exatamente uma vez de todos os eventos, pois CT não é um log completo de eventos.

## Falhas, retenção e recuperação

A retenção configurada é sete dias. Ela deve ser maior que o pior intervalo esperado entre cargas bem-sucedidas, com margem operacional. Uma parada longa pode expirar o checkpoint. O programa falha explicitamente em vez de continuar e perder alterações silenciosamente. Execute `run --resync` para reler um snapshot completo, corrigir dimensões, remover fatos ausentes e confirmar uma nova versão. Essa exceção completa é documentada e não substitui a operação incremental normal.

A identidade combina um UUID registrado na preparação da base e as versões de habilitação CT das tabelas. Ela ajuda a detectar troca da origem ou reabilitação do mecanismo. Versão atual menor que o checkpoint também é rejeitada. Uma restauração pode recuperar metadados antigos e nem toda divergência de linhagem será detectada automaticamente; **após qualquer restauração ou alteração administrativa do CT, faça ressincronização explícita**, mesmo que a comparação de versões não reclame.

Falha por qualidade não é descartada para continuar a carga. O lote inteiro é revertido e a causa deve ser corrigida na origem ou na regra de transformação antes de tentar novamente. Não foi implementada quarentena parcial, porque ela exigiria checkpoint por subconjunto ou outro mecanismo para não perder registros rejeitados.

O log registra contagens de chaves CT por tabela, linhas de dimensão extraídas/escritas, pedidos afetados e fatos extraídos/escritos/excluídos. `versao_origem` na fato identifica a versão do lote da última mudança material nela carregada, não a versão individual exata do registro no CT. `atualizado_em` nas dimensões mede a gravação no DW, não a data histórica de mudança do negócio.

## Limites assumidos

Não há agendador automático, histórico SCD2, captura de todas as versões intermediárias, tratamento de fontes múltiplas nem streaming. O lote em memória simplifica a implementação para AdventureWorks; para milhões de registros, seria necessário staging persistente ou partições paginadas sob snapshot, mantendo confirmação atômica. Não há promessa de conversão de moedas nem de lucro histórico. Uma auditoria completa (`verify`) lê toda a origem de propósito e é separada da ETL incremental.

O uso de contas administrativas nas instruções é restrito ao laboratório. Em implantação compartilhada, separe a conta que habilita CT da conta de execução: esta precisa SELECT nas tabelas utilizadas e VIEW CHANGE TRACKING, além das permissões mínimas de leitura de metadados empregadas. As portas do Compose são publicadas apenas em loopback.

## Fontes

[Microsoft — trabalhar com Change Tracking](https://learn.microsoft.com/en-us/sql/relational-databases/track-changes/work-with-change-tracking-sql-server?view=sql-server-ver17) sustenta a ordem de validação, versão e leitura sob snapshot. [PostgreSQL 17 — INSERT](https://www.postgresql.org/docs/17/sql-insert.html) documenta o uso de ON CONFLICT. As regras específicas de dependências, população dos KPIs e recuperação deste projeto são decisões da implementação.
