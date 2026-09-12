"""Regras puras, sem acesso aos bancos; Decimal evita erros de ponto flutuante."""
from datetime import date, datetime
from decimal import Decimal


def date_key(value):
    if value is None:
        return None
    return value.year * 10000 + value.month * 100 + value.day


def validate_line(row):
    qty = int(row['quantidade'])
    price = Decimal(row['preco_unitario'])
    rate = Decimal(row['taxa_desconto'])
    net = Decimal(row['receita_liquida'])
    if qty <= 0 or price < 0 or not 0 <= rate <= 1 or net < 0:
        raise ValueError(f"Medida inválida no item {row['item_id']}")
    if abs(qty * price * (1-rate) - net) > Decimal('0.000001'):
        raise ValueError(f"LineTotal inconsistente no item {row['item_id']}")
    if not 1 <= int(row['status']) <= 6:
        raise ValueError('Status fora do domínio esperado do AdventureWorks2016')
    if row['data_pedido'] is None or row['data_vencimento'] is None:
        raise ValueError('Datas obrigatórias ausentes')
    if row['data_vencimento'] < row['data_pedido']:
        raise ValueError('Vencimento anterior ao pedido')
    if row['data_envio'] is not None and row['data_envio'] < row['data_pedido']:
        raise ValueError('Expedição anterior ao pedido')


def checked_version(last, current, minimums):
    if current is None or any(v is None for v in minimums):
        raise RuntimeError('Change Tracking não habilitado em todas as tabelas')
    if last is not None and (last > current or any(last < v for v in minimums)):
        raise RuntimeError('Checkpoint inválido/expirado. Execute run --resync conscientemente.')


def json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(type(value).__name__)
