# Como abrir e editar o modelo estrela

O diagrama pronto está em `modelo_estrela.png` e em `modelo_estrela.svg`. A versão editável por texto é `modelo_estrela.puml`.

Use o [servidor oficial PlantUML](https://www.plantuml.com/plantuml/uml). Copie o conteúdo de `modelo_estrela.puml`, incluindo `@startuml` e `@enduml`, para o editor e gere a figura. O [manual do servidor](https://plantuml.com/server) explica a interface. Também é possível usar PlantUML localmente, com Java e a extensão de sua IDE.

O PNG/SVG incluído usa uma disposição fixa para facilitar a leitura no artigo; PlantUML pode reposicionar as caixas ao regenerar a imagem. Os dois representam o mesmo contrato de tabelas e relações. Não crie ligações entre categoria, subcategoria e produto: esses atributos pertencem à mesma dimensão. O controle `etl` fica fora do diagrama multidimensional.

No DBeaver, abra o diagrama ER das tabelas do esquema `dw` depois de executar o DDL. Essa visualização apresenta as FKs reais do PostgreSQL e permite conferir as três relações de data. Uma dimensão pode ter zero ou muitos fatos; produto e cliente são obrigatórios no item, envio é opcional e vendedor/território ausentes usam membro técnico.
