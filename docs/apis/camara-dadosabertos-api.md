# Novo Dados Abertos

**Versão:** v1.0  
**Base URL:** `https://dadosabertos.camara.leg.br/api/v2/`  
**Fonte:** https://dadosabertos.camara.leg.br/swagger/api.html (spec: https://dadosabertos.camara.leg.br/api/v2/api-docs)

**Versão: 0.4.344 - 08/18/2026 02:19 PM** - _confira o que mudou na [página de Notícias](http://dadosabertos.camara.leg.br/news/noticias.html)_

Bem vindo à nova versão do serviço **Dados Abertos** da Câmara dos Deputados!

Esta versão pode entregar dados puros em formatos JSON e XML, e tenta se aderir ao máximo à arquitetura REST.

Nesta página você pode conhecer e experimentar as URLs de acesso aos dados, os parâmetros de *query string* que podem ser aplicados para filtrar e selecionar resultados, e as estruturas de dados que são retornadas.

Além do método HTTP GET, você também pode usar o método HEAD com qualquer dos serviços.

Por padrão, todos os serviços de listagens retornam 15 itens, e o limite por requisição é de 100 itens.

 **ATENÇÃO:** Esta versão é ainda incompleta, sujeita a mudanças e não substitui a [versão original do **Dados Abertos**](http://www2.camara.leg.br/transparencia/dados-abertos/dados-abertos-legislativo). Caso você encontre problemas ou queira dar sugestões, por favor entre em [contato](https://dadosabertos.camara.leg.br/contact/contact.html).

## Índice

Total: 79 operações em 11 grupos.

- [Blocos](#blocos) (3)
- [Deputados](#deputados) (16)
- [Eventos](#eventos) (10)
- [Frentes](#frentes) (3)
- [Grupos](#grupos) (4)
- [Legislaturas](#legislaturas) (2)
- [Partidos](#partidos) (4)
- [Proposições](#proposições) (7)
- [Referências](#referências) (19)
- [Votações](#votações) (4)
- [Órgãos](#órgãos) (7)

## Blocos

### GET `/blocos`

**Lista de dados sobre os blocos partidários**

Nas atividades parlamentares, partidos podem se juntar em __blocos partidários__. Quando associados, os partidos passam a trabalhar como se fossem um "partidão", com um só líder e um mesmo conjunto de vice-líderes.

Os blocos só podem existir até o fim da legislatura em que foram criados: na legislatura seguinte, os mesmos partidos, se associados, formam um novo bloco.

Este recurso é uma lista dos blocos em atividade no momento da requisição. Se forem passados números de legislaturas com o parâmetro _idLegislatura_, são listados também os blocos formados e extintos nessas legislaturas.

`operationId`: `getBlocos`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | query | não | array |  | Número(s) identificador(es) de um ou mais bloco(s), separados por vírgulas. |
| `idLegislatura` | query | não | array |  | Número(s) identificador(es) de uma ou mais legislatura(s), separados por vírgulas. Se presente, faz com que sejam retornados todos os blocos que existiram nessa(s) legislatura(s). |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. |
| `ordem` | query | não | string |  | O sentido da ordenação: `asc` para A a Z ou 0 a 9, e `desc` para Z a A ou 9 a 0. |
| `ordenarPor` | query | não | string |  | Nome do campo pelo qual a lista será ordenada: `idLegislatura`, `id` ou `nome`. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoBloco](#resultadobloco)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoBloco](#resultadobloco)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoBloco](#resultadobloco)

### GET `/blocos/{id}`

**Informações sobre um bloco partidário específico**

Retorna informações sobre o bloco identificado por `{id}` além daquelas obtidas na listagem.

`operationId`: `obterBlocoID`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Número identificador do bloco de partidos. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoBloco](#resultadobloco)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoBlocoID](#resultadoblocoid)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoBlocoID](#resultadoblocoid)

### GET `/blocos/{id}/partidos`

**Lista de partidos do bloco.**

Lista em que cada item contém os identificadores básicos de cada partido integrante do bloco identificado por {id}.

`operationId`: `obterBlocoIDPartidos`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Número identificador do bloco de partidos. |
| `data` | query | não | string |  | Data e hora, em formato `AAAA-MM-DDTHH:mm`, na qual se deseja saber os partidos que faziam parte do bloco `{id}`. Se omitida, é retornada a composição no momento da requisição. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoBloco](#resultadobloco)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoPartidos](#resultadopartidos)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoPartidos](#resultadopartidos)

## Deputados

### GET `/deputados`

**Listagem e busca de deputados, segundo critérios**

Retorna uma lista de dados básicos sobre deputados que estiveram em exercício parlamentar em algum intervalo de tempo.

Se não for passado um parâmetro de tempo, como `idLegislatura` ou `dataInicio`, a lista enumerará somente os deputados _em exercício no momento da requisição_.

`operationId`: `obterDeputados`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | query | não | array |  | Número(s) identificador(es) de um deputado, separados por vírgulas. |
| `nome` | query | não | string |  | Parte nome parlamentar. |
| `idLegislatura` | query | não | array |  | Número(s) identificador(es) de uma ou mais legislatura(s) de que os parlamentares tenham participado, separados por vírgulas. |
| `siglaUf` | query | não | array |  | Uma ou mais sigla(s) de unidades federativas (estados e Distrito Federal). Uma lista de siglas válidas pode ser obtida em `/referencias/deputados/siglaUf`. Se ausente, serão retornados deputados de todos os estados. |
| `siglaPartido` | query | não | array |  | Uma ou mais sigla(s) de partidos aos quais sejam filiados os deputados. Para obter as siglas válidas, consulte `/partidos`. __Atenção:__ partidos diferentes podem usar a mesma sigla em diferentes legislaturas! |
| `siglaSexo` | query | não | string |  | Letra que designe o gênero dos parlamentares que se deseja buscar, sendo M para masculino e F para feminino |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. |
| `dataInicio` | query | não | string |  | Data de início de um intervalo de tempo, no formato `AAAA-MM-DD`. |
| `dataFim` | query | não | string |  | Data de término de um intervalo de tempo, no formato `AAAA-MM-DD`. |
| `ordem` | query | não | string |  | O sentido da ordenação: `asc` para A a Z ou 0 a 9, e `desc` para Z a A ou 9 a 0. |
| `ordenarPor` | query | não | string |  | Nome do campo pelo qual a lista deve ser ordenada: `id`, `idLegislatura`, `nome`, `siglaUF` ou `siglaPartido` |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputado](#resultadodeputado)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputado](#resultadodeputado)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputado](#resultadodeputado)

### GET `/deputados/{id}`

**Informações detalhadas sobre um deputado específico**

Retorna os dados cadastrais de um parlamentar identificado por `{id}` que, em algum momento da história e por qualquer período, entrou em exercício na Câmara.

`operationId`: `obterDeputadoID_1`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Identificador numérico do parlamentar. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoID](#resultadodeputadoid)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoID](#resultadodeputadoid)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoID](#resultadodeputadoid)

### GET `/deputados/{id}/despesas`

**As despesas com exercício parlamentar do deputado**

Dá acesso aos registros de pagamentos e reembolsos feitos pela Câmara em prol do deputado identificado por `{id}`, a título da Cota para Exercício da Atividade Parlamentar, a chamada "cota parlamentar".

A lista pode ser filtrada por mês, ano, legislatura, CNPJ ou CPF de um fornecedor.

Se não forem passados os parâmetros de tempo, o serviço retorna os dados dos __seis meses anteriores à requisição__.

`operationId`: `getDeputadoDespesas`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Identificador numérico do parlamentar. |
| `idLegislatura` | query | não | array |  | Número(s) de uma ou mais legislatura(s), separados por vírgulas, em que tenham ocorrido as despesas. |
| `ano` | query | não | array |  | Um ou mais ano(s) de ocorrência das despesas. |
| `mes` | query | não | array |  | Um ou mais número(s) do(s) mês(es) de ocorrência das despesas. |
| `cnpjCpfFornecedor` | query | não | string |  | CNPJ de uma pessoa jurídica, ou CPF de uma pessoa física, fornecedora do produto ou serviço (apenas números) |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. |
| `ordem` | query | não | string |  | O sentido da ordenação: `asc` para A a Z ou 0 a 9, e `desc` para Z a A ou 9 a 0. |
| `ordenarPor` | query | não | string |  | Nome do campo pelo qual a lista deverá ser ordenada: qualquer um dos campos do retorno, e também `idLegislatura` |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoDespesas](#resultadodeputadodespesas)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoDespesas](#resultadodeputadodespesas)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoDespesas](#resultadodeputadodespesas)

### GET `/deputados/{id}/discursos`

**Os discursos feitos por um deputado em eventos diversos**

Retorna uma lista de informações sobre os pronunciamentos feitos pelo deputado identificado por {id} que tenham sido registrados, em quaisquer eventos, nos sistemas da Câmara.

Caso os parâmetros de tempo (`dataInicio`, `dataFim` e `idLegislatura`) não sejam configurados na requisição, são buscados os discursos ocorridos nos sete dias anteriores ao da requisição.

`operationId`: `getDeputadoDiscursos_1`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Identificador numérico do parlamentar. |
| `idLegislatura` | query | não | array |  | Número da(s) legislatura(s), separados por vírgulas, às quais os dados buscados devem corresponder. |
| `dataInicio` | query | não | string |  | Data de início de um intervalo de tempo, no formato `AAAA-MM-DD`. |
| `dataFim` | query | não | string |  | Data de término de um intervalo de tempo, no formato `AAAA-MM-DD`. |
| `ordenarPor` | query | não | string |  | Qual dos elementos da representação deverá ser usado para aplicar ordenação à lista. |
| `ordem` | query | não | string |  | O sentido da ordenação: `asc` para A a Z ou 0 a 9, e `desc` para Z a A ou 9 a 0. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoDiscurso](#resultadodeputadodiscurso)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoDiscurso](#resultadodeputadodiscurso)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoDiscurso](#resultadodeputadodiscurso)

### GET `/deputados/{id}/eventos`

**Uma lista de eventos com a participação do parlamentar**

Retorna uma lista de objetos `evento` nos quais a participação do parlamentar identificado por `{id}` era ou é prevista.

Um período de tempo pode ser delimitado para a busca.

Se não forem passados parâmetros de tempo, são retornados os eventos num período de __cinco dias__, sendo dois antes e dois depois do dia da requisição.

Os itens podem ser ordenados por `id`, `siglaOrgao` ou `dataHoraInicio`.

`operationId`: `getEvento`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | O identificador numérico do parlamentar. |
| `dataInicio` | query | não | string |  | Data de início de um intervalo de tempo, no formato `AAAA-MM-DD`. |
| `dataFim` | query | não | string |  | Data de término de um intervalo de tempo, no formato `AAAA-MM-DD`. |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. |
| `ordem` | query | não | string |  | O sentido da ordenação: `asc` para A a Z ou 0 a 9, e `desc` para Z a A ou 9 a 0. |
| `ordenarPor` | query | não | string |  | Qual dos elementos da representação deverá ser usado para aplicar ordenação à lista. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoEventos](#resultadodeputadoeventos)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoEventos](#resultadodeputadoeventos)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoEventos](#resultadodeputadoeventos)

### GET `/deputados/{id}/frentes`

**As frentes parlamentares das quais um deputado é integrante**

Retorna uma lista de informações básicas sobre as frentes parlamentares das quais o parlamentar identificado por `{id}` seja membro, ou, no caso de frentes existentes em legislaturas anteriores, tenha encerrado a legislatura como integrante.

`operationId`: `getDeputadoDiscursos`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | O identificador numérico do parlamentar. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoIdDeputadoMembro](#resultadoiddeputadomembro)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoIdDeputadoMembro](#resultadoiddeputadomembro)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoIdDeputadoMembro](#resultadoiddeputadomembro)

### GET `/deputados/{id}/historico`

**Lista de mudanças no exercício parlamentar de um deputado (versão GraphQL otimizada)**

Endpoint alternativo que busca o histórico do deputado via API GraphQL externa de alta performance, retornando a mesma estrutura de dados do endpoint v1.

`operationId`: `getDeputadoHistoricoV2`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Identificador numérico do parlamentar. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoHistorico](#resultadodeputadohistorico)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoHistorico](#resultadodeputadohistorico)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoHistorico](#resultadodeputadohistorico)

### GET `/deputados/{id}/historico-old`

**Lista de mudanças no exercício parlamentar de um deputado**

Um deputado pode, no meio de uma legislatura, mudar de partido ou de nome parlamentar, entrar em licença, ser afastado ou substituir outro deputado. Como essas mudanças se refletem em votações, ou na autoria e relatoria de proposições, pode se tornar difícil identificar um mesmo parlamentar em diferentes momentos de sua atuação na Câmara.

Este serviço retorna uma listagem com as diferentes situações de exercício parlamentar do deputado identificado por `{id}`, mesmo que a alteração registrada não tenha afetado o andamento do mandato.

`operationId`: `getDeputadoHistorico`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Identificador numérico do parlamentar. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoHistorico](#resultadodeputadohistorico)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoHistorico](#resultadodeputadohistorico)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoHistorico](#resultadodeputadohistorico)

### GET `/deputados/{id}/mandatosExternos`

**Outros cargos eletivos já exercidos pelo parlamentar em sua carreira.**

Retorna uma lista em que cada item traz informações básicas sobre um cargo para o qual o parlamentar identificado por {id} tenha sido eleito, em sua carreira política fora da Câmara dos Deputados. Estes dados são fornecidos pelo Tribunal Superior Eleitoral. A lista vem ordenada cronologicamente, por padrão.

`operationId`: `buscar_1`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | O identificador numérico do parlamentar. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoMandatoExterno](#resultadodeputadomandatoexterno)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoMandatoExterno](#resultadodeputadomandatoexterno)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoMandatoExterno](#resultadodeputadomandatoexterno)

### GET `/deputados/{id}/ocupacoes`

**Os empregos e atividades que o(a) deputado(a) já teve**

Enumera as atividades profissionais ou ocupacionais que o deputado identificado por `{id}` já teve em sua carreira e declarou à Câmara dos Deputados.

*ATENÇÃO:* Há problemas reconhecidos de estruturação nesses dados. Os casos encontrados podem ser reportados ao Centro de Documentação e Informação da Câmara, por meio do endereço https://camara.leg.br/faleconosco .

`operationId`: `getOcupacoesDeputados`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | O identificador numérico da entidade. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoOcupacoesDeputado](#resultadoocupacoesdeputado)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoOcupacoesDeputado](#resultadoocupacoesdeputado)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoOcupacoesDeputado](#resultadoocupacoesdeputado)

### GET `/deputados/{id}/orgaos`

**Os órgãos dos quais um deputado é integrante**

Retorna uma lista de órgãos, como as comissões e procuradorias, dos quais o deputado identificado por `{id}` participa ou participou durante um intervalo de tempo.

Cada item identifica um órgão, o cargo ocupado pelo parlamentar neste órgão (como presidente, vice-presidente, titular ou suplente) e as datas de início e fim da ocupação deste cargo.

Se não for passado algum parâmetro de tempo, são retornados os órgãos ocupados pelo parlamentar __no momento da requisição__. Neste caso a lista será vazia se o deputado não estiver em exercício.

`operationId`: `getDeputadoOrgaos`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | O identificador numérico do parlamentar. |
| `dataInicio` | query | não | string |  | Data de início de um intervalo de tempo, no formato `AAAA-MM-DD`. |
| `dataFim` | query | não | string |  | Data de término de um intervalo de tempo, no formato `AAAA-MM-DD`. |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. |
| `ordem` | query | não | string |  | O sentido da ordenação: `asc` para A a Z ou 0 a 9, e `desc` para Z a A ou 9 a 0. |
| `ordenarPor` | query | não | string |  | Nome do campo de dados pelo qual a lista deve ser ordenada: `idOrgao`, `siglaOrgao`, `nomeOrgao`, `titulo`, `dataInicio` ou `dataFim` |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoOrgaos](#resultadodeputadoorgaos)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoOrgaos](#resultadodeputadoorgaos)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoOrgaos](#resultadodeputadoorgaos)

### GET `/deputados/{id}/profissoes`

**As profissões que o parlamentar declarou à Câmara que já exerceu ou que pode exercer pela sua formação e/ou experiência**

Retorna uma lista de dados sobre profissões que o parlamentar identificado por `{id}` declarou à Câmara que já exerceu ou que pode exercer pela sua formação e/ou experiência.

`operationId`: `getDeputadoProfissao`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | O identificador numérico do parlamentar. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoProfissoes](#resultadodeputadoprofissoes)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoProfissoes](#resultadodeputadoprofissoes)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoDeputadoProfissoes](#resultadodeputadoprofissoes)

### GET `/legislaturas/{id}/lideres`

**Lista de líderes, vice-líderes e representantes na legislatura**

Retorna uma lista de parlamentares que ocuparam cargos de liderança ao longo da legislatura `{id}`. Cada item identifica um parlamentar, uma bancada (partido, bloco ou lideranças de situação e oposição), o título de liderança exercido e o período de exercício do parlamentar nesta posição.

`operationId`: `obterLideres_1`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | array |  | Número da legislatura da qual se deseja os dados. |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoLegislaturaIDLideres](#resultadolegislaturaidlideres)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoLegislaturaIDLideres](#resultadolegislaturaidlideres)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoLegislaturaIDLideres](#resultadolegislaturaidlideres)

### GET `/legislaturas/{id}/mesa`

**Quais deputados fizeram parte da Mesa Diretora em uma legislatura**

Retorna uma lista com dados básicos sobre todos os deputados que ocuparam algum posto na Mesa Diretora da Câmara em algum período de tempo dentro da legislatura identificada por `{id}`.

Normalmente, cada legislatura tem duas Mesas Diretoras, com presidente, dois vice-presidentes, quatro secretários parlamentares e os suplentes dos secretários.

`operationId`: `obterMesaPorId`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Número da legislatura da qual se deseja os dados. |
| `dataInicio` | query | não | string |  | Dia de início do intervalo de tempo do qual se deseja saber a composição da Mesa, no formato `AAAA-MM-DD`. |
| `dataFim` | query | não | string |  | Data de término do intervalo de tempo do qual se deseja saber a composição da Mesa, no formato `AAAA-MM-DD`. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoLegislaturaIDMesa](#resultadolegislaturaidmesa)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoLegislaturaIDMesa](#resultadolegislaturaidmesa)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoLegislaturaIDMesa](#resultadolegislaturaidmesa)

### GET `/referencias/deputados/codSituacao`

**As possíveis situações de exercício parlamentar de um deputado**

Retorna uma lista de siglas e descrições dos possíveis estados em que um deputado pode estar em relação ao seu exercício parlamentar: `Exercício`, `Fim de Mandato`, `Afastado`, etc.

`operationId`: `getSituacoesDeputado_1`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/situacoesDeputado`

**As possíveis situações de exercício parlamentar de um deputado**

Retorna uma lista de siglas e descrições dos possíveis estados em que um deputado pode estar em relação ao seu exercício parlamentar: `Exercício`, `Fim de Mandato`, `Afastado`, etc.

`operationId`: `getSituacoesDeputado`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

## Eventos

### GET `/eventos`

**Lista de eventos ocorridos ou previstos nos diversos órgãos da Câmara**

Retorna uma lista cujos elementos trazem informações básicas sobre eventos dos órgãos legislativos da Câmara, previstos ou já ocorridos, em um certo intervalo de tempo.

Esse intervalo pode ser configurado pelos parâmetros de data e hora listados abaixo. Se nenhum for passado, são listados eventos dos cinco dias anteriores, dos cinco dias seguintes e do próprio dia em que é feita a requisição.

`operationId`: `getEventos`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | query | não | array |  | Identificador(es) numérico(s) de um ou mais eventos, separados por vírgulas. |
| `codTipoEvento` | query | não | array |  | Um ou mais identificador(es) numérico(s) do(s) tipo(s) de evento que se deseja obter. Os valores válidos podem ser obtidos por uma requisição a `/referencias/tiposEvento`. |
| `codSituacao` | query | não | array |  | Um ou mais identificador(es) numéricos de tipo(s) de situação de evento, separados por vírgula. Valores válidos podem ser obtidos em `/referencias/situacoesEvento`. |
| `codTipoOrgao` | query | não | array |  | Um ou mais identificador(es) numérico(s) de tipo(s) de órgão(s) realizadores dos eventos que se deseja obter, separados por vírgula. Os valores válidos podem ser obtidos em `/referencias/tiposOrgao`. |
| `idOrgao` | query | não | array |  | Um ou mais identificador(es) numérico(s) de órgão(s), separados por vírgula. Os identificadores podem ser obtidos em uma requisição a `/orgaos`. |
| `dataInicio` | query | não | string |  | Data de início de um intervalo de tempo, no formato `AAAA-MM-DD`. |
| `dataFim` | query | não | string |  | Data de término de um intervalo de tempo, no formato `AAAA-MM-DD`. |
| `horaInicio` | query | não | string |  | Hora inicial de um intervalo de tempo, no formato `hh:mm`, em horário de Brasília. |
| `horaFim` | query | não | string |  | Hora final de um intervalo de tempo, no formato `hh:mm`, em horário de Brasília. |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. |
| `ordem` | query | não | string |  | O sentido da ordenação: `asc` para A a Z ou 0 a 9, e `desc` para Z a A ou 9 a 0. |
| `ordenarPor` | query | não | string |  | Nome do campo pelo qual a lista deve ser ordenada: `id`, `dataHoraInicio`, `dataHoraFim`, `descricaoSituacao`, `descricaoTipo` ou `titulo` |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoEventos](#resultadoeventos)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoEventos](#resultadoeventos)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoEventos](#resultadoeventos)

### GET `/eventos/{id}`

**Informações detalhadas sobre um evento específico**

Retorna um conjunto detalhado de informações sobre o evento da Câmara identificado por `id`.

`operationId`: `getEventos_1`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | O identificador numérico do evento do qual se deseja informações |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoEventosID](#resultadoeventosid)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoEventosID](#resultadoeventosid)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoEventosID](#resultadoeventosid)

### GET `/eventos/{id}/deputados`

**Os deputados participantes de um evento específico**

Retorna uma lista de dados resumidos sobre deputados participantes do evento identificado por `{id}`.
Se o evento já ocorreu, a lista identifica os deputados que efetivamente registraram presença no evento. Se o evento ainda não ocorreu, a lista mostra os deputados que _devem_ participar do evento, por serem convidados ou por serem membros do(s) órgão(s) responsável pelo evento.

`operationId`: `getEventosDeputados`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | O identificador numérico da entidade. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoEventosDeputado](#resultadoeventosdeputado)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoEventosDeputado](#resultadoeventosdeputado)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoEventosDeputado](#resultadoeventosdeputado)

### GET `/eventos/{id}/orgaos`

**Lista de órgãos organizadores do evento `{id}`**

Retorna uma lista em que cada item é um conjunto mínimo de dados sobre o(s) órgão(s) responsável(veis) pelo evento identificado por `{id}`. Atualmente, mas _provisoriamente_, esta informação já vem incorporada ao retorno de `/eventos/{id}`, mas este _endpoint_ facilita a importação destes dados em planilhas eletrônicas.

`operationId`: `obterOrgaosDoEvento`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | O identificador numérico da entidade. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoEventoOrgao](#resultadoeventoorgao)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoEventoOrgao](#resultadoeventoorgao)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoEventoOrgao](#resultadoeventoorgao)

### GET `/eventos/{id}/pauta`

**Lista de proposições que foram ou deverão ser avaliadas em um evento de caráter deliberativo**

Se o evento `{id}` for de caráter deliberativo (uma reunião ordinária, por exemplo) este serviço retorna a lista de proposições previstas para avaliação pelos parlamentares. Cada item identifica, se as informações estiverem disponíveis, a proposição avaliada, o regime de preferência para avaliação, o relator e seu parecer, o resultado da apreciação e a votação realizada.

`operationId`: `getEventosPauta`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | O identificador numérico da entidade. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoEventosPauta](#resultadoeventospauta)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoEventosPauta](#resultadoeventospauta)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoEventosPauta](#resultadoeventospauta)

### GET `/eventos/{id}/votacoes`

**Informações detalhadas de votações sobre um evento específico**

Retorna uma lista de dados básicos sobre votações que tenham sido realizadas no evento identificado por `{id}`. Votações só ocorrem em eventos de caráter deliberativo. Dados complementares sobre cada votação listada podem ser obtidos no recurso `/votacoes/{id}`.

Para compreender melhor os dados sobre votações, veja [a página de tutorial do Portal de Dados Abertos](https://dadosabertos.camara.leg.br/howtouse/2020-02-07-dados-votacoes.html).

`operationId`: `obterVotacoesPorEvento`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | O identificador numérico do evento do qual se deseja informações |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoes](#resultadovotacoes)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoes](#resultadovotacoes)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoes](#resultadovotacoes)

### GET `/referencias/eventos/codSituacaoEvento`

**As possíveis situações para eventos**

Retorna uma lista de identificadores numéricos, siglas e descrições dos estados em que eventos como uma reunião podem se encontrar, como `Em Andamento`, `Cancelada` e `Encerrada`.

`operationId`: `getSituacoesEvento`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/eventos/codTipoEvento`

**Os tipos de eventos realizados na Câmara**

Retorna uma lista de identificadores numéricos, siglas e descrições dos tipos de eventos ocorridos na Câmara, tais como `Audiência Pública`, `Comissão Geral` e `Palestra`, entre outros.

`operationId`: `getTiposEvento_1`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/situacoesEvento`

**As possíveis situações para eventos**

Retorna uma lista de identificadores numéricos, siglas e descrições dos estados em que eventos como uma reunião podem se encontrar, como `Em Andamento`, `Cancelada` e `Encerrada`.

`operationId`: `getSituacoesEvento_1`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/tiposEvento`

**Os tipos de eventos realizados na Câmara**

Retorna uma lista de identificadores numéricos, siglas e descrições dos tipos de eventos ocorridos na Câmara, tais como `Audiência Pública`, `Comissão Geral` e `Palestra`, entre outros.

`operationId`: `getTiposEvento`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

## Frentes

### GET `/frentes`

**Lista de frentes parlamentares de uma ou mais legislaturas**

Retorna uma lista de informações sobre uma frente parlamentar - um agrupamento oficial de parlamentares em torno de um determinado tema ou proposta.

As frentes existem até o fim da legislatura em que foram criadas, e podem ser recriadas a cada legislatura. Algumas delas são compostas por deputados e senadores.

Um ou mais número de legislatura(s) pode(m) ser passado(s) como parâmetro, mas se for omitido são retornadas todas as frentes parlamentares criadas desde 2003.

`operationId`: `buscar`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `idLegislatura` | query | não | array |  | Número da(s) legislatura(s), separados por vírgulas, às quais os dados buscados devem corresponder. |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoFrentes](#resultadofrentes)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoFrentes](#resultadofrentes)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoFrentes](#resultadofrentes)

### GET `/frentes/{id}`

**Informações detalhadas sobre uma frente parlamentar**

Este recurso traz informações detalhadas sobre a frente parlamentar identificada por `{id}`.

`operationId`: `obterDeputadoID`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Identificador numérico da frente parlamentar. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoFrenteID](#resultadofrenteid)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoFrenteID](#resultadofrenteid)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoFrenteID](#resultadofrenteid)

### GET `/frentes/{id}/membros`

**Os deputados que participam de uma frente parlamentar**

Uma lista dos deputados participantes da frente parlamentar identificada por `{id}` e os papéis que exerceram nessa frente (signatário, coordenador ou presidente).

Observe que, mesmo no caso de frentes parlamentares mistas (compostas por deputados e senadores), são retornados apenas dados sobre os deputados.

`operationId`: `obterMembro`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | O identificador numérico da entidade. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoMembroFrente](#resultadomembrofrente)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoMembroFrente](#resultadomembrofrente)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoMembroFrente](#resultadomembrofrente)

## Grupos

### GET `/grupos`

**Os grupos de cooperação entre parlamentares brasileiros e de outros países**

Este endpoint retorna uma lista em que cada item representa um dos grupos interparlamentares em que a Câmara teve representantes. As informações incluem nome, a resolução que criou o grupo e seu ano de publicação, e as mais recentes informações sobre situação, presidente e ofício de instalação.

`operationId`: `grupos`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. |
| `ordem` | query | não | string |  | O sentido da ordenação: `asc` para A a Z ou 0 a 9, e `desc` para Z a A ou 9 a 0. |
| `ordenarPor` | query | não | string |  | Nome do campo pelo qual a lista será ordenada: `id`, `idLegislatura`. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoGrupos](#resultadogrupos)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoGrupos](#resultadogrupos)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoGrupos](#resultadogrupos)

### GET `/grupos/{id}`

**Informações detalhadas sobre um determinado grupo interparlamentar**

Todo o conjunto de informações disponíveis sobre o grupo parlamentar identificado por `{id}`. Além dos retornados por `/grupos`, há dados sobre o projeto de resolução que levou à criação do grupo, identificadores do mais recente documento e/ou ofício de instalação do grupo, datas de sua apresentação e de sua publicação, e identificação do autor do ofício.

`operationId`: `obterGruposID`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Número identificador do Grupo. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoGruposID](#resultadogruposid)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoGruposID](#resultadogruposid)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoGruposID](#resultadogruposid)

### GET `/grupos/{id}/historico`

**As variações de estado que um grupo parlamentar teve ao longo do tempo**

Uma lista contendo todos os "retratos" das informações sujeitas a mudanças sobre o grupo parlamentar identificado por `{id}` &mdash; por exemplo, todos os ofícios de instalação dos grupos apresentados a cada legislatura desde sua criação, e eventuais substituições de presidentes.

`operationId`: `historico`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Identificador numérico de Grupo histórico. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoGruposHistorico](#resultadogruposhistorico)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoGruposHistorico](#resultadogruposhistorico)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoGruposHistorico](#resultadogruposhistorico)

### GET `/grupos/{id}/membros`

**Lista de parlamentares integrantes de um grupo interparlamentar**

Retorna uma lista de deputados ou senadores que são ou foram participantes do grupo interparlamentar identificado por `{id}`. Podem ser utilizados os parâmetros `dataInicio` e/ou `dataFim` para definir de qual período se deseja saber quem foram os participantes.

Se nenhum parâmetro de tempo for utilizado, são retornados os integrantes registrados no momento da requisição (inclusive deputados e senadores que podem não estar em exercício). A lista será vazia se o grupo `{id}` ainda não tiver sido instalado na legislatura atual.

`operationId`: `membros`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Número(s) identificador(es) de um Membro. |
| `dataInicio` | query | não | string |  | Data de início de um intervalo de tempo, no formato `AAAA-MM-DD`. |
| `dataFim` | query | não | string |  | Data de término de um intervalo de tempo, no formato `AAAA-MM-DD`. |
| `ordem` | query | não | string |  | O sentido da ordenação: `asc` para A a Z ou 0 a 9, e `desc` para Z a A ou 9 a 0. |
| `ordenarPor` | query | não | string |  | Nome do campo pelo qual a lista será ordenada: `idLegislatura`. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoGruposMembros](#resultadogruposmembros)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoGruposMembros](#resultadogruposmembros)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoGruposMembros](#resultadogruposmembros)

## Legislaturas

### GET `/legislaturas`

**Os períodos de mandatos e atividades parlamentares da Câmara**

Legislatura é o nome dado ao período de trabalhos parlamentares entre uma eleição e outra.

Este serviço retorna uma lista em que cada item contém as informações básicas sobre um desses períodos.

Os números que identificam as legislaturas são sequenciais, desde a primeira que ocorreu.

`operationId`: `getLegislatura`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | query | não | array |  | Um ou mais número(s) de legislatura(s), separados por vírgulas. Se omitido, serão retornados dados sobre todas as legislaturas. |
| `data` | query | não | string |  | Uma ou mais data(s) no formato `AAAA-MM-DD`, separadas por vírgulas. Se este parâmetro estiver presente, a requisição retornará as informações básicas sobre as legislaturas que estavam em curso nas datas informadas. |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. |
| `ordem` | query | não | string |  | O sentido da ordenação: `asc` para A a Z ou 0 a 9, e `desc` para Z a A ou 9 a 0. |
| `ordenarPor` | query | não | string |  | Qual dos elementos da representação deverá ser usado para aplicar ordenação à lista. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoLegislaturas](#resultadolegislaturas)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoLegislaturas](#resultadolegislaturas)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoLegislaturas](#resultadolegislaturas)

### GET `/legislaturas/{id}`

**Informações extras sobre uma determinada legislatura da Câmara**

Retorna informações adicionais sobre o período de atividades da Câmara identificado por `{id}`.

`operationId`: `obterPorId_1`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Número da legislatura da qual se quer os dados. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoLegislaturasDetalhe](#resultadolegislaturasdetalhe)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoLegislaturasDetalhe](#resultadolegislaturasdetalhe)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoLegislaturasDetalhe](#resultadolegislaturasdetalhe)

## Partidos

### GET `/partidos`

**Os partidos políticos que têm ou já tiveram parlamentares em exercício na Câmara**

Retorna uma lista de dados básicos sobre os partidos políticos que têm ou já tiveram deputados na Câmara.
Se não forem passados parâmetros, o serviço retorna os partidos que têm deputados em exercício no momento da requisição.

É possível obter uma lista de partidos representados na Câmara em um certo intervalo de datas ou de legislaturas. Se um intervalo e uma ou mais legislatura(s) não coincidentes forem passados, todos os intervalos de tempo serão somados.

Também se pode fazer busca por uma ou mais sigla(s), mas atenção: em diferentes legislaturas, pode haver mais de um partido usando a mesma sigla.

`operationId`: `listarPartidos`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `sigla` | query | não | array |  | Sigla de um ou mais partido(s), separadas por vírgulas. |
| `idLegislatura` | query | não | array |  | Número da(s) legislatura(s), separados por vírgulas, às quais os dados buscados devem corresponder. |
| `dataInicio` | query | não | string |  | Data de início de um intervalo de tempo, no formato `AAAA-MM-DD`. |
| `dataFim` | query | não | string |  | Data de término de um intervalo de tempo, no formato `AAAA-MM-DD`. |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. |
| `ordem` | query | não | string |  | O sentido da ordenação: `asc` para A a Z ou 0 a 9, e `desc` para Z a A ou 9 a 0. |
| `ordenarPor` | query | não | string |  | Nome do campo pelo qual a lista deve ser ordenada: `id`, `sigla`, `nome`, `dataInicio` ou `dataFim` |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoPartidos](#resultadopartidos)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoPartidos](#resultadopartidos)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoPartidos](#resultadopartidos)

### GET `/partidos/{id}`

**Informações detalhadas sobre um partido**

`operationId`: `getPartido`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Id do Partido |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoPartidosID](#resultadopartidosid)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoPartidosID](#resultadopartidosid)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoPartidosID](#resultadopartidosid)

### GET `/partidos/{id}/lideres`

**Deputados que são ou foram líderes ou vice-líderes de um partido**

Retorna uma lista de deputados que ocupam ou ocuparam cargos de líder ou vice-líder do partido {id} num intervalo de tempo opcional, com a identificação do cargo e o período em que o tiveram.

`operationId`: `obterLideres`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | ID do partido do qual se deseja os dados. |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoPartidosIDLideresVice](#resultadopartidosidlideresvice)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoPartidosIDLideresVice](#resultadopartidosidlideresvice)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoPartidosIDLideresVice](#resultadopartidosidlideresvice)

### GET `/partidos/{id}/membros`

**Uma lista dos parlamentares de um partido durante um período**

Retorna uma lista de deputados que estão ou estiveram em exercício pelo partido `{id}`.

Opcionalmente, pode-se usar os parâmetros `dataInicio`, `dataFim` ou `idLegislatura` para se obter uma lista de deputados filiados ao partido num certo intervalo de tempo. Isso é equivalente ao serviço `/deputados` com filtro por partido, mas é melhor para obter informações sobre membros de partidos já extintos.

`operationId`: `getMembros`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Id do Partido |
| `dataInicio` | query | não | string |  | Data de início de um intervalo de tempo, no formato `AAAA-MM-DD`. |
| `dataFim` | query | não | string |  | Data de término de um intervalo de tempo, no formato `AAAA-MM-DD`. |
| `idLegislatura` | query | não | array<integer (int64)> |  | Número da(s) legislatura(s), separados por vírgulas, às quais os dados buscados devem corresponder. |
| `ordenarPor` | query | não | string |  | Nome do campo pelo qual a lista será ordenada: `id`, `nome`, `siglaUf` |
| `ordem` | query | não | string |  | O sentido da ordenação: `asc` para A a Z ou 0 a 9, e `desc` para Z a A ou 9 a 0. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoPartidosIDMembros](#resultadopartidosidmembros)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoPartidosIDMembros](#resultadopartidosidmembros)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoPartidosIDMembros](#resultadopartidosidmembros)

## Proposições

### GET `/proposicoes`

**Lista configurável de proposições na Câmara**

Lista de informações básicas sobre projetos de lei, resoluções, medidas provisórias, emendas, pareceres e todos os outros tipos de proposições na Câmara.

Por padrão, são retornadas todas as proposições que foram apresentadas ou tiveram alguma mudança de situação nos últimos 30 dias. Esse intervalo de tramitação pode ser configurado pelos parâmetros `dataInicio` e `dataFim`.

Se for(em) passado(s) um ou mais dos parâmetros...

  - `id`

  - `ano`

  - `dataApresentacaoInicio`

  - `dataApresentacaoFim`

  - `idAutor`

  - `autor`

...o intervalo de tramitação só será levado em consideração se os parâmetros `dataInicio` e/ou `dataFim` estiverem explicitamente configurados. Se não estiverem, poderão ser listadas proposições que não tiveram tramitação recente (e a resposta pode demorar bastante).

`operationId`: `search`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | query | não | array |  | Número(s) identificador(es) de uma ou mais proposições no **Dados Abertos**, separados por vírgulas. |
| `siglaTipo` | query | não | array |  | Uma ou mais sigla(s) separadas por vírgulas do(s) tipo(s) das proposições que se deseja obter. A lista de tipos e siglas existentes pode ser obtida em `/referencias/proposicoes/siglaTipo` |
| `numero` | query | não | array |  | Um ou mais número(s), separados por vírgula, oficialmente atribuídos às proposições segundo o art. 137 do Regimento Interno, como "PL **1234**/2016" |
| `ano` | query | não | array |  | Um ou mais ano(s) de apresentação das proposições que serão listadas, separados por vírgulas, no formato `AAAA` |
| `codTipo` | query | não | array |  | Um ou mais código(s) numérico(s) de tipo específico de proposição, separados por vírgula. A lista de códigos existentes pode ser obtida em `/referencias/proposicoes/siglaTipo`. |
| `idDeputadoAutor` | query | não | array |  | Um ou mais números identificador(es), separados por vírgula, do(s) deputado(s) autor(es) das proposições que serão listadas. Cada número deve ser o identificador exclusivo de um parlamentar no **Dados Abertos** |
| `autor` | query | não | string |  | Nome ou parte do nome do(s) autor(es) das proposições que se deseja obter. Deve estar entre aspas |
| `siglaPartidoAutor` | query | não | array |  | Uma ou mais sigla(s) separadas por vírgulas do(s) partido(s) a que pertençam os autores das proposições a serem listadas |
| `idPartidoAutor` | query | não | integer (int64) |  | Identificador numérico no **Dados Abertos** do partido a que pertençam os autores das proposições que serão listadas. Esses identificadores podem ser obtidos em `/partidos` e são mais precisos do que as siglas, que podem ser usadas por partidos diferentes em épocas diferentes |
| `siglaUfAutor` | query | não | array |  | Uma ou mais sigla(s) de unidade(s) da federação (estados e Distrito Federal) pela(s) qual(quais) o(s) autor(es) das proposições selecionadas tenha(m) sido eleito(s) |
| `keywords` | query | não | array |  | Uma ou mais palavras chaves sobre o tema a que a proposição se relaciona |
| `tramitacaoSenado` | query | não | boolean |  | Indicador booleano, com valor `TRUE` ou `FALSE` para trazer apenas proposições que já tenha tramitado no Senado |
| `dataInicio` | query | não | string (date-time) |  | Data do início do intervalo de tempo em que tenha havido tramitação das proposições a serem listadas, no formato `AAAA-MM-DD`. Se omitido, é assumido como a data de 30 dias anteriores à proposição |
| `dataFim` | query | não | string (date-time) |  | Data do fim do intervalo de tempo em que tenha havido tramitação das proposições a serem listadas. Se omitido, é considerado ser o dia em que é feita a requisição |
| `dataApresentacaoInicio` | query | não | string (date-time) |  | Data do início do intervalo de tempo em que tenham sido apresentadas as proposições a serem listadas, no formato `AAAA-MM-DD` |
| `dataApresentacaoFim` | query | não | string (date-time) |  | Data do fim do intervalo de tempo em que tenham sido apresentadas as proposições a serem listadas |
| `codSituacao` | query | não | array |  | Código(s) numérico(s), separados por vírgulas, do tipo de situação em que se encontram as proposições que serão listadas. As situações possíveis podem ser obtidas em `/referencias/proposicoes/codSituacao`. **Atenção:** este parâmetro pode apresentar resultados inesperados, por problemas com o registro dos dados. |
| `codTema` | query | não | array |  | Código(s) numérico(s), separados por vírgulas, das áreas temáticas das proposições que serão listadas. Os temas possíveis podem ser obtidos em `/referencias/proposicoes/codTema` |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. |
| `ordem` | query | não | string |  | O sentido da ordenação: `asc` para A a Z ou 0 a 9, e `desc` para Z a A ou 9 a 0. |
| `ordenarPor` | query | não | string |  | Nome do campo pelo qual a lista deve ser ordenada: `id`, `codTipo`, `siglaTipo`, `numero` ou `ano` |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoProposicoes](#resultadoproposicoes)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoProposicoesObject](#resultadoproposicoesobject)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoProposicoesObject](#resultadoproposicoesobject)

### GET `/proposicoes/{id}`

**Informações detalhadas sobre uma proposição específica**

`operationId`: `obterPorId`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Identificador numérico da proposição |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → object
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → object
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → object

### GET `/proposicoes/{id}/autores`

**Lista pessoas e/ou entidades autoras de uma proposição**

Retorna uma lista em que cada item identifica uma pessoa ou entidade que é autora da proposição identificada por `{id}`. Além de deputados, também podem ser autores de proposições os senadores, a sociedade civil, assembleias legislativas e os poderes Executivo e Judiciário.

Pelo Regimento da Câmara, todos os que assinam uma proposição são considerados autores (art. 102), tanto os proponentes quanto os apoiadores.

Para obter mais informações sobre cada autor, é recomendável acessar, se disponível, a URL que é valor do campo `uri`.

`operationId`: `obterAutoresDaProposicao`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Identificador alfanumérico da entidade |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoProposicoesAutores](#resultadoproposicoesautores)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoProposicoesAutores](#resultadoproposicoesautores)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoProposicoesAutores](#resultadoproposicoesautores)

### GET `/proposicoes/{id}/relacionadas`

**Uma lista de proposições relacionadas a uma em especial**

Lista de informações básicas sobre proposições que de alguma forma se relacionam com a proposição identificada por `{id}`, como pareceres, requerimentos, substitutivos, etc.

`operationId`: `obterRelacionadasPorId`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Id da proposição |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoProposicoesRelacionadas](#resultadoproposicoesrelacionadas)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoProposicoesRelacionadas](#resultadoproposicoesrelacionadas)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoProposicoesRelacionadas](#resultadoproposicoesrelacionadas)

### GET `/proposicoes/{id}/temas`

**Lista de áreas temáticas de uma proposição**

Lista em que cada item traz informações sobre uma área temática à qual a proposição identificada por `{id}` se relaciona, segundo classificação oficial do Centro de Documentação e Informação da Câmara.

`operationId`: `obterTemasPorId`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Id da proposição |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoProposicoesTema](#resultadoproposicoestema)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoProposicoesTema](#resultadoproposicoestema)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoProposicoesTema](#resultadoproposicoestema)

### GET `/proposicoes/{id}/tramitacoes`

**O histórico de passos na tramitação de uma proposta**

Lista que traz, como cada item, um "retrato" de informações que podem ser alteradas a cada etapa de tramitação na vida de uma proposição (como regime de tramitação e situação) e informações sobre o que causou esse novo estado.

Esta representação das tramitações ainda é provisória.

`operationId`: `obterTramitacaoPorId`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Identificador numérico da proposição |
| `dataInicio` | query | não | string |  | Data do início da tramitação, no formato `AAAA-MM-DD`. |
| `dataFim` | query | não | string |  | Data do fim da tramitação |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoFrentes](#resultadofrentes)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoProposicoesTramitacao](#resultadoproposicoestramitacao)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoProposicoesTramitacao](#resultadoproposicoestramitacao)

### GET `/proposicoes/{id}/votacoes`

**Informações detalhadas de votações sobre uma proposição específica**

Retorna uma lista de identificadores básicos sobre as votações na Câmara que tiveram a proposição `{id}` como _objeto_ ou como _afetada_ pelos seus resultados. Dados complementares sobre cada votação listada podem ser obtidos no recurso `/votacoes/{id}`.

Para compreender melhor os dados sobre votações, veja [a página de tutorial do Portal de Dados Abertos](https://dadosabertos.camara.leg.br/howtouse/2020-02-07-dados-votacoes.html).

`operationId`: `obterVotacoesPorId`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `ordem` | query | não | string |  | O sentido da ordenação: `asc` para A a Z ou 0 a 9, e `desc` para Z a A ou 9 a 0. |
| `ordenarPor` | query | não | string |  | Nome do campo pelo qual a lista será ordenada: `id`, `dataHoraRegistro` |
| `id` | path | sim | integer (int64) |  | Identificador numérico da proposição |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoes](#resultadovotacoes)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoes](#resultadovotacoes)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoes](#resultadovotacoes)

## Referências

### GET `/referencias/deputados`

**Valores válidos para parâmetros do endpoint `/deputados`**

Retorna, como valor do elemento "dados", um objeto em que cada elemento tem o nome de um parâmetro aplicável ao endpoint /deputados. Cada elemento desses tem como valor uma lista de itens (nós em XML) em que cada item representa um valor válido que pode ser atribuído ao parâmetro.
Em outras palavras: uma requisição a esta URL tem como resposta uma versão agregada das respostas de todas as URLs abaixo dela. Assim, em uma só chamada é possível obter uma lista de todos os parâmetros que exigem valores predeterminados, e quais são os valores válidos para tais parâmetros.
Este recurso não é disponível em formato CSV.

`operationId`: `getDeputados`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ReferenciaDeputado](#referenciadeputado)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferenciaSubResourceReferenciaDeputado](#resultadoreferenciasubresourcereferenciadeputado)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferenciaSubResourceReferenciaDeputado](#resultadoreferenciasubresourcereferenciadeputado)

### GET `/referencias/deputados/codTipoProfissao`

**Códigos e títulos de atividades profissionais usados na Câmara**

Retorna uma lista dos títulos de profissões registradas na Câmara dos Deputados (em masculino) e seus códigos.

`operationId`: `getCodTipoProfissao`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/deputados/siglaUF`

**As siglas e nomes dos estados e do Distrito Federal**

Retorna uma lista de siglas e nomes das unidades de federação brasileiras, usados principalmente para indicar onde um parlamentar foi eleito.

`operationId`: `getUf_1`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/deputados/tipoDespesa`

**Os possíveis tipos de despesas que fazem parte da Cota Parlamentar**

Retorna uma lista de códigos e nomes das possíveis despesas de Cota Parlamentar: `COMBUSTÍVEIS E LUBRIFICANTES.`, `TELEFONIA`, `SERVIÇOS POSTAIS`, etc.

`operationId`: `getDespesas`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/eventos`

**Valores válidos para parâmetros do endpoint `/eventos`**

Retorna, como valor do elemento "dados", um objeto em que cada elemento tem o nome de um parâmetro aplicável ao endpoint /eventos. Cada elemento desses tem como valor uma lista de itens (nós em XML) em que cada item representa um valor válido que pode ser atribuído ao parâmetro.
Em outras palavras: uma requisição a esta URL tem como resposta uma versão agregada das respostas de todas as URLs abaixo dela. Assim, em uma só chamada é possível obter uma lista de todos os parâmetros que exigem valores predeterminados, e quais são os tais valores para cada um desses parâmetros.
Este recurso não é disponível em formato CSV.

`operationId`: `getEentos`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ReferenciaEvento](#referenciaevento)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferenciaSubResourceReferenciaEvento](#resultadoreferenciasubresourcereferenciaevento)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferenciaSubResourceReferenciaEvento](#resultadoreferenciasubresourcereferenciaevento)

### GET `/referencias/orgaos`

**Valores válidos para parâmetros do endpoint sobre órgãos**

Retorna, como valor do elemento "dados", um objeto em que cada elemento tem o nome de um parâmetro aplicável ao endpoint /orgaos. Cada elemento desses tem como valor uma lista de itens (nós em XML) em que cada item representa um valor válido que pode ser atribuído ao parâmetro.
Em outras palavras: uma requisição a esta URL tem como resposta uma versão agregada das respostas de todas as URLs abaixo dela. Assim, em uma só chamada é possível obter uma lista de todos os parâmetros que exigem valores predeterminados, e quais são os tais valores para cada um desses parâmetros.
Este recurso não é disponível em formato CSV.

`operationId`: `getOrgaos`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ReferenciaOrgao](#referenciaorgao)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferenciaSubResourceReferenciaOrgao](#resultadoreferenciasubresourcereferenciaorgao)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferenciaSubResourceReferenciaOrgao](#resultadoreferenciasubresourcereferenciaorgao)

### GET `/referencias/orgaos/codTipoOrgao`

**Os tipos de órgãos que existem na Câmara**

Retorna uma lista de identificadores numéricos, siglas e descrições dos tipos de órgãos legislativos ou representados na Câmara, tais como as comissões permanentes, CPIs, procuradorias, etc.

`operationId`: `getTiposOrgao_1`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/proposicoes`

**Valores válidos para parâmetros do endpoint sobre órgãos**

Retorna, como valor do elemento "dados", um objeto em que cada elemento tem o nome de um parâmetro aplicável ao endpoint /proposicoes. Cada elemento desses tem como valor uma lista de itens (nós em XML) em que cada item representa um valor válido que pode ser atribuído ao parâmetro.
Em outras palavras: uma requisição a esta URL tem como resposta uma versão agregada das respostas de todas as URLs abaixo dela. Assim, em uma só chamada é possível obter uma lista de todos os parâmetros que exigem valores predeterminados, e quais são os tais valores para cada um desses parâmetros.
Este recurso não é disponível em formato CSV.

`operationId`: `getProposicoes`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ReferenciaProposicao](#referenciaproposicao)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferenciaSubResourceReferenciaProposicao](#resultadoreferenciasubresourcereferenciaproposicao)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferenciaSubResourceReferenciaProposicao](#resultadoreferenciasubresourcereferenciaproposicao)

### GET `/referencias/proposicoes/codSituacao`

**Os possíveis estados de tramitação de uma proposição**

Uma lista de identificadores das diversas situações de tramitação em que uma proposição pode se encontrar, como `Encaminhada à Publicação`, `Aguardando Análise`, `Devolvida ao Autor`, etc.

`operationId`: `getSituacoesProposicao`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/proposicoes/codTema`

**Os vários tipos de temas existentes**

Uma lista de identificadores numéricos e nome dos temas que uma proposição pode apresentar.

`operationId`: `getTemasProposicao`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoEventos](#resultadoeventos)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/proposicoes/codTipoAutor`

**Entidades que podem ser autoras de proposições**

Uma lista de códigos numéricos e descritores dos tipos de parlamentares, órgãos da Câmara e instituições que podem ser autores de proposições.

`operationId`: `getTiposAutor_1`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/proposicoes/codTipoTramitacao`

**Os vários tipos de tramitação existentes**

Uma lista de identificadores numéricos, siglas e descrições dos tipos de tramitações em que uma proposição pode se encontrar, como `Apensação`, `Despacho`, `Devolução ao autor`, etc.

`operationId`: `getTiposTramitacao_1`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoEventos](#resultadoeventos)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/proposicoes/siglaTipo`

**Os vários tipos de proposições existentes**

Uma lista de identificadores numéricos, siglas e descrições dos tipos de proposições que existem ou já existiram no Congresso, tais como `PEC`, `Requerimento`, `Emenda de Plenário` e outros.

`operationId`: `getTiposProposicao`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoEventos](#resultadoeventos)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/situacoesProposicao`

**Os possíveis estados de tramitação de uma proposição**

Uma lista de identificadores das diversas situações de tramitação em que uma proposição pode se encontrar, como `Encaminhada à Publicação`, `Aguardando Análise`, `Devolvida ao Autor`, etc.

`operationId`: `getSituacoesProposicao_1`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/tiposAutor`

**Entidades que podem ser autoras de proposições**

Uma lista de códigos numéricos e descritores dos tipos de parlamentares, órgãos da Câmara e instituições que podem ser autores de proposições.

`operationId`: `getTiposAutor`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/tiposOrgao`

**Os tipos de órgãos que existem na Câmara**

Retorna uma lista de identificadores numéricos, siglas e descrições dos tipos de órgãos legislativos ou representados na Câmara, tais como as comissões permanentes, CPIs, procuradorias, etc.

`operationId`: `getTiposOrgao`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/tiposProposicao`

**Os vários tipos de proposições existentes**

Uma lista de identificadores numéricos, siglas e descrições dos tipos de proposições que existem ou já existiram no Congresso, tais como `PEC`, `Requerimento`, `Emenda de Plenário` e outros.

`operationId`: `getTiposProposicao_1`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoEventos](#resultadoeventos)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/tiposTramitacao`

**Os vários tipos de tramitação existentes**

Uma lista de identificadores numéricos, siglas e descrições dos tipos de tramitações em que uma proposição pode se encontrar, como `Apensação`, `Despacho`, `Devolução ao autor`, etc.

`operationId`: `getTiposTramitacao`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoEventos](#resultadoeventos)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/uf`

**As siglas e nomes dos estados e do Distrito Federal**

Retorna uma lista de siglas e nomes das unidades de federação brasileiras, usados principalmente para indicar onde um parlamentar foi eleito.

`operationId`: `getUf`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

## Votações

### GET `/votacoes`

**Lista das votações da Câmara**

Retorna uma lista de informações básicas sobre as votações ocorridas em eventos dos diversos órgãos da Câmara.

Se não forem passados parâmetros que delimitem o intervalo de tempo da pesquisa, são retornados dados sobre todas as votações ocorridas nos últimos 30 dias, em eventos de todos os órgãos.

Os parâmetros de data permitem estender o período, mas por enquanto é **necessário** que as duas datas sejam de um mesmo ano. Quando apenas uma delas está presente, são retornadas somente as votações ocorridas no mesmo ano, antes de `dataFim` ou após `dataInicio`.

Também é possível filtrar a listagem por identificadores de órgãos da Câmara, de proposições e de eventos.

Quando não há identificação da proposição que foi efetivamente votada, é preciso consultar o endpoint `/votacoes/{id}` para obter uma lista de proposições das quais uma pode ter sido o objeto da votação.

Para mais informações sobre o uso dos endpoints de votações, veja [a página de tutorial do Portal de Dados Abertos](https://dadosabertos.camara.leg.br/howtouse/2020-02-07-dados-votacoes.html).

`operationId`: `listar`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | query | não | array |  | Um ou mais identificador(es) alfanuméricos de votação, separados por vírgulas, para que seja(m) listado(s) dados sobre uma ou mais votações específicas. |
| `idProposicao` | query | não | array |  | Um ou mais identificador(es) numéricos de proposições, que podem ser obtidos por meio do recurso `/proposicoes`. Se presente, listará as votações que tiveram a(s) proposição(ções) como objeto de votação ou que afetaram as proposições listadas. |
| `idEvento` | query | não | array |  | Identificador de um ou mais evento(s) realizado(s) na Câmara, separados por vírgula, nos quais tenham sido realizadas as votações a serem listadas. Os identificadores podem ser obtidos por meio do recurso `/eventos`. Somente os eventos deliberativos podem ter votações. Os eventos podem ter ocorrido fora do intervalo de tempo padrão ou definido por `dataInicio` e/ou `dataFim`. |
| `idOrgao` | query | não | array |  | Um ou mais identificador(es) numéricos de órgãos da Câmara, separados por vírgulas. Se presente, serão retornadas somente votações dos órgãos enumerados. Os identificadores existentes podem ser obtidos por meio do recurso `/orgaos`. |
| `dataInicio` | query | não | string |  | Data em formato `AAAA-MM-DD` para início do intervalo de tempo no qual tenham sido realizadas as votações a serem listadas. Se usado sozinho, esse parâmetro faz com que sejam retornadas votações ocorridas dessa data até o fim do mesmo ano. Se usado com `dataFim`, as duas datas devem ser de um mesmo ano. |
| `dataFim` | query | não | string |  | Data em formato `AAAA-MM-DD` que define o fim do intervalo de tempo no qual tenham sido realizadas as votações a serem listadas. Se usado sozinho, esse parâmetro faz com que sejam retornadas todas as votações ocorridas desde 1º de janeiro do mesmo ano até esta data. Se usado com `dataInicio`, é preciso que as duas datas sejam de um mesmo ano. |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. O valor padrão e máximo para este endpoint é 100, e valores maiores serão ignorados. |
| `ordem` | query | não | string |  | O sentido da ordenação: `asc` para A a Z ou 0 a 9, e `desc` para Z a A ou 9 a 0. |
| `ordenarPor` | query | não | string |  | Nome do campo pelo qual a lista será ordenada. Pode ser `id`, `idOrgao`, `siglaOrgao`, `idEvento`, `idProposicao`, `data`, `dataHoraRegistro` ou `idProposicaoObjeto`. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoes](#resultadovotacoes)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoes](#resultadovotacoes)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoes](#resultadovotacoes)

### GET `/votacoes/{id}`

**Informações detalhadas sobre uma votação da Câmara**

Retorna um conjunto detalhado de dados sobre a votação identificada por `{id}`, tais como as proposições que podem ter sido o objeto da votação e os efeitos de tramitação de outras proposições que eventualmente tenham sido cadastrados em consequência desta votação.

Para compreender melhor os dados retornados, veja o [tutorial sobre votações do Portal de Dados Abertos](https://dadosabertos.camara.leg.br/howtouse/2020-02-07-dados-votacoes.html).

`operationId`: `getVotacaoID`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | string |  | Identificador alfanumérico da votação |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoesID](#resultadovotacoesid)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoesID](#resultadovotacoesid)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoesID](#resultadovotacoesid)

### GET `/votacoes/{id}/orientacoes`

**O voto recomendado pelas lideranças aos seus deputados em uma votação.**

Em muitas votações, os líderes de partidos e blocos - as _bancadas_ - fazem recomendações de voto para seus parlamentares. Essas _orientações_ de uma votação também são feitas pelas lideranças de Governo, Minoria e as mais recentes Maioria e Oposição. Uma liderança também pode _liberar a bancada_ para que cada deputado vote como quiser, ou entrar em _obstrução_, para que seus parlamentares não sejam contados para o quórum da votação.

Se a votação identificada por `{id}` teve orientações, este recurso retorna uma lista em que cada item contém os identificadores de um partido, bloco ou liderança, e o posicionamento ou voto que foi recomendado aos seus parlamentares.

Até o momento, só estão disponíveis dados sobre orientações dadas em votações no Plenário.

`operationId`: `getVotacaoIDOrientacoes`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | string |  | Identificador alfanumérico da votação |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoesIDOrientacoes](#resultadovotacoesidorientacoes)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoesIDOrientacoes](#resultadovotacoesidorientacoes)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoesIDOrientacoes](#resultadovotacoesidorientacoes)

### GET `/votacoes/{id}/votos`

**Como cada parlamentar votou em uma votação nominal e aberta**

Se `{id}` é o identificador de uma votação da Câmara _nominal_ que não tenha sido _secreta_, este _endpoint_ retorna uma lista em que cada item contém os identificadores básicos de um deputado e o voto ou posicionamento que ele registrou. 

O resultado é uma lista vazia se `{id}` foi uma votação _simbólica_, em que os votos individuais não são contabilizados. Mas há algumas votações simbólicas que também têm registros de \"votos\": nesses casos, normalmente se trata de parlamentares que pediram expressamente que seus posicionamentos fossem registrados.

Não são listados parlamentares ausentes à votação.

`operationId`: `getVotacaoVotosPorId`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | string |  | Identificador alfanumérico da votação |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoesIDVotos](#resultadovotacoesidvotos)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoesIDVotos](#resultadovotacoesidvotos)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoesIDVotos](#resultadovotacoesidvotos)

## Órgãos

### GET `/orgaos`

**A lista das comissões e outros órgãos legislativos da Câmara**

Retorna uma lista de informações básicas sobre os órgãos legislativos e seus identificadores, tipos e descrições.

Pela query string é possível filtrar a lista por identificadores, tipos de órgãos, sigla, situação do órgão ou período de tempo em que os órgãos estiveram ativos, se aplicável.

`operationId`: `listar_1`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | query | não | array |  | Um ou mais identificador(es) numérico(s), separados por vírgulas. |
| `sigla` | query | não | array |  | Uma ou mais sigla(s) oficialmente usadas para designar um ou mais órgão(s) da Câmara, separadas por vírgulas. |
| `codTipoOrgao` | query | não | array |  | Um ou mais identificador(es) numérico(s) do(s) tipo(s) de órgãos que se deseja buscar dados. Pode(m) ser obtido(s) em `/referencias/orgaos/codTipoOrgao`. |
| `dataInicio` | query | não | string |  | Data de início, no formato `AAAA-MM-DD`, de um intervalo de tempo no qual os órgãos buscados devem ter estado em atividade. |
| `dataFim` | query | não | string |  | Data de término, no formato `AAAA-MM-DD`, de um intervalo de tempo no qual os órgãos buscados devem ter estado em atividade. |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. |
| `ordem` | query | não | string |  | O sentido da ordenação: `asc` para A a Z ou 0 a 9, e `desc` para Z a A ou 9 a 0. |
| `ordenarPor` | query | não | string |  | Nome do campo pelo qual a lista será ordenada: `id`, `sigla`, `nome`, `apelido`, `codTipoOrgao`, `tipoOrgao`, `dataInicio` ou `dataFim` |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoOrgaos](#resultadoorgaos)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoOrgaos](#resultadoorgaos)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoOrgaos](#resultadoorgaos)

### GET `/orgaos/{id}`

**Informações detalhadas sobre um órgão da Câmara**

Retorna todas as informações disponíveis sobre o órgão da Câmara identificado por `id`.

`operationId`: `getOrgaoDetalhe`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Identificador numérico do órgão |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoOrgaoDetalhe](#resultadoorgaodetalhe)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoOrgaoDetalhe](#resultadoorgaodetalhe)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoOrgaoDetalhe](#resultadoorgaodetalhe)

### GET `/orgaos/{id}/eventos`

**Os eventos ocorridos ou previstos em um órgão legislativo**

Retorna uma lista de informações resumidas dos eventos realizados (ou a realizar) pelo órgão legislativo identificado por `{id}`.
Por padrão, são retornados eventos em andamento ou previstos para o mesmo dia, dois dias antes e dois dias depois da requisição. Parâmetros podem ser passados para alterar esse período, bem como os tipos de eventos.

`operationId`: `getOrgaoEventosDetalhe`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Identificador numérico do órgão |
| `idTipoEvento` | query | não | array |  | Um ou mais identificador(es) numérico(s) de tipos de evento que se deseja obter. os valores válidos podem ser obtidos por uma requisição anterior a `/referencias/tiposEvento`. |
| `dataInicio` | query | não | string |  | Data de início de um intervalo de tempo, no formato `AAAA-MM-DD`. |
| `dataFim` | query | não | string |  | Data de término de um intervalo de tempo, no formato `AAAA-MM-DD`. |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. |
| `ordem` | query | não | string |  | O sentido da ordenação: `asc` para A a Z ou 0 a 9, e `desc` para Z a A ou 9 a 0. |
| `ordenarPor` | query | não | string |  | Qual dos elementos da representação deverá ser usado para aplicar ordenação à lista. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoOrgaoEventos](#resultadoorgaoeventos)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoOrgaoEventos](#resultadoorgaoeventos)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoOrgaoEventos](#resultadoorgaoeventos)

### GET `/orgaos/{id}/membros`

**Lista de cargos de um órgão e parlamentares que os ocupam.**

Retorna uma lista de dados resumidos que identificam cada parlamentar e o cargo ou posição que ocupa ou ocupou no órgão parlamentar identificado por `{id}` durante um certo período de tempo.
Se não forem passados parâmetros que delimitem esse período, o serviço retorna os membros do órgão no momento da requisição. Se o órgão não existir mais ou não estiver instalado, é retornada uma lista vazia.

`operationId`: `getOrgaoMembros`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Identificador numérico do órgão |
| `dataInicio` | query | não | string |  | Data de início de um intervalo de tempo, no formato AAAA-MM-DD. |
| `dataFim` | query | não | string |  | Data de término de um intervalo de tempo, no formato AAAA-MM-DD. |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoOrgaoMembros](#resultadoorgaomembros)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoOrgaoMembros](#resultadoorgaomembros)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoOrgaoMembros](#resultadoorgaomembros)

### GET `/orgaos/{id}/votacoes`

**Informações detalhadas sobre votações de um órgão da Câmara**

Retorna uma lista de dados básicos de votações que tenham sido realizadas em eventos realizados no órgão `{id}`.

Se `{id}` for um órgão permanente da Câmara, são retornados, por padrão, dados sobre as votações realizadas pelo órgão nos últimos 30 dias. Esse período pode ser alterado com o uso dos parâmetros `dataInicio` e/ou `dataFim`, que por enquanto são limitados a selecionar somente votações ocorridas em um mesmo ano.

Caso `{id}` seja um órgão temporário, como uma comissão especial, são listadas por padrão todas as votações ocorridas no órgão, em qualquer período de tempo.

Dados complementares sobre cada votação listada podem ser obtidos no recurso `/votacoes/{id}`.

Para compreender melhor os dados sobre votações, veja [a página de tutorial do Portal de Dados Abertos](https://dadosabertos.camara.leg.br/howtouse/2020-02-07-dados-votacoes.html).

`operationId`: `getVotacoesPorOrgao`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) |  | Identificador numérico do órgão |
| `idProposicao` | query | não | array |  | Um ou mais identificador(es) numéricos de proposições, que podem ser obtidos por meio do recurso `/proposicoes`. Se presente, listará as votações que tiveram a(s) proposição(ções) como objeto de votação ou que afetaram as proposições listadas. |
| `dataInicio` | query | não | string |  | Data em formato `AAAA-MM-DD` para início do intervalo de tempo no qual tenham sido realizadas as votações a serem listadas. Se usado sozinho, esse parâmetro faz com que sejam retornadas votações ocorridas dessa data até o fim do mesmo ano. Se usado com `dataFim`, as duas datas devem ser de um mesmo ano. |
| `dataFim` | query | não | string |  | Data em formato `AAAA-MM-DD` que define o fim do intervalo de tempo no qual tenham sido realizadas as votações a serem listadas. Se usado sozinho, esse parâmetro faz com que sejam retornadas todas as votações ocorridas desde 1º de janeiro do mesmo ano até esta data. Se usado com `dataInicio`, é preciso que as duas datas sejam de um mesmo ano. |
| `pagina` | query | não | integer (int32) |  | Número da página de resultados, a partir de 1, que se deseja obter com a requisição, contendo o número de itens definido pelo parâmetro itens. Se omitido, assume o valor 1. |
| `itens` | query | não | integer (int32) |  | Número máximo de itens na página que se deseja obter com esta requisição. O valor padrão e máximo para este endpoint é 100, e valores maiores serão ignorados. |
| `ordem` | query | não | string |  | O sentido da ordenação: `asc` para A a Z ou 0 a 9, e `desc` para Z a A ou 9 a 0. |
| `ordenarPor` | query | não | string |  | Nome do campo pelo qual a lista será ordenada. Pode ser `id`, `idOrgao`, `siglaOrgao`, `idEvento`, `idProposicao`, `data`, `dataHoraRegistro` ou `idProposicaoObjeto`. |
| `Accept` | header | não | string enum(application/json, application/xml) |  |  |

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoes](#resultadovotacoes)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoes](#resultadovotacoes)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoVotacoes](#resultadovotacoes)

### GET `/referencias/orgaos/codSituacao`

**As situações em que órgãos podem se encontrar**

Retorna uma lista de identificadores numéricos, títulos e descrições das situações possíveis para órgãos em operação na Câmara, como `Em funcionamento`, `Extinta`, `Pronta para criação`, etc.

`operationId`: `getSituacoesOrgao`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

### GET `/referencias/situacoesOrgao`

**As situações em que órgãos podem se encontrar**

Retorna uma lista de identificadores numéricos, títulos e descrições das situações possíveis para órgãos em operação na Câmara, como `Em funcionamento`, `Extinta`, `Pronta para criação`, etc.

`operationId`: `getSituacoesOrgao_1`

- **200** Lista retornada com sucesso — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **400** Requisição inválida — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)
- **404** Não encontrado — `application/json`, `application/xml`, `text/xml` → [ResultadoReferencias](#resultadoreferencias)

## Schemas

### BancadaLideres

| Campo | Tipo | Descrição |
|---|---|---|
| `nome` | string |  |
| `tipo` | string |  |
| `uri` | string |  |

### Bloco

| Campo | Tipo | Descrição |
|---|---|---|
| `federacao` | boolean |  |
| `id` | string |  |
| `idLegislatura` | string |  |
| `nome` | string |  |
| `uri` | string |  |

### BlocoID

| Campo | Tipo | Descrição |
|---|---|---|
| `federacao` | boolean |  |
| `id` | string |  |
| `idLegislatura` | string |  |
| `nome` | string |  |
| `uri` | string |  |

### Deputado

| Campo | Tipo | Descrição |
|---|---|---|
| `email` | string |  |
| `id` | integer (int64) |  |
| `idLegislatura` | integer (int64) |  |
| `nome` | string |  |
| `siglaPartido` | string |  |
| `siglaUf` | string |  |
| `uri` | string |  |
| `uriPartido` | string |  |
| `urlFoto` | string |  |

### DeputadoDespesas

| Campo | Tipo | Descrição |
|---|---|---|
| `ano` | integer (int64) |  |
| `cnpjCpfFornecedor` | string |  |
| `codDocumento` | string |  |
| `codLote` | integer (int64) |  |
| `codTipoDocumento` | integer (int64) |  |
| `dataDocumento` | string |  |
| `mes` | integer (int64) |  |
| `nomeFornecedor` | string |  |
| `numDocumento` | string |  |
| `numRessarcimento` | string |  |
| `parcela` | integer (int64) |  |
| `tipoDespesa` | string |  |
| `tipoDocumento` | string |  |
| `urlDocumento` | string |  |
| `valorDocumento` | number (double) |  |
| `valorGlosa` | number (double) |  |
| `valorLiquido` | number (double) |  |

### DeputadoDiscurso

| Campo | Tipo | Descrição |
|---|---|---|
| `dataHoraFim` | string |  |
| `dataHoraInicio` | string |  |
| `faseEvento` | FaseEvento |  |
| `keywords` | string |  |
| `sumario` | string |  |
| `tipoDiscurso` | string |  |
| `transcricao` | string |  |
| `uriEvento` | string |  |
| `urlAudio` | string |  |
| `urlTexto` | string |  |
| `urlVideo` | string |  |

### DeputadoHistorico

| Campo | Tipo | Descrição |
|---|---|---|
| `condicaoEleitoral` | string |  |
| `dataHora` | string |  |
| `descricaoStatus` | string |  |
| `email` | string |  |
| `id` | integer (int64) |  |
| `idLegislatura` | integer (int64) |  |
| `nome` | string |  |
| `nomeEleitoral` | string |  |
| `siglaPartido` | string |  |
| `siglaUf` | string |  |
| `situacao` | string |  |
| `uri` | string |  |
| `uriPartido` | string |  |
| `urlFoto` | string |  |

### DeputadoID

| Campo | Tipo | Descrição |
|---|---|---|
| `cpf` | string |  |
| `dataFalecimento` | string |  |
| `dataNascimento` | string |  |
| `escolaridade` | string |  |
| `id` | integer (int32) |  |
| `municipioNascimento` | string |  |
| `nomeCivil` | string |  |
| `redeSocial` | array<string> |  |
| `sexo` | string |  |
| `ufNascimento` | string |  |
| `ultimoStatus` | DeputadoUltimoStatus |  |
| `uri` | string |  |
| `urlWebsite` | string |  |

### DeputadoMandatoExterno

| Campo | Tipo | Descrição |
|---|---|---|
| `anoFim` | string |  |
| `anoInicio` | string |  |
| `cargo` | string |  |
| `municipio` | string |  |
| `siglaPartidoEleicao` | string |  |
| `siglaUf` | string |  |
| `uriPartidoEleicao` | string |  |

### DeputadoOcupacoes

| Campo | Tipo | Descrição |
|---|---|---|
| `anoFim` | integer (int32) |  |
| `anoInicio` | integer (int32) |  |
| `entidade` | string |  |
| `entidadePais` | string |  |
| `entidadeUF` | string |  |
| `titulo` | string |  |

### DeputadoOrgao

| Campo | Tipo | Descrição |
|---|---|---|
| `codTitulo` | string |  |
| `dataFim` | string |  |
| `dataInicio` | string |  |
| `idOrgao` | integer (int64) |  |
| `nomeOrgao` | string |  |
| `nomePublicacao` | string |  |
| `siglaOrgao` | string |  |
| `titulo` | string |  |
| `uriOrgao` | string |  |

### DeputadoProfissoes

| Campo | Tipo | Descrição |
|---|---|---|
| `codTipoProfissao` | integer (int64) |  |
| `dataHora` | string |  |
| `titulo` | string |  |

### DeputadoUltimoStatus

| Campo | Tipo | Descrição |
|---|---|---|
| `condicaoEleitoral` | string |  |
| `data` | string |  |
| `descricaoStatus` | string |  |
| `email` | string |  |
| `gabinete` | Gabinete |  |
| `id` | integer (int64) |  |
| `idLegislatura` | integer (int64) |  |
| `nome` | string |  |
| `nomeEleitoral` | string |  |
| `siglaPartido` | string |  |
| `siglaUf` | string |  |
| `situacao` | string |  |
| `uri` | string |  |
| `uriPartido` | string |  |
| `urlFoto` | string |  |

### EfeitosRegistrados

| Campo | Tipo | Descrição |
|---|---|---|
| `dataHoraResultado` | string |  |
| `dataHoraUltimaAberturaVotacao` | string |  |
| `dataHoraUltimaApresentacaoProposicao` | string |  |
| `descResultado` | string |  |
| `descUltimaAberturaVotacao` | string |  |
| `descUltimaApresentacaoProposicao` | string |  |
| `tituloProposicao` | string |  |
| `tituloProposicaoCitada` | string |  |
| `uriProposicao` | string |  |
| `uriProposicaoCitada` | string |  |

### Eventos

| Campo | Tipo | Descrição |
|---|---|---|
| `dataHoraFim` | string |  |
| `dataHoraInicio` | string |  |
| `descricao` | string |  |
| `descricaoTipo` | string |  |
| `id` | integer (int32) |  |
| `localCamara` | LocalCamara |  |
| `localExterno` | string |  |
| `orgaos` | array<Orgao> |  |
| `situacao` | string |  |
| `uri` | string |  |
| `urlRegistro` | string |  |

### EventosID

| Campo | Tipo | Descrição |
|---|---|---|
| `dataHoraFim` | string |  |
| `dataHoraInicio` | string |  |
| `descricao` | string |  |
| `descricaoTipo` | string |  |
| `fases` | string |  |
| `id` | integer (int32) |  |
| `localCamara` | LocalCamara |  |
| `localExterno` | string |  |
| `orgaos` | array<Orgao> |  |
| `requerimentos` | array<Requerimento> |  |
| `situacao` | string |  |
| `uri` | string |  |
| `uriConvidados` | string |  |
| `uriDeputados` | string |  |
| `urlDocumentoPauta` | string |  |
| `urlRegistro` | string |  |

### FaseEvento

| Campo | Tipo | Descrição |
|---|---|---|
| `dataHoraFim` | string |  |
| `dataHoraInicio` | string |  |
| `titulo` | string |  |

### Frente

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | integer (int64) |  |
| `idLegislatura` | integer (int64) |  |
| `titulo` | string |  |
| `uri` | string |  |

### FrenteID

| Campo | Tipo | Descrição |
|---|---|---|
| `coordenador` | Deputado |  |
| `email` | string |  |
| `id` | integer (int64) |  |
| `idLegislatura` | integer (int64) |  |
| `idSituacao` | integer (int64) |  |
| `keywords` | string |  |
| `situacao` | string |  |
| `telefone` | string |  |
| `titulo` | string |  |
| `uri` | string |  |
| `urlDocumento` | string |  |
| `urlWebsite` | string |  |

### Gabinete

| Campo | Tipo | Descrição |
|---|---|---|
| `andar` | string |  |
| `email` | string |  |
| `nome` | string |  |
| `predio` | string |  |
| `sala` | string |  |
| `telefone` | string |  |

### Grupos

| Campo | Tipo | Descrição |
|---|---|---|
| `anoCriacao` | string |  |
| `ativo` | string |  |
| `grupoMisto` | string |  |
| `id` | integer (int64) |  |
| `nome` | string |  |
| `observacoes` | string |  |
| `resolucaoTitulo` | string |  |
| `resolucaoUri` | string |  |
| `subvencionado` | string |  |
| `ultimoStatus` | UltimoStatus |  |
| `uri` | string |  |

### GruposId

| Campo | Tipo | Descrição |
|---|---|---|
| `anoCriacao` | string |  |
| `ativo` | string |  |
| `grupoMisto` | string |  |
| `id` | integer (int64) |  |
| `nome` | string |  |
| `observacoes` | string |  |
| `projetoTitulo` | string |  |
| `projetoUri` | string |  |
| `resolucaoTitulo` | string |  |
| `resolucaoUri` | string |  |
| `subvencionado` | string |  |
| `ultimoStatus` | UltimoStatus |  |
| `ultimoStatusID` | UltimoStatusID |  |
| `uri` | string |  |

### GruposMembros

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | integer (int64) |  |
| `membros` | array<Membro> |  |
| `nome` | string |  |

### Historico

| Campo | Tipo | Descrição |
|---|---|---|
| `dataStatus` | string |  |
| `documentoSGM` | string |  |
| `idLegislatura` | string |  |
| `observacao` | string |  |
| `oficioAutor` | string |  |
| `oficioAutorTipo` | string |  |
| `oficioAutorUri` | string |  |
| `oficioDataApresentacao` | string |  |
| `oficioDataPublicacao` | string |  |
| `oficioTitulo` | string |  |
| `presidente` | string |  |
| `presidenteUri` | string |  |

### Legislatura

| Campo | Tipo | Descrição |
|---|---|---|
| `dataFim` | string |  |
| `dataInicio` | string |  |
| `id` | integer (int64) |  |
| `uri` | string |  |

### LegislaturaIDLideres

| Campo | Tipo | Descrição |
|---|---|---|
| `bancada` | BancadaLideres |  |
| `dataFim` | string |  |
| `dataInicio` | string |  |
| `parlamentar` | ParlamentarLideres |  |
| `titulo` | string |  |

### LegislaturaIDMesa

| Campo | Tipo | Descrição |
|---|---|---|
| `codTitulo` | string |  |
| `dataFim` | string |  |
| `dataInicio` | string |  |
| `email` | string |  |
| `id` | integer (int64) |  |
| `idLegislatura` | integer (int64) |  |
| `nome` | string |  |
| `siglaPartido` | string |  |
| `siglaUf` | string |  |
| `titulo` | string |  |
| `uri` | string |  |
| `uriPartido` | string |  |
| `urlFoto` | string |  |

### Link

| Campo | Tipo | Descrição |
|---|---|---|
| `href` | string |  |
| `rel` | string |  |
| `type` | string |  |

### LocalCamara

| Campo | Tipo | Descrição |
|---|---|---|
| `andar` | string |  |
| `nome` | string |  |
| `predio` | string |  |
| `sala` | string |  |

### Membro

| Campo | Tipo | Descrição |
|---|---|---|
| `cargo` | string |  |
| `dataFim` | string |  |
| `dataInicio` | string |  |
| `idLegislatura` | string |  |
| `nome` | string |  |
| `ordemEntrada` | integer (int64) |  |
| `tipo` | string |  |
| `uri` | string |  |

### MembroFrente

| Campo | Tipo | Descrição |
|---|---|---|
| `codTitulo` | integer (int64) |  |
| `dataFim` | string |  |
| `dataInicio` | string |  |
| `email` | string |  |
| `id` | integer (int64) |  |
| `idLegislatura` | integer (int64) |  |
| `nome` | string |  |
| `siglaPartido` | string |  |
| `siglaUf` | string |  |
| `titulo` | string |  |
| `uri` | string |  |
| `uriPartido` | string |  |
| `urlFoto` | string |  |

### Orgao

| Campo | Tipo | Descrição |
|---|---|---|
| `apelido` | string |  |
| `codTipoOrgao` | integer (int64) |  |
| `id` | integer (int64) |  |
| `nome` | string |  |
| `nomePublicacao` | string |  |
| `nomeResumido` | string |  |
| `sigla` | string |  |
| `tipoOrgao` | string |  |
| `uri` | string |  |

### OrgaoDetalhe

| Campo | Tipo | Descrição |
|---|---|---|
| `apelido` | string |  |
| `casa` | string |  |
| `codTipoOrgao` | integer (int64) |  |
| `dataFim` | string |  |
| `dataFimOriginal` | string |  |
| `dataInicio` | string |  |
| `dataInstalacao` | string |  |
| `id` | integer (int64) |  |
| `nome` | string |  |
| `nomePublicacao` | string |  |
| `nomeResumido` | string |  |
| `sala` | string |  |
| `sigla` | string |  |
| `tipoOrgao` | string |  |
| `uri` | string |  |
| `urlWebsite` | string |  |

### OrgaoMembros

| Campo | Tipo | Descrição |
|---|---|---|
| `codTitulo` | integer (int64) |  |
| `dataFim` | string |  |
| `dataInicio` | string |  |
| `email` | string |  |
| `id` | integer (int64) |  |
| `idLegislatura` | integer (int64) |  |
| `nome` | string |  |
| `siglaPartido` | string |  |
| `siglaUf` | string |  |
| `titulo` | string |  |
| `uri` | string |  |
| `uriPartido` | string |  |
| `urlFoto` | string |  |

### Orientacao

| Campo | Tipo | Descrição |
|---|---|---|
| `codPartidoBloco` | integer (int64) |  |
| `codTipoLideranca` | string |  |
| `orientacaoVoto` | string |  |
| `siglaPartidoBloco` | string |  |
| `uriPartidoBloco` | string |  |

### ParlamentarLideres

| Campo | Tipo | Descrição |
|---|---|---|
| `email` | string |  |
| `id` | integer (int64) |  |
| `idLegislatura` | integer (int64) |  |
| `nome` | string |  |
| `siglaPartido` | string |  |
| `siglaUf` | string |  |
| `uri` | string |  |
| `uriPartido` | string |  |
| `urlFoto` | string |  |

### Partido

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | integer (int32) |  |
| `nome` | string |  |
| `sigla` | string |  |
| `uri` | string |  |

### PartidoID

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | integer (int32) |  |
| `nome` | string |  |
| `numeroEleitoral` | integer (int32) |  |
| `sigla` | string |  |
| `status` | PartidoIDStatus |  |
| `uri` | string |  |
| `urlFacebook` | string |  |
| `urlLogo` | string |  |
| `urlWebSite` | string |  |

### PartidoIDStatus

| Campo | Tipo | Descrição |
|---|---|---|
| `data` | string |  |
| `idLegislatura` | string |  |
| `lider` | PartidoLider |  |
| `situacao` | string |  |
| `totalMembros` | string |  |
| `totalPosse` | string |  |
| `uriMembros` | string |  |

### PartidoLider

| Campo | Tipo | Descrição |
|---|---|---|
| `idLegislatura` | integer (int32) |  |
| `nome` | string |  |
| `siglaPartido` | string |  |
| `uf` | string |  |
| `uri` | string |  |
| `uriPartido` | string |  |
| `urlFoto` | string |  |

### PartidosIDLideres

| Campo | Tipo | Descrição |
|---|---|---|
| `codTitulo` | integer (int64) |  |
| `dataFim` | string |  |
| `dataInicio` | string |  |
| `email` | string |  |
| `id` | integer (int64) |  |
| `idLegislatura` | integer (int64) |  |
| `nome` | string |  |
| `siglaPartido` | string |  |
| `siglaUf` | string |  |
| `titulo` | string |  |
| `uri` | string |  |
| `uriPartido` | string |  |
| `urlFoto` | string |  |

### Pauta

| Campo | Tipo | Descrição |
|---|---|---|
| `codRegime` | integer (int64) |  |
| `ordem` | integer (int64) |  |
| `proposicaoRelacionada_` | ProposicoesRelacionadas |  |
| `proposicao_` | ProposicaoRetornoPrincipal |  |
| `regime` | string |  |
| `relator` | Deputado |  |
| `situacaoItem` | string |  |
| `textoParecer` | string |  |
| `titulo` | string |  |
| `topico` | string |  |
| `uriVotacao` | string |  |

### ProposicaoAutor

| Campo | Tipo | Descrição |
|---|---|---|
| `codTipo` | integer (int64) |  |
| `nome` | string |  |
| `ordemAssinatura` | integer (int32) |  |
| `proponente` | integer (int32) |  |
| `tipo` | string |  |
| `uri` | string |  |

### ProposicaoRetornoPrincipal

| Campo | Tipo | Descrição |
|---|---|---|
| `ano` | integer (int64) |  |
| `codTipo` | integer (int64) |  |
| `dataApresentacao` | string |  |
| `ementa` | string |  |
| `id` | integer (int64) |  |
| `numero` | integer (int64) |  |
| `siglaTipo` | string |  |
| `uri` | string |  |

### ProposicaoTema

| Campo | Tipo | Descrição |
|---|---|---|
| `codTema` | integer (int64) |  |
| `relevancia` | integer (int64) |  |
| `tema` | string |  |

### ProposicaoTramitacao

| Campo | Tipo | Descrição |
|---|---|---|
| `ambito` | string |  |
| `apreciacao` | string |  |
| `codSituacao` | integer (int64) |  |
| `codTipoTramitacao` | string |  |
| `dataHora` | string |  |
| `descricaoSituacao` | string |  |
| `descricaoTramitacao` | string |  |
| `despacho` | string |  |
| `regime` | string |  |
| `sequencia` | integer (int64) |  |
| `siglaOrgao` | string |  |
| `uriOrgao` | string |  |
| `uriUltimoRelator` | string |  |
| `url` | string |  |

### ProposicoesRelacionadas

| Campo | Tipo | Descrição |
|---|---|---|
| `ano` | string |  |
| `codTipo` | string |  |
| `dataApresentacao` | string |  |
| `ementa` | string |  |
| `id` | integer (int64) |  |
| `numero` | string |  |
| `siglaTipo` | string |  |
| `uri` | string |  |

### Referencia

| Campo | Tipo | Descrição |
|---|---|---|
| `cod` | string |  |
| `descricao` | string |  |
| `nome` | string |  |
| `sigla` | string |  |

### ReferenciaDeputado

| Campo | Tipo | Descrição |
|---|---|---|
| `codTipoProfissao` | array<Referencia> |  |
| `siglaSituacao` | array<Referencia> |  |
| `siglaUF` | array<Referencia> |  |

### ReferenciaEvento

| Campo | Tipo | Descrição |
|---|---|---|
| `codSituacao` | array<Referencia> |  |
| `codTipoEvento` | array<Referencia> |  |

### ReferenciaOrgao

| Campo | Tipo | Descrição |
|---|---|---|
| `idSituacao` | array<Referencia> |  |
| `idTipoOrgao` | array<Referencia> |  |

### ReferenciaProposicao

| Campo | Tipo | Descrição |
|---|---|---|
| `codSituacao` | array<Referencia> |  |
| `codTema` | array<Referencia> |  |
| `codTipoAutor` | array<Referencia> |  |
| `siglaTipo` | array<Referencia> |  |
| `tiposTramitacao` | array<Referencia> |  |

### Requerimento

| Campo | Tipo | Descrição |
|---|---|---|
| `titulo` | string |  |
| `uri` | string |  |

### ResultadoBloco

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Bloco> |  |
| `links` | array<Link> |  |

### ResultadoBlocoID

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | BlocoID |  |
| `links` | array<Link> |  |

### ResultadoDeputado

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Deputado> |  |
| `links` | array<Link> |  |

### ResultadoDeputadoDespesas

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<DeputadoDespesas> |  |
| `links` | array<Link> |  |

### ResultadoDeputadoDiscurso

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<DeputadoDiscurso> |  |
| `links` | array<Link> |  |

### ResultadoDeputadoEventos

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Eventos> |  |
| `links` | array<Link> |  |

### ResultadoDeputadoHistorico

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<DeputadoHistorico> |  |
| `links` | array<Link> |  |

### ResultadoDeputadoID

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | DeputadoID |  |
| `links` | array<Link> |  |

### ResultadoDeputadoMandatoExterno

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<DeputadoMandatoExterno> |  |
| `links` | array<Link> |  |

### ResultadoDeputadoOrgaos

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<DeputadoOrgao> |  |
| `links` | array<Link> |  |

### ResultadoDeputadoProfissoes

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<DeputadoProfissoes> |  |
| `links` | array<Link> |  |

### ResultadoEventoOrgao

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Orgao> |  |
| `links` | array<Link> |  |

### ResultadoEventos

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Eventos> |  |
| `links` | array<Link> |  |

### ResultadoEventosDeputado

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Deputado> |  |
| `links` | array<Link> |  |

### ResultadoEventosID

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | EventosID |  |
| `links` | array<Link> |  |

### ResultadoEventosPauta

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Pauta> |  |
| `links` | array<Link> |  |

### ResultadoFrenteID

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | FrenteID |  |
| `links` | array<Link> |  |

### ResultadoFrentes

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Frente> |  |
| `links` | array<Link> |  |

### ResultadoGrupos

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Grupos> |  |
| `links` | array<Link> |  |

### ResultadoGruposHistorico

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Historico> |  |
| `links` | array<Link> |  |

### ResultadoGruposID

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | GruposId |  |
| `links` | array<Link> |  |

### ResultadoGruposMembros

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<GruposMembros> |  |
| `links` | array<Link> |  |

### ResultadoIdDeputadoMembro

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Frente> |  |
| `links` | array<Link> |  |

### ResultadoLegislaturaIDLideres

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<LegislaturaIDLideres> |  |
| `links` | array<Link> |  |

### ResultadoLegislaturaIDMesa

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<LegislaturaIDMesa> |  |
| `links` | array<Link> |  |

### ResultadoLegislaturas

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Legislatura> |  |
| `links` | array<Link> |  |

### ResultadoLegislaturasDetalhe

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | Legislatura |  |
| `links` | array<Link> |  |

### ResultadoMembroFrente

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<MembroFrente> |  |
| `links` | array<Link> |  |

### ResultadoOcupacoesDeputado

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<DeputadoOcupacoes> |  |
| `links` | array<Link> |  |

### ResultadoOrgaoDetalhe

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | OrgaoDetalhe |  |
| `links` | array<Link> |  |

### ResultadoOrgaoEventos

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Eventos> |  |
| `links` | array<Link> |  |

### ResultadoOrgaoMembros

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<OrgaoMembros> |  |
| `links` | array<Link> |  |

### ResultadoOrgaos

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Orgao> |  |
| `links` | array<Link> |  |

### ResultadoPartidos

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Partido> |  |
| `links` | array<Link> |  |

### ResultadoPartidosID

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | PartidoID |  |
| `links` | array<Link> |  |

### ResultadoPartidosIDLideresVice

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<PartidosIDLideres> |  |
| `links` | array<Link> |  |

### ResultadoPartidosIDMembros

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Deputado> |  |
| `links` | array<Link> |  |

### ResultadoProposicoes

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<object> |  |
| `links` | array<Link> |  |

### ResultadoProposicoesAutores

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<ProposicaoAutor> |  |
| `links` | array<Link> |  |

### ResultadoProposicoesObject

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<object> |  |
| `links` | array<Link> |  |

### ResultadoProposicoesRelacionadas

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<ProposicoesRelacionadas> |  |
| `links` | array<Link> |  |

### ResultadoProposicoesTema

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<ProposicaoTema> |  |
| `links` | array<Link> |  |

### ResultadoProposicoesTramitacao

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<ProposicaoTramitacao> |  |
| `links` | array<Link> |  |

### ResultadoReferenciaSubResourceReferenciaDeputado

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | ReferenciaDeputado |  |
| `links` | array<Link> |  |

### ResultadoReferenciaSubResourceReferenciaEvento

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | ReferenciaEvento |  |
| `links` | array<Link> |  |

### ResultadoReferenciaSubResourceReferenciaOrgao

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | ReferenciaOrgao |  |
| `links` | array<Link> |  |

### ResultadoReferenciaSubResourceReferenciaProposicao

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | ReferenciaProposicao |  |
| `links` | array<Link> |  |

### ResultadoReferencias

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Referencia> |  |
| `links` | array<Link> |  |

### ResultadoVotacoes

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Votacao> |  |
| `links` | array<Link> |  |

### ResultadoVotacoesID

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | VotacaoID |  |
| `links` | array<Link> |  |

### ResultadoVotacoesIDOrientacoes

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Orientacao> |  |
| `links` | array<Link> |  |

### ResultadoVotacoesIDVotos

| Campo | Tipo | Descrição |
|---|---|---|
| `dados` | array<Votos> |  |
| `links` | array<Link> |  |

### UltimaApresentacaoProposicao

| Campo | Tipo | Descrição |
|---|---|---|
| `dataHoraRegistro` | string |  |
| `descricao` | string |  |
| `uriProposicaoCitada` | string |  |

### UltimoStatus

| Campo | Tipo | Descrição |
|---|---|---|
| `dataStatus` | string |  |
| `idLegislatura` | string |  |
| `oficioTitulo` | string |  |
| `oficioUri` | string |  |
| `presidenteNome` | string |  |
| `presidenteUri` | string |  |

### UltimoStatusID

| Campo | Tipo | Descrição |
|---|---|---|
| `dataStatus` | string |  |
| `documento` | string |  |
| `idLegislatura` | string |  |
| `oficioAutorNome` | string |  |
| `oficioAutorTipo` | string |  |
| `oficioAutorUri` | string |  |
| `oficioDataApresentacao` | string |  |
| `oficioDataPublicacao` | string |  |
| `oficioTitulo` | string |  |
| `oficioUri` | string |  |
| `presidenteNome` | string |  |
| `presidenteUri` | string |  |

### Votacao

| Campo | Tipo | Descrição |
|---|---|---|
| `aprovacao` | integer (int64) |  |
| `data` | string |  |
| `dataHoraRegistro` | string |  |
| `descricao` | string |  |
| `id` | string |  |
| `proposicaoObjeto` | string |  |
| `siglaOrgao` | string |  |
| `uri` | string |  |
| `uriEvento` | string |  |
| `uriOrgao` | string |  |
| `uriProposicaoObjeto` | string |  |

### VotacaoID

| Campo | Tipo | Descrição |
|---|---|---|
| `aprovacao` | integer (int64) |  |
| `data` | string |  |
| `dataHoraRegistro` | string |  |
| `dataHoraUltimaAberturaVotacao` | string |  |
| `descUltimaAberturaVotacao` | string |  |
| `descricao` | string |  |
| `efeitosRegistrados` | array<EfeitosRegistrados> |  |
| `id` | string |  |
| `idEvento` | integer (int64) |  |
| `idOrgao` | integer (int64) |  |
| `objetosPossiveis` | array<ProposicaoRetornoPrincipal> |  |
| `proposicoesAfetadas` | array<ProposicaoRetornoPrincipal> |  |
| `siglaOrgao` | string |  |
| `ultimaApresentacaoProposicao` | UltimaApresentacaoProposicao |  |
| `uri` | string |  |
| `uriEvento` | string |  |
| `uriOrgao` | string |  |

### Votos

| Campo | Tipo | Descrição |
|---|---|---|
| `dataRegistroVoto` | string |  |
| `deputado_` | Deputado |  |
| `tipoVoto` | string |  |
