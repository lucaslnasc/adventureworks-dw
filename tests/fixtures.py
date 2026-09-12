from datetime import date
from decimal import Decimal as D
from etl.source import Batch


def sample_batch(version=10):
    dims = {
      'produto':[dict(produto_id=i,nome='Produto '+str(i),numero_produto='P'+str(i),
                       cor=None,subcategoria='Subcategoria',categoria='Categoria') for i in (1,2,3)],
      'cliente':[dict(cliente_id=i,nome='Cliente '+str(i),tipo='Pessoa') for i in (1,2)],
      'territorio':[], 'vendedor':[]}
    def fact(order,item,product,qty,price,rate,net,month,customer,status=5):
        return dict(pedido_id=order,item_id=item,produto_id=product,cliente_id=customer,
          territorio_id=0,vendedor_id=0,canal_sk=1 if order==1 else 0,status=status,
          quantidade=qty,preco_unitario=D(price),taxa_desconto=D(rate),receita_liquida=D(net),
          data_pedido=date(2024,month,10),data_vencimento=date(2024,month,15),
          data_envio=date(2024,month,12 if order==1 else 16))
    facts=[fact(1,1,1,2,'100','.1','180',1,1),fact(1,2,2,1,'50','0','50',1,1),
           fact(2,3,3,3,'20','0','60',3,2),fact(3,4,1,1,'40','.25','30',3,1,status=6)]
    affected={k:[r[k+'_id'] for r in v] for k,v in dims.items()}
    return Batch(version,'fixture-epoch',True,dims,affected,[1,2,3],facts,{})


def delta(version, facts=None, orders=None):
    return Batch(version,'fixture-epoch',False,{k:[] for k in ('produto','cliente','territorio','vendedor')},
                 {k:[] for k in ('produto','cliente','territorio','vendedor')},orders or [],facts or [],{})
