-- Área de stage no PostgreSQL: recebe da origem apenas os registros alterados,
-- ainda com as chaves e nomes do OLTP. As regras de negócio ficam na carga do DW,
-- o que mantém curto o tempo de leitura no banco de produção.
CREATE SCHEMA IF NOT EXISTS stage;

-- Um lote por grupo: guarda a faixa de versões do Change Tracking extraída.
-- versao_de NULL indica carga completa.
CREATE TABLE IF NOT EXISTS stage.lote (
    grupo text PRIMARY KEY,
    execucao_id uuid NOT NULL,
    versao_de bigint,
    versao_ate bigint NOT NULL,
    identidade_origem text NOT NULL,
    linhas integer NOT NULL,
    extraido_em timestamptz NOT NULL DEFAULT now()
);

-- operacao: I = inserido, U = alterado (ou afetado por tabela relacionada), D = excluído.
CREATE TABLE IF NOT EXISTS stage.produto (
    operacao char(1) NOT NULL CHECK (operacao IN ('I','U','D')),
    product_id integer PRIMARY KEY,
    name text, product_number text, color text,
    subcategoria text, categoria text
);
CREATE TABLE IF NOT EXISTS stage.cliente (
    operacao char(1) NOT NULL CHECK (operacao IN ('I','U','D')),
    customer_id integer PRIMARY KEY,
    person_id integer, store_id integer,
    first_name text, middle_name text, last_name text, store_name text
);
CREATE TABLE IF NOT EXISTS stage.territorio (
    operacao char(1) NOT NULL CHECK (operacao IN ('I','U','D')),
    territory_id integer PRIMARY KEY,
    name text, country_region_code text, grupo text
);
CREATE TABLE IF NOT EXISTS stage.vendedor (
    operacao char(1) NOT NULL CHECK (operacao IN ('I','U','D')),
    business_entity_id integer PRIMARY KEY,
    first_name text, middle_name text, last_name text
);
-- Cabeçalhos de todos os pedidos afetados (alterados ou com itens alterados).
CREATE TABLE IF NOT EXISTS stage.pedido (
    operacao char(1) NOT NULL CHECK (operacao IN ('I','U','D')),
    sales_order_id integer PRIMARY KEY,
    order_date date, due_date date, ship_date date,
    customer_id integer, territory_id integer, sales_person_id integer,
    online_order_flag boolean, status smallint
);
CREATE TABLE IF NOT EXISTS stage.item (
    operacao char(1) NOT NULL CHECK (operacao IN ('I','U','D')),
    sales_order_id integer NOT NULL,
    sales_order_detail_id integer NOT NULL,
    product_id integer, order_qty integer,
    unit_price numeric(19,4), unit_price_discount numeric(19,4), line_total numeric(38,6),
    PRIMARY KEY (sales_order_id, sales_order_detail_id)
);
