"""Gera o artigo a partir de fontes editaveis e evidencias versionadas."""
from pathlib import Path
import os, re, json, textwrap
from html import escape
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, Table, TableStyle, KeepTogether
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT=Path(__file__).resolve().parents[1]
FONT=Path(os.getenv('ARIAL_FONT_DIR','C:/Windows/Fonts'))
for name,filename in [('Arial','arial.ttf'),('Arial-Bold','arialbd.ttf'),('Arial-Italic','ariali.ttf')]:
    if not (FONT/filename).is_file():raise SystemExit('Configure ARIAL_FONT_DIR com os arquivos Arial: arial.ttf, arialbd.ttf e ariali.ttf.')
    pdfmetrics.registerFont(TTFont(name,str(FONT/filename)))
pdfmetrics.registerFontFamily('Arial',normal='Arial',bold='Arial-Bold',italic='Arial-Italic',boldItalic='Arial-Bold')
ST={
 'body':ParagraphStyle('body',fontName='Arial',fontSize=12,leading=14,spaceAfter=6,alignment=TA_JUSTIFY),
 'center':ParagraphStyle('center',fontName='Arial',fontSize=12,leading=14,spaceAfter=6,alignment=TA_CENTER),
 'title':ParagraphStyle('title',fontName='Arial-Bold',fontSize=12,leading=14,spaceAfter=12,alignment=TA_CENTER),
 'h1':ParagraphStyle('h1',fontName='Arial-Bold',fontSize=12,leading=14,spaceBefore=12,spaceAfter=0,keepWithNext=True),
 'h2':ParagraphStyle('h2',fontName='Arial',fontSize=12,leading=14,spaceBefore=12,spaceAfter=0,keepWithNext=True),
 'cell':ParagraphStyle('cell',fontName='Arial',fontSize=10,leading=12,alignment=TA_LEFT),
 'caption':ParagraphStyle('caption',fontName='Arial',fontSize=10,leading=12,spaceAfter=6),
 'continuation':ParagraphStyle('continuation',fontName='Arial',fontSize=10,leading=12,alignment=TA_RIGHT,spaceAfter=4),
 'ref':ParagraphStyle('ref',fontName='Arial',fontSize=12,leading=14,spaceAfter=14,alignment=TA_LEFT),
 'code':ParagraphStyle('code',fontName='Courier',fontSize=10,leading=12,spaceAfter=8,alignment=TA_LEFT),
}
WIDTH=16*cm
story=[]
def para(text,style='body'):
    value=escape(str(text))
    value=re.sub(r'https://[^\s<>]+',lambda m:'<link href="'+m[0].rstrip('.,')+'" color="#000000">'+m[0]+'</link>',value)
    return Paragraph(value,ST[style])

