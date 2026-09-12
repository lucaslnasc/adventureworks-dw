from datetime import date
from decimal import Decimal as D
import pytest
from etl.transform import date_key, validate_line, checked_version


def line():
    return dict(item_id=1,quantidade=2,preco_unitario=D('100'),taxa_desconto=D('.1'),
                receita_liquida=D('180'),status=5,data_pedido=date(2024,1,1),
                data_vencimento=date(2024,1,10),data_envio=None)


def test_money_and_dates():
    validate_line(line())
    assert date_key(date(2024,2,29)) == 20240229
    assert date_key(None) is None


@pytest.mark.parametrize('key,value',[('quantidade',0),('preco_unitario',D('-1')),
    ('taxa_desconto',D('1.1')),('receita_liquida',D('179')),('status',9),
    ('data_envio',date(2023,1,1)),('data_vencimento',date(2023,1,1))])
def test_bad_data_rejected(key,value):
    row = line()
    row[key]=value
    with pytest.raises(ValueError):
        validate_line(row)


@pytest.mark.parametrize('last,current,minimums',[(4,8,[5,5]),(9,8,[0]),(1,None,[0]),(1,3,[None])])
def test_invalid_checkpoints(last,current,minimums):
    with pytest.raises(RuntimeError):
        checked_version(last,current,minimums)


def test_valid_checkpoint_boundary():
    checked_version(5,8,[5,4])
    checked_version(None,8,[8,8])
