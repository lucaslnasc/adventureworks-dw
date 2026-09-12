# Fonte editável e geração do artigo

O texto está em [ARTIGO.md](ARTIGO.md). Os marcadores `{{DIAGRAMA}}`, `{{DEFINICOES_KPIS}}`, `{{RECONCILIACAO}}`, `{{RESUMO_KPIS}}` e `{{CHAVES_ESTRANGEIRAS}}` inserem componentes gerados. Eles não aparecem no PDF. Os apêndices são montados automaticamente a partir de `dicionario.json`, scripts SQL e `evidence/kpis.json`.

Em um Python local com acesso às fontes Arial:

```powershell
python -m pip install -r requirements-docs.txt
python scripts/build_article.py
```

No Windows, o gerador procura Arial em `C:/Windows/Fonts`. Em outro ambiente, defina `ARIAL_FONT_DIR` para uma pasta que contenha `arial.ttf`, `arialbd.ttf` e `ariali.ttf`. O gerador informa a ausência dessas fontes sem substituir silenciosamente a tipografia institucional.

O resultado é `docs/artigo_unisales_adventureworks.pdf`. O gerador usa A4, margens de 3 cm superior/esquerda e 2 cm inferior/direita, corpo Arial 12, tabelas e quadros Arial 10, identificação e cabeçalho em cada continuação. Tabelas pequenas são mantidas inteiras; tabelas maiores são divididas em partes identificadas.

Após editar, abra o PDF e confira todas as páginas. Uma nova execução de testes/exportação deve atualizar também as datas e afirmações na seção de resultados de ARTIGO.md e em evidence/RESULTADOS.md. O conteúdo numérico das tabelas/apêndices é lido dos JSONs; datas mencionadas em parágrafos não são substituídas automaticamente.

O artigo referencia o manifesto SHA-256 dos arquivos testados em `evidence/validacao.json`. Não use o hash de um commit anterior como se ele identificasse alterações que ainda não existiam naquele commit.