def tab(headers,rows,widths,closed=False):
    cells=[[Paragraph('<b>'+escape(str(v))+'</b>',ST['cell']) for v in headers]]
    cells.extend([[para(v,'cell') for v in row] for row in rows])
    t=Table(cells,colWidths=[x*cm for x in widths],hAlign='LEFT')
    rules=[('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),
           ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
           ('LINEABOVE',(0,0),(-1,0),.7,colors.black),('LINEBELOW',(0,0),(-1,0),.5,colors.black),
           ('LINEBELOW',(0,-1),(-1,-1),.7,colors.black)]
    if closed:rules.append(('GRID',(0,0),(-1,-1),.4,colors.grey))
    t.setStyle(TableStyle(rules))
    return t

def table_block(title,headers,rows,widths,source,closed=False,new_page=False):
    if new_page:story.append(PageBreak())
    # Divide antes da composicao: cada parte cabe inteira e repete titulo/cabecalho.
    chunks=[];chunk=[]
    for row in rows:
        candidate=chunk+[row]
        if chunk and tab(headers,candidate,widths,closed).wrap(WIDTH,700)[1]>530:
            chunks.append(chunk);chunk=[]
        chunk.append(row)
    if chunk:chunks.append(chunk)
    for i,part in enumerate(chunks):
        if i:story.append(PageBreak())
        label=title
        headings=[para(label)]
        if len(chunks)>1:
            mark='('+('continua' if i==0 else 'conclusão' if i==len(chunks)-1 else 'continuação')+')'
            headings.append(para(mark,'continuation'))
        tail=source if i==len(chunks)-1 else 'Continua na página seguinte.'
        story.append(KeepTogether(headings+[Spacer(1,6),tab(headers,part,widths,closed),Spacer(1,6),para(tail,'caption'),Spacer(1,8)]))

recon=json.loads((ROOT/'evidence/reconciliation.json').read_text(encoding='utf-8'))
kpis=json.loads((ROOT/'evidence/kpis.json').read_text(encoding='utf-8'))
validation=json.loads((ROOT/'evidence/validacao.json').read_text(encoding='utf-8'))
def stamp(payload):
    dt=datetime.fromisoformat(payload['gerado_em']).astimezone(timezone(timedelta(hours=-3)))
    return dt.strftime('%d/%m/%Y, %H:%M:%S')+' (UTC-3), versão CT '+str(payload['versao'])
def pt(value,n=2):return f'{Decimal(value):,.{n}f}'.replace(',','@').replace('.',',').replace('@','.')
labels=['Receita bruta','Descontos comerciais','Receita líquida comercial','Unidades vendidas','Pedidos expedidos','Ticket médio','Taxa ponderada de desconto','Clientes com compra','Crescimento mensal','Expedição até vencimento']
def special(name):
    if name=='DIAGRAMA':
        pic=Image(str(ROOT/'docs/modelo_estrela.png'))
        pic.drawHeight=WIDTH*pic.imageHeight/pic.imageWidth;pic.drawWidth=WIDTH
        story.append(KeepTogether([para('Figura 1 - Modelo estrela de vendas'),Spacer(1,12),pic,Spacer(1,6),para('Fonte: elaboração própria (2026).','caption'),Spacer(1,12)]))
    elif name=='DEFINICOES_KPIS':
        rules=['Soma de quantidade × preço','Soma de bruta - líquida','Soma de LineTotal','Soma de quantidade','Contagem distinta de pedido_id','Receita líquida ÷ pedidos distintos','100 × descontos ÷ receita bruta','Contagem distinta de cliente_sk','Variação frente ao mês calendário anterior','100 × pedidos pontuais ÷ pedidos com data de envio']
        table_block('Quadro 1 - Indicadores implementados',['Nº','Indicador','Regra principal'],[[i+1,labels[i],rules[i]] for i in range(10)],[.8,6,9.2],'Fonte: elaboração própria (2026).',True)
    elif name=='RECONCILIACAO':
        rows=[['Itens na origem',recon['itens_origem']],['Itens no DW',recon['itens_dw']],['Itens divergentes',recon['itens_divergentes']],['Receita da origem - todos os status',recon['receita_origem_todos_status']],['Receita do DW - todos os status',recon['receita_dw_todos_status']],['Versão de sincronização',recon['versao']],['Resultado',recon['resultado']]]
        table_block('Tabela 1 - Reconciliação do AdventureWorks',['Campo','Retorno'],rows,[9,7],'Fonte: evidence/reconciliation.json; '+stamp(recon)+'. Valores em UM; separador decimal do JSON preservado.')
    elif name=='RESUMO_KPIS':
        vals=[]
        for i,(view,rows) in enumerate(kpis['indicadores'].items()):
            v=list(rows[0].values())[0] if rows else None
            if i in [0,1,2,5]:s=pt(v)+' UM'
            elif i==6:s=pt(v,4)+'%'
            elif i==8:s=str(len(rows))+' meses; Apêndice C'
            elif i==9:s=pt(rows[0]['expedicao_no_prazo_pct'],4)+'%'
            else:s=pt(v,0)
            vals.append([i+1,labels[i],s])
        table_block('Tabela 2 - Indicadores do AdventureWorks',['Nº','Indicador','Resultado'],vals,[.8,8.2,7],'Fonte: evidence/kpis.json; '+stamp(kpis)+'. Síntese arredondada; valores completos no Apêndice C.')
    elif name=='CHAVES_ESTRANGEIRAS':
        story.append(Paragraph('SELECT conname, convalidated FROM pg_constraint<br/>WHERE conrelid = \'dw.fato_venda\'::regclass<br/>AND contype = \'f\' ORDER BY conname;',ST['code']))
        table_block('Tabela 3 - Chaves estrangeiras da fato',['conname','convalidated'],[[a,str(b).lower()] for a,b in validation['fks']],[12,4],'Fonte: catálogo PostgreSQL registrado em evidence/validacao.json, 12/09/2026.')

references=False
for line in (ROOT/'docs/ARTIGO.md').read_text(encoding='utf-8').splitlines():
    line=line.strip()
    if not line:continue
    if line.startswith('{{'):
        special(line[2:-2]);continue
    if line.startswith('# '):story.append(para(line[2:],'title'));continue
    if line.startswith('### '):story.append(para(line[4:],'h2'));continue
    if line.startswith('## '):
        if line=='## REFERÊNCIAS':story.append(PageBreak());references=True
        story.append(para(line[3:],'h1'));continue
    style='ref' if references else 'body'
    if line.startswith(('ANDRÉ','BRENO','LUCAS','SERGIO','Centro Universitário','Curso:','Disciplina:','Professor:','Vitória,')):style='center'
    story.append(para(line,style))

story.extend([PageBreak(),para('APÊNDICE A - DICIONÁRIO DO DATA WAREHOUSE','h1'),para('PK identifica a linha; NK é a chave da origem; SK é a chave substituta; FK é a referência dimensional. As dimensões descritivas usam SCD1. Os tipos e a nulabilidade correspondem ao DDL e ao catálogo verificado.')])
dictionary=json.loads((ROOT/'docs/dicionario.json').read_text(encoding='utf-8'))
for idx,(name,rows) in enumerate(dictionary.items(),2):
    table_block(f'Quadro {idx} - {name}',['Campo','Tipo / nulo','Origem e significado'],[[r[0],r[1]+' / '+r[2],r[3]] for r in rows],[4.3,3.5,8.2],'Fonte: elaboração própria (2026), com base no DDL e no dicionário do projeto.',True)
story.extend([para('Relacionamentos e restrições','h2'),para('A PK da fato é (pedido_id, item_id). As NKs descritivas são únicas. São oito FKs; somente data_envio_sk admite nulo entre elas. Não há FKs entre dimensões. Quantidade é positiva; preço e receita são não negativos; desconto está entre zero e um; status varia de um a seis. A fórmula de LineTotal admite tolerância de 0,000001 UM.')])

story.extend([PageBreak(),para('APÊNDICE B - SCRIPTS DOS DEZ INDICADORES','h1'),para('SQL PostgreSQL extraído dos arquivos versionados. A primeira view estabelece a população de vendas expedidas; os retornos das dez consultas estão no Apêndice C.')])
schema=(ROOT/'sql/postgres/001_schema.sql').read_text(encoding='utf-8')
base=re.search(r'CREATE OR REPLACE VIEW dw.v_vendas AS\n.*?;',schema,re.S).group(0)
sql=base+'\n\n'+(ROOT/'sql/postgres/002_kpis.sql').read_text(encoding='utf-8')
for block in re.split(r'\n\s*\n',sql):
    if not block.strip():continue
    lines=[]
    for line in block.splitlines():lines.extend(textwrap.wrap(line,73,replace_whitespace=False,break_long_words=False,break_on_hyphens=False) or [''])
    text='<br/>'.join(escape(x).replace(' ','&#160;') for x in lines)
    story.append(KeepTogether([Paragraph(text,ST['code'])]))

story.extend([PageBreak(),para('APÊNDICE C - CONSULTAS E RETORNOS','h1'),para('Resultados de evidence/kpis.json, '+stamp(kpis)+'. Valores escalares preservam as casas decimais e o ponto do JSON. A série mensal apresenta receitas com seis casas e crescimento com quatro casas decimais; NULL indica ausência de base válida.')])
for i,(view,rows) in enumerate(kpis['indicadores'].items(),1):
    title=f'C.{i} {labels[i-1]}'
    query='SELECT * FROM dw.'+view+(' ORDER BY mes' if i==9 else '')+';'
    if i==9:
        story.append(PageBreak())
        story.extend([para(title,'h2'),para(query,'code')])
        table_block('Tabela C.9 - Crescimento mensal',['Mês','Receita (UM)','Receita anterior (UM)','Crescimento (%)'],[[r['mes'],pt(r['receita'],6),'NULL' if r['receita_anterior'] is None else pt(r['receita_anterior'],6),'NULL' if r['crescimento_pct'] is None else pt(r['crescimento_pct'],4)] for r in rows],[2.5,4.8,4.8,3.9],'Fonte: evidence/kpis.json; '+stamp(kpis)+'.')
    else:
        data=[[k,str(v)] for k,v in rows[0].items()]
        story.append(KeepTogether([para(title,'h2'),para(query,'code'),tab(['Campo retornado','Valor'],data,[8.8,7.2]),Spacer(1,6),para('Fonte: evidence/kpis.json; '+stamp(kpis)+'.','caption'),Spacer(1,10)]))

out=ROOT/'docs/artigo_unisales_adventureworks.pdf'
doc=SimpleDocTemplate(str(out),pagesize=(21*cm,29.7*cm),leftMargin=3*cm,rightMargin=2*cm,topMargin=3*cm,bottomMargin=2*cm,
 title='Modelagem dimensional de vendas e ETL incremental com AdventureWorks',author='André Alves da Silva; Breno dos Santos Guimarães; Lucas de Lima Nascimento; Sergio Paulo de Andrade')
def footer(canvas,doc):
    canvas.setFont('Arial',10);canvas.drawRightString(19*cm,1*cm,str(doc.page))
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print('PDF gerado:',out)
