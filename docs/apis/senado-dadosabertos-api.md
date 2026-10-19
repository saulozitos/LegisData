# Dados Abertos Legislativos do Senado Federal e Congresso Nacional

**Versão:** 4.1.3.101  
**Base URL:** `https://legis.senado.leg.br`  
**Spec OpenAPI:** `https://legis.senado.leg.br/dadosabertos/v3/api-docs`  
**Swagger UI:** https://legis.senado.leg.br/dadosabertos/api-docs/swagger-ui/index.html

A API de Dados Abertos Legislativos do Senado Federal e do Congresso Nacional é uma API
 de acesso público,
 sem necessidade de autenticação. Contempla informações sobre Parlamentares, reuniões de
 Comissão e Sessões Plenárias, Processos Legislativos, Votações, Discursos, Orçamento
 e diversas outras informações relacionadas ao Processo Legislativo no âmbito do Congresso Nacional Brasileiro.
  Para outras APIs de Dados Abertos do Senado Federal, acesse
 [esta página](https://www12.senado.leg.br/dados-abertos).

**Como selecionar formatos de saída**

Dependendo do formato de saída disponível no campo "Media type" abaixo,
efetue a requisição acrescentando o cabeçalho HTTP *Accept* com um dos formatos disponível
para o serviço no campo "Media type".

Por exemplo: Se existir o formato "application/json" disponível, acrescente o seguinte
cabeçalho a sua requisição: *Accept: application/json*

Alternativamente, para escolher o formato de saída desejado, acrescente o sufixo do formato
desejado ao endereço.
Exemplos:
 * Se disponível o formato *"application/json"*, acrescente o sufixo *".json"* ao endereço.
Ex: *https://legis.senado.leg.br/dadosabertos/legislacao/tiposPublicacao.json*
 * Se disponível o formato *"application/xml"*, acrescente o sufixo *".xml"* ao endereço.
Ex: *https://legis.senado.leg.br/dadosabertos/legislacao/tiposPublicacao.xml*
 * Se disponível o formato *"text/csv"*, acrescente o sufixo *".csv"* ao endereço.
Ex: *https://legis.senado.leg.br/dadosabertos/legislacao/397127.csv*

**Restrição de requisições**

Para garantir acesso justo a todos os usuários, esta API implementa uma limitação de requisições.

- Mais de 10 requisições por segundo estão sujeitas a receber o erro HTTP 429 (Too Many Requests).
- Evite programar rotinas que enviam muitas requisições em horários arredondados (ex: exatamente às 00:00:00,
  01:00:00, 01:15:00 etc.), pois isso pode causar picos de acesso simultâneo.
- Em instantes de muita demanda, as requisições estão sujeitas a receber o erro HTTP 503 (Service Unavailable).

**Aviso**:  Como consequência da remodelagem de dados dos Sistemas Legislativos do Senado
Federal, diversos serviços estão em processo de descontinuação. Confira abaixo quais
serviços estão marcados como <i>Deprecated</i> e quais são os serviços substitutos.

Os serviços depreciados retornam os seguintes cabeçalhos HTTP:
* <i>Deprecation</i>: Data de início da depreciação do serviço
* <i>Sunset</i>: Data da desativação completa do serviço
* <i>Link</i>: URL do serviço substituto

Exemplo de cabeçalhos de depreciação:
```
Deprecation: Mon, 10 Mar 2025 00:00:00 GMT
Sunset: Sun, 01 Feb 2026 00:00:00 GMT
Link: <https://legis.senado.leg.br/dadosabertos/composicao/lideranca>; rel="successor"
```

## Índice

Total: 157 operações em 9 grupos.

- [Comissão](#comissão) (14)
- [Composição](#composição) (16)
- [Discurso](#discurso) (9)
- [Legislação](#legislação) (10)
- [Orçamento](#orçamento) (3)
- [Parlamentar](#parlamentar) (14)
- [Plenário](#plenário) (25)
- [Processo](#processo) (61)
- [Votação](#votação) (5)

## Comissão

### GET `/dadosabertos/comissao/agenda/atual/iCal`

**Obtém a Agenda das Comissões do Congresso Nacional dos próximos 30 dias a partir da data atual. (Formato iCal)**

Retorna a Agenda de Reuniões de Comissão para os próximos 30 dias em formato iCal, 30 dias a partir da data atual.

`operationId`: `AgendaiCalComissoes`

- **200** OK — `text/calendar`

### GET `/dadosabertos/comissao/agenda/mes/{mesReferencia}`

**Agenda das Reuniões de Comissão no mês informado**

Obtém a Agenda das Reuniões das Comissões no mês informado no parâmetro. Formato AAAAMM.

`operationId`: `agendaReuniaoMes`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `mesReferencia` | path | sim | string | 202412 | Mês de referência |
| `v` | query | não | integer (int32) | 2 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`

### GET `/dadosabertos/comissao/agenda/{dataInicio}/{dataFim}`

**Agenda das Reuniões de Comissão**

Obtém a Agenda das Reuniões das Comissões no período informado no formato AAAAMMDD. Máximo de 30 dias.

`operationId`: `agendaReuniaoPeriodo`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `dataInicio` | path | sim | string (date) | 20241210 | Data de início do período |
| `dataFim` | path | sim | string (date) | 20241220 | Data de fim do período |
| `v` | query | não | integer (int32) | 2 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`

### GET `/dadosabertos/comissao/agenda/{dataReferencia}`

**Agenda das Reuniões de Comissão**

Obtém a Agenda das Reunião das Comissões na data informada no formato AAAAMMDD.

`operationId`: `agendaReuniaoDia`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `dataReferencia` | path | sim | string (date) | 20241218 | Data de referência |
| `v` | query | não | integer (int32) | 2 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`

### GET `/dadosabertos/comissao/cpi/{comissao}/requerimentos`

**Lista Requerimentos de CPI. Exclusivo para CPIs**

Retorna a lista de Requerimentos da CPI, com os documentos enviados e/ou recebidos. RETORNO SOMENTE EM JSON.

`operationId`: `requerimentos`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `comissao` | path | sim | string | cpibets | Sigla da comissão |
| `pagina` | query | não | integer (int32) | 1 | (obrigatório) - Número da página da lista de Requerimentos. Se não informado assume 0. |
| `tamanho` | query | não | integer (int32) | 20 | (opcional) - Tamanho da página. É o número de registros retornados por página. Valor padrão 20. Valor permitido de 5 a 30. |

- **200** OK — `application/json`

### GET `/dadosabertos/comissao/lista/colegiados`

**Obtém a Lista geral de Colegiados EM ATIVIDADE no Congresso Nacional**

`operationId`: `listaColegiados`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/comissao/lista/mistas`

**Comissões Mistas atuais do Congresso Nacional**

`operationId`: `listaComissoesMistas`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/comissao/lista/tiposColegiado`

**Obtém a Lista de Tipos de Colegiado do Senado Federal e Congresso Nacional**

`operationId`: `listaTiposColegiado`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/comissao/lista/{tipo}`

**Lista de Colegiados do Senado Federal (por tipo)**

`operationId`: `listaColegiadosSFPorTipo`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `tipo` | path | sim | string | permanente | Tipo do Colegiado: permanente\|cpi\|temporaria\|orgaos |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/comissao/reuniao/notas/{codigoReuniao}`

**Notas Taquigráficas da Reunião de Comissão**

`operationId`: `notasReuniao`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigoReuniao` | path | sim | integer (int64) | 13219 | Código da Reunião |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/comissao/reuniao/{codigoReuniao}`

**Informações detalhadas da Reunião de Comissão**

Obtém as informações da Reunião de Comissão, incluindo detalhes dos itens de pauta (autoria, relatoria, resultado etc.)

`operationId`: `detalheReuniao`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigoReuniao` | path | sim | integer (int64) | 1500 | Código da Reunião |
| `v` | query | não | integer (int32) | 2 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/comissao/reuniao/{sigla}/documento/{tipoDocumento}`

**Link para um documento da última Reunião de uma Comissão**

Retorna o link para o documento, através do status HTTP "Temporary Redirect" (307),
se o documento não existir retorna HTTP "Not Found" (404)

`operationId`: `documentoReuniao`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `sigla` | path | sim | string | CAE | Sigla da Comissão |
| `tipoDocumento` | path | sim | string | pauta | Tipo do documento (pauta\|pautacheia\|resultado) |

- **307** Redireciona para o documento se existir — `*/*`

### GET `/dadosabertos/comissao/{codigo}`

**Detalhes de um Colegiado do Congresso Nacional**

`operationId`: `detalhesColegiado`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 449 | Código do Colegiado (Comissão) |
| `v` | query | não | integer (int32) | 3 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/comissao/{comissao}/documentos`

**(DEPRECATED) Obtém os documentos apresentados em um Colegiado**

Substitua pelo serviço disponível em [/dadosabertos/processo/documento](#/Processo/documentosProcesso).

Se não informar o período, serão retornados os documentos apresentados nos últimos 30 dias.

`operationId`: `documentosColegiado` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `comissao` | path | sim | string | cpipandemia | Sigla do Colegiado (Comissão) |
| `tipo` | query | não | string | REQ | Sigla do tipo de identificação do documento |
| `dataInicio` | query | não | string (date) | 20210501 | Data de início do período da pesquisa no formato AAAAMMDD.     Se não for informada, dataInicio = data atual - 1 mês |
| `dataFim` | query | não | string (date) | 20210531 | Data de fim do período da pesquisa no formato AAAAMMDD.     Se não for informada, dataFim = data atual |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

## Composição

### GET `/dadosabertos/composicao/bloco/{codigo}`

**Composição de um Bloco Parlamentar**

`operationId`: `bloco`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 335 | Código do Bloco (vide serviço /composicao/lista/blocos) |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/composicao/comissao/atual/mista/{codigo}`

**Composição atual de uma Comissão Mista**

`operationId`: `composicaoAtualMista`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 449 | Código da Comissão |
| `v` | query | não | integer (int32) | 3 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/composicao/comissao/resumida/mista/{codigo}/{dataInicio}/{dataFim}`

**Composição resumida de uma Comissão Mista em determinado período**

`operationId`: `composicaoResumidaMista`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 1664 | Código da Comissão |
| `dataInicio` | path | sim | string | 20240518 | Data de início do período no formato AAAAMMDD |
| `dataFim` | path | sim | string | 20240518 | Data de fim do período no formato AAAAMMDD |
| `v` | query | não | integer (int32) | 3 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/composicao/comissao/{codigo}`

**Última Composição de uma Comissão do Senado Federal**

`operationId`: `ultimaComposicaoComissao`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int32) | 34 | Código da Comissão |
| `ativas` | query | sim | string | S | Para vagas ativas apenas (S). Para todas, não informe este parâmetro |
| `v` | query | não | integer (int32) | 3 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/composicao/lideranca`

**Lista Lideranças do Senado Federal, Congresso Nacional e Câmara dos Deputados**

É obrigatório informar pelo menos um dos seguintes parâmetros:
 * codigo
 * codigoParlamentar
 * vigente (com valor S - default se nenhum outro parâmetro obrigatório for informado)
 * dataInicio + dataFim (intervalo deve ser de até 1 ano no máximo se nenhum outro parâmetro
 obrigatório for informado)
 * codigoPartido
 * codigoBloco

Caso nenhum desses parâmetros for informado, retornará somente as lideranças vigentes
(vigente=S).

`operationId`: `listaLiderancas`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | query | não | integer (int64) |  | Codigo da liderança |
| `casa` | query | não | string |  | Casa da liderança (CN, CD ou SF) |
| `idTipoUnidadeLideranca` | query | não | integer (int32) |  | ID do tipo de unidade de liderança - veja a lista de tipos em /lideranca/tipos-unidade |
| `codigoParlamentar` | query | não | integer (int64) |  | Código do parlamentar |
| `vigente` | query | não | string |  | 'S' - Vigentes, 'N' - Encerradas, Em branco - Todas |
| `dataInicio` | query | não | string (date) |  | Lideranças designadas a partir desta data, no formato AAAA-MM-DD |
| `dataFim` | query | não | string (date) |  | Lideranças designadas até esta data, no formato AAAA-MM-DD |
| `siglaTipoLideranca` | query | não | string |  | Sigla do tipo de liderança - veja a lista de tipos em /lideranca/tipos |
| `codigoPartido` | query | não | integer (int64) |  | Código do partido |
| `codigoBloco` | query | não | integer (int64) |  | Código do bloco |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/json`, `application/x-ndjson`, `application/xml`, `text/csv`

### GET `/dadosabertos/composicao/lideranca/tipos`

**Lista Tipos de Lideranças**

`operationId`: `getTiposLideranca`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/composicao/lideranca/tipos-unidade`

**Lista Tipos de Unidades de Lideranças**

`operationId`: `getTiposUnidadeLideranca`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/composicao/lista/blocos`

**Obtém a lista e a Composição dos Blocos Parlamentares no Senado Federal**

`operationId`: `listaBlocosParlamentares`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/composicao/lista/cn/{tipo}`

**Composição das Comissões do Congresso Nacional por tipo**

`operationId`: `listaComissoesCN`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `tipo` | path | sim | string | cpmi | Tipo de comissão: cpmi, veto, permanente, mpv, mistaEspecial, mesa, trabalhoCCS, representativa |
| `v` | query | não | integer (int32) | 3 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/composicao/lista/liderancaCN`

**(DEPRECATED) Obtém a lista das Lideranças em atividade no Congresso Nacional**

Substitua pelo serviço de Lideranças disponível em [/dadosabertos/composicao/lideranca](#/Composição/liderancas)

`operationId`: `listaLiderancaCN` — **DEPRECADO**

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/composicao/lista/liderancaSF`

**(DEPRECATED) Obtém a lista das Lideranças em atividade no Senado Federal**

Substitua pelo serviço de Lideranças disponível em [/dadosabertos/composicao/lideranca](#/Composição/liderancas)

`operationId`: `listaLiderancaSF` — **DEPRECADO**

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/composicao/lista/partidos`

**Obtém a lista dos Partidos Políticos em atividade e/ou extintos no Senado Federal**

`operationId`: `listaTiposPrazos_1`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/composicao/lista/tiposCargo`

**Obtém a lista de Tipos de Cargo nas Comissões do Senado Federal e Congresso Nacional**

`operationId`: `listaTiposCargo`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/composicao/lista/{tipo}`

**Obtém a Composição das Comissões do Senado Federal por tipo de Colegiado**

`operationId`: `listaComposicaoColegiadoTipo`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `tipo` | path | sim | string | permanente | Tipo de colegiado conforme opções: cpi\|cpmi\|permanente\|orgaos\|temporaria |

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/composicao/mesaCN`

**Obtém a Composição dos integrantes da Mesa Diretora do Congresso Nacional**

`operationId`: `mesaDiretoraCN`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/composicao/mesaSF`

**Obtém a Composição dos integrantes da Mesa Diretora do Senado Federal**

`operationId`: `mesaDiretoraSF`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

## Discurso

### GET `/dadosabertos/discurso/texto-binario/{codigoPronunciamento}`

**Texto Integral de um Pronunciamento em formato binário**

`operationId`: `getDiscursoTextoBinario`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigoPronunciamento` | path | sim | integer (int64) | 398013 | Código do Pronunciamento |

- **200** OK — `*/*`

### GET `/dadosabertos/discurso/texto-integral/{codigoPronunciamento}`

**Texto Integral de um Pronunciamento em formato texto plano (txt)**

`operationId`: `getDiscursoTextoIntegral`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigoPronunciamento` | path | sim | integer (int64) | 398013 | Código do Pronunciamento |

- **200** OK — `text/plain`

### GET `/dadosabertos/senador/lista/tiposUsoPalavra`

**Lista os Tipos de Uso da Palavra (Modalidades de Discursos)**

`operationId`: `listaTiposUsoPalavra`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/senador/{codigo}/apartes`

**Apartes feitos por um Senador**

`operationId`: `aparteSenador`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 4763 | Código do Senador |
| `casa` | query | não | string | SF | Sigla da Casa onde ocorre o pronunciamento - SF (Senado Federal), CD (Câmara dos Deputados), CN (Congresso Nacional), PR (Presidência), CR (Comissão Representativa do Congresso), AC (Assembléia Constituinte) |
| `dataInicio` | query | não | string (date) | 20150301 | Data de início do período da pesquisa no formato AAAAMMDD. Se não for informada, dataFim = data atual - 1 mês |
| `dataFim` | query | não | string (date) | 20150331 | Data de fim do período da pesquisa no formato AAAAMMDD. Se não for informada, dataFim = data atual |
| `numeroSessao` | query | não | integer (int64) | 456 | Número da Sessão Plenária |
| `tipoSessao` | query | não | string | DOR | Tipo da Sessão Plenária (veja serviço que lista os Tipos de Sessão: /dadosabertos/plenario/tiposSessao) |
| `v` | query | não | integer (int32) | 5 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/senador/{codigo}/discursos`

**Discursos de um Senador**

Retorna a relação de Discursos do Senador proferidos no período máximo de 1 ano.
Se não informar o período, serão retornados os discursos dos últimos 30 dias.

`operationId`: `discursoSenador`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 5529 | Código do Senador |
| `casa` | query | não | string | SF | Sigla da Casa onde ocorre o pronunciamento - SF (Senado Federal), CD (Câmara dos Deputados), CN (Congresso Nacional), PR (Presidência), CR (Comissão Representativa do Congresso), AC (Assembléia Constituinte) |
| `dataInicio` | query | não | string (date) | 20150301 | Data de início do período da pesquisa no formato AAAAMMDD. Se não for informada, dataFim = data atual - 1 mês |
| `dataFim` | query | não | string (date) | 20150331 | Data de fim do período da pesquisa no formato AAAAMMDD. Se não for informada, dataFim = data atual |
| `numeroSessao` | query | não | integer (int64) | 456 | Número da Sessão Plenária |
| `tipoSessao` | query | não | string | DOR | Tipo da Sessão Plenária (veja serviço que lista os Tipos de Sessão: /dadosabertos/plenario/tiposSessao) |
| `v` | query | não | integer (int32) | 5 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/taquigrafia/notas/reuniao/{idReuniao}`

**Notas Taquigráficas de Reuniões de Comissão e/ou outros Colegiados**

Recupera os dados estruturados das Notas Taquigráficas da Reunião de Comissão ou Colegiado informada no parâmetro.

`operationId`: `NotasReuniao`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `idReuniao` | path | sim | integer (int64) | 11762 | Código do Encontro Legislativo (Reunião de Colegiado) |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/taquigrafia/notas/sessao/{idSessao}`

**Notas Taquigráficas de Sessões Plenárias**

Recupera os dados estruturados das Notas Taquigráficas da Sessão Plenária informada no parâmetro.

`operationId`: `NotasSessao`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `idSessao` | path | sim | integer (int64) | 26303 | Código do Encontro Legislativo (Sessão Plenária) |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/taquigrafia/videos/reuniao/{idReuniao}`

**Unidades Descritivas (vídeos) de Reuniões de Comissão e/ou outros Colegiados**

Recupera as falas dos Parlamentares ao longo da Reunião, associadas aos trechos de vídeos que ocorreram.

`operationId`: `VideosReuniao`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `idReuniao` | path | sim | integer (int64) | 11762 | Código do Encontro Legislativo (Reunião de Colegiado) |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/taquigrafia/videos/sessao/{idSessao}`

**Unidades Descritivas (vídeos) de Sessões Plenárias**

Recupera as falas dos Parlamentares ao longo da Sessão Plenária, associadas aos trechos de vídeos que ocorreram.

`operationId`: `VideosSessao`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `idSessao` | path | sim | integer (int64) | 26303 | Código do Encontro Legislativo (Sessão Plenária) |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

## Legislação

### GET `/dadosabertos/legislacao/classes`

**Lista Classificação de Normas Jurídicas, Projetos e Pronunciamentos**

Lista tabela do Sistema de Classificação utilizado na categorização de Normas Jurídicas, Projetos e Pronunciamentos.

`operationId`: `listaClasses`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/legislacao/lista`

**Pesquisa de Normas Federais**

Obtém a lista de Legislação Federal com base nos parâmetros informados.

`operationId`: `pesquisaLegislacao`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `tipo` | query | não | string | LEI | Sigla do tipo da Norma |
| `numero` | query | não | integer (int32) | 8112 | Número da Norma |
| `ano` | query | não | integer (int32) | 2013 | Ano da Norma |
| `data` | query | não | string | 19901211 | Data da assinatura da Norma no formato AAAAMMDD |
| `seq` | query | não | integer (int32) | 12 | Número sequencial da assinatura da Norma na data |
| `reedicao` | query | não | integer (int32) | 3 | Número sequencial da reedição |
| `ident` | query | não | string | A | Letra de Identificação |
| `complemento` | query | não | string | C | Letra de Complemento |
| `v` | query | não | integer (int32) | 3 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/legislacao/termos`

**Pesquisa de Termos do Catálogo**

Obtém a lista Termos do Catálogo, com base nos parâmetros informados.

`operationId`: `pesquisaTermos`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `tipo` | query | não | integer (int32) | 9 | Código referente ao Tipo de Termo |
| `termo` | query | não | string | método | Termo a ser pesquisado |
| `v` | query | não | integer (int32) | 3 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/legislacao/tiposNorma`

**Lista Tipos de Norma**

`operationId`: `listaTiposNorma`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/legislacao/tiposPublicacao`

**Lista de Tipos de Publicação**

`operationId`: `listaTiposPublicacao`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/legislacao/tiposVide`

**Lista de Tipos de Declaração**

Retorna a lista de Tipos de Declaração.

`operationId`: `listaTiposVide`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/legislacao/tiposdeclaracao/detalhe`

**Lista de Detalhes de Declaração**

Retorna a lista de Detalhes de Declaração.

`operationId`: `listaTiposDeclaracaoDetalhe`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/legislacao/urn`

**Detalhes de uma Norma Jurídica pela URN**

Obtém detalhes de uma Norma Jurídica por meio da URN informada no parâmetro.

`operationId`: `normaUrn`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `urn` | query | sim | string | urn:lex:br:federal:lei:2006-08-07;11340 | Identificador Universal da Norma, presente no normas.leg.br |
| `v` | query | não | integer (int32) | 3 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/legislacao/{codigo}`

**Detalhes de uma Norma Jurídica pelo código**

Obtém detalhes de uma Norma Jurídica por meio do código informado no parâmetro.

`operationId`: `normaId`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int32) | 397127 | Código do Documento (Norma Jurídica) |
| `v` | query | não | integer (int32) | 3 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/legislacao/{tipo}/{numdata}/{anoseq}`

**Detalhes de uma Norma Jurídica pela identificação (sigla / número / ano)**

Obtém detalhes da Norma por meio do tipo/número/ano ou data de assinatura/sequencial

`operationId`: `normaIdentificacao`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `tipo` | path | sim | string | LEI | Sigla do Tipo da Norma |
| `numdata` | path | sim | integer (int32) |  | Número ou data da Norma no formato AAAAMMDD |
| `anoseq` | path | sim | integer (int32) | 1990 | Ano da data de assinatura da Norma ou sequencial |
| `v` | query | não | integer (int32) | 3 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

## Orçamento

### GET `/dadosabertos/orcamento/lista`

**Lotes de Emendas ao Orçamento**

`operationId`: `listaEmendas`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/orcamento/oficios`

**Lista os Ofícios de apoio às Emendas de Orçamento**

Retorna a lista de Ofícios de apoio às Emendas de Orçamento.

`operationId`: `listaOficios`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/orcamento/oficios/{numeroSedol}`

**Recupera informações de determinado Ofício de apoio às Emendas de Orçamento**

Retorna informações do Ofício e a relação de Emendas apoiadas pelo mesmo.

`operationId`: `detalheOficio`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |
| `numeroSedol` | path | sim | string | SF254855761583 | Número do Documento Sedol recuperado na lista de Ofícios (/dadosbabertos/orcamento/oficios). Se não existir um Número do Documento Sedol, utilize o atributo 'id' do Ofício para recuperar seus detalhes. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

## Parlamentar

### GET `/dadosabertos/senador/afastados`

**Obtém a lista dos Senadores atualmente afastados (Fora de Exercício)**

`operationId`: `listaAfastados`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/senador/lista/atual`

**Senadores em Exercício**

Lista de Senadores em Exercício. Permite filtrar por UF e tipo de participação.

`operationId`: `listaSenadoresEmExercicio`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `uf` | query | não | string | DF | UF de mandato do Senador - sigla com dois caracteres |
| `participacao` | query | não | string enum(T, S) | T | Tipo de participação no mandato: (T)itular ou (S)uplente |
| `v` | query | não | integer (int32) | 4 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/senador/lista/legislatura/{legislaturaInicio}/{legislaturaFim}`

**Obtém a lista de Senadores de um intervalo de Legislaturas**

Retorna a lista de Senadores com mandatos dentro do período das Legislaturas informadas.

`operationId`: `listaLegislaturaIniFimSenador`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `legislaturaInicio` | path | sim | integer (int32) | 54 | Número da Legislatura inicial. O mandato deverá iniciar após a Legislatura informada. |
| `legislaturaFim` | path | sim | integer (int32) | 56 | Número da Legislatura final. O mandato deverá finalizar antes da Legislatura informada. |
| `uf` | query | não | string | RJ | Filtra pela sigla da UF do mandato |
| `participacao` | query | não | string | T | Filtra pelo tipo de participação no mandato. (T)itular ou (S)uplente |
| `exercicio` | query | não | string | S | Filtra apenas parlamentares que entraram em exercício (S)im ou apenas os que não entraram (N)ão |
| `v` | query | não | integer (int32) | 4 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/senador/lista/legislatura/{legislatura}`

**Obtém a lista de Senadores de uma determinada Legislatura**

`operationId`: `listaLegislaturaSenador`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `legislatura` | path | sim | integer (int32) | 54 | Número da Legislatura de referência. O Mandato deverá abranger a Legislatura informada. |
| `uf` | query | não | string | RJ | Filtra pela sigla da UF do mandato |
| `participacao` | query | não | string | T | Filtra pelo tipo de participação no mandato. (T)itular ou (S)uplente |
| `exercicio` | query | não | string | S | Filtra apenas parlamentares que entraram em exercício (S)im ou apenas os que não entraram (N)ão |
| `v` | query | não | integer (int32) | 4 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/senador/partidos`

**Lista os Partidos Políticos em atividade e/ou extintos**

`operationId`: `listaTiposPrazos`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/senador/{codigo}`

**Obtém informações de um Senador**

`operationId`: `detalhesSenador`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 5322 | Código do Senador |
| `v` | query | não | integer (int32) | 6 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `*/*`

### GET `/dadosabertos/senador/{codigo}/cargos`

**Obtém a relação de Cargos ocupados por um Senador**

`operationId`: `cargoSenador`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 5322 | Código do Senador |
| `ativo` | query | não | string | S | Exibe apenas cargos ativos 'S' ou exibe os cargos finalizados 'N' |
| `comissao` | query | não | string | CCJ | Sigla da Comissão - retorna apenas os cargos na Comissão informada |
| `v` | query | não | integer (int32) | 5 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/senador/{codigo}/comissoes`

**Obtém a relação das Comissões que um Senador é membro**

`operationId`: `comissaoSenador`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int32) | 5322 | Código do Senador |
| `ativo` | query | não | string | S | Se 'S' retorna apenas as Comissões atuais, se 'N' retorna apenas as já finalizadas |
| `comissao` | query | não | string | CE | Sigla da Comissão - retorna apenas a Comissão informada |
| `v` | query | não | integer (int32) | 5 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/senador/{codigo}/filiacoes`

**Obtém as Filiações Partidárias de um Senador**

`operationId`: `filiacaoSenador`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 5322 | Código do Senador |
| `v` | query | não | integer (int32) | 5 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/senador/{codigo}/historicoAcademico`

**Obtém o Histórico Acadêmico de um Senador**

Retorna a relação de Cursos feitos pelo Senador.

`operationId`: `historicoAcademicoSenador`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 5322 | Código do Senador |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/senador/{codigo}/licencas`

**Obtém as Licenças oficiais de um Senador**

`operationId`: `licencaSenador`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 5322 | Código do Senador |
| `dataInicio` | query | não | string | 20190201 | Data de início de referência para pesquisa no formato AAAAMMDD. |
| `dataFim` | query | não | string | 20240301 | Data de término de referência para pesquisa no formato AAAAMMDD. Se não informado considera-se a data atual. |
| `v` | query | não | integer (int32) | 6 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/senador/{codigo}/liderancas`

**(DEPRECATED) Obtém os Cargos de Liderança de um Senador**

Substitua pelo serviço de Lideranças disponível em [/dadosabertos/composicao/lideranca](#/Composição/liderancas)

`operationId`: `liderancaSenador` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 4981 | Código do Senador |
| `ativo` | query | não | string | S | Se 'S' retorna apenas as Lideranças em exercício, se 'N' retorna também as já finalizadas |
| `v` | query | não | integer (int32) | 5 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/senador/{codigo}/mandatos`

**Obtém os Mandatos Parlamentares de um Senador**

`operationId`: `mandatoSenador`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 5322 | Código do Senador |
| `v` | query | não | integer (int32) | 5 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/senador/{codigo}/profissao`

**Obtém as Profissões de um Senador**

`operationId`: `profissaoSenador`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 5985 | Código do Senador |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

## Plenário

### GET `/dadosabertos/plenario/agenda/atual/iCal`

**Agenda de Plenário em formato iCal**

Retorna a Agenda dos Plenários do Senado Federal e Congresso Nacional em formato iCal, 30 dias a partir da data atual.

`operationId`: `AgendaiCalPlenario`

- **200** Retorna a Agenda do mês nos Plenários do Senado Federal e Congresso Nacional. — `text/calendar`

### GET `/dadosabertos/plenario/agenda/cn/{data}`

**Agenda do dia do Plenário do Congresso Nacional**

`operationId`: `agendaNaDataCN`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `data` | path | sim | string | 20130522 | Data da Agenda no formato AAAAMMDD |
| `v` | query | não | integer (int32) | 2 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/agenda/cn/{inicio}/{fim}`

**Agenda do período do Plenário do Congresso Nacional**

`operationId`: `agendaDoPeriodoCN`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `inicio` | path | sim | string | 20130501 | Data de início da Agenda no formato AAAAMMDD |
| `fim` | path | sim | string | 20130531 | Data de fim da Agenda no formato AAAAMMDD |
| `v` | query | não | integer (int32) | 2 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/agenda/dia/{data}`

**Agenda do dia nos Plenários do Senado Federal e Congresso Nacional**

`operationId`: `AgendaDiaPlenario`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `data` | path | sim | string (date) | 20241015 | Data de referência para pesquisa da Agenda no formato AAAAMMDD. |
| `v` | query | não | integer (int32) | 2 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/agenda/mes/{data}`

**Agenda do mês nos Plenários do Senado Federal e Congresso Nacional**

Retorna a Agenda do mês nos Plenários do Senado Federal e Congresso Nacional (a partir da data informada até o fim do mês).

`operationId`: `AgendaMesPlenario`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `data` | path | sim | string (date) | 20241015 | Data de referência para pesquisa da Agenda no formato AAAAMMDD |
| `v` | query | não | integer (int32) | 2 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/encontro/{codigo}`

**Detalhes do Encontro Legislativo**

Recupera os detalhes do Encontro Legislativo.

`operationId`: `detalheEncontro`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int32) | 319359 | Código do Encontro Legislativo |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/encontro/{codigo}/pauta`

**Itens de Pauta do Encontro Legislativo**

`operationId`: `pautaEncontro`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int32) | 319359 | Código do Encontro Legislativo |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/encontro/{codigo}/resultado`

**Resultado de Pauta do Encontro Legislativo**

Retorna a relação de Itens de Pauta do Encontro Legislativo com os resultados da apreciação.

`operationId`: `resultadoEncontro`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int32) | 319359 | Código do Encontro Legislativo |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** Retorna a relação de Itens de Pauta do Encontro Legislativo com os resultados da apreciação. — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/encontro/{codigo}/resumo`

**Resumo do Encontro Legislativo**

Retorna o resumo do Encontro Legislativo.

`operationId`: `resumoEncontro`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int32) | 319359 | Código do Encontro Legislativo |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/legislatura/{data}`

**Obtém a Legislatura na data informada e suas Sessões Legislativas**

`operationId`: `legislaturaData`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `data` | path | sim | string | 20130313 | Data de referência para pesquisa da Legislatura no formato AAAAMMDD. |
| `v` | query | não | integer (int32) | 3 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/lista/discursos/{dataInicio}/{dataFim}`

**Discursos por período/sessão**

Lista Discursos das Sessões que ocorreram dentro do período informado (máximo de 1 mês).

`operationId`: `listaDiscursosSessao`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `dataInicio` | path | sim | string | 20130301 | Data de início do período da consulta no formato AAAAMMDD |
| `dataFim` | path | sim | string | 20130331 | Data de fim do período da consulta no formato AAAAMMDD |
| `siglaCasa` | query | não | string | SF | Sigla da casa (SF = Senado Federal, CN = Congresso Nacional) |
| `tipoSessao` | query | não | string | DOR | Sigla do tipo de Sessão |
| `numeroSessao` | query | não | string | 456 | Número da Sessão |
| `v` | query | não | integer (int32) | 4 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/lista/legislaturas`

**Lista de todas as Legislaturas e suas Sessões Legislativas**

Retorna a lista de todas as Legislaturas e suas Sessões Legislativas em ordem decrescente de número da Legislatura.

`operationId`: `listaLegislatura`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/lista/tiposComparecimento`

**Lista os Tipos de Comparecimento em Votações do Plenário**

`operationId`: `listaTiposComparecimento`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/lista/votacao/{dataInicio}/{dataFim}`

**(DEPRECATED) Lista de Votações Nominais nas Sessões por período**

Substitua pelo serviço de listagem de votos disponível em [/dadosabertos/votacao](#/Votação/votacoes)

`operationId`: `listaVotacoesPeriodoSessao` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `dataInicio` | path | sim | string | 20160401 | Data de início do período da consulta no formato AAAAMMDD |
| `dataFim` | path | sim | string | 20160430 | Data de fim do período da consulta no formato AAAAMMDD |
| `v` | query | não | integer (int32) | 2 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/lista/votacao/{dataSessao}`

**(DEPRECATED) Lista de Votações Nominais nas Sessões por data**

Substitua pelo serviço de listagem de votos disponível em [/dadosabertos/votacao](#/Votação/votacoes)

`operationId`: `listaVotacoesDataSessao` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `dataSessao` | path | sim | string | 20130516 | Data de referência da Sessão no formato AAAAMMDD |
| `v` | query | não | integer (int32) | 2 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/resultado/cn/{data}`

**Resultado da Sessão Plenária do Congresso Nacional**

`operationId`: `resultadoSessaoCN`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `data` | path | sim | string | 20241218 | Data da Sessão no formato AAAAMMDD |
| `v` | query | não | integer (int32) | 3 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/resultado/mes/{data}`

Obtém o resultado do mês das Sessões Plenárias a partir da data informada.

`operationId`: `resultadoMes`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `data` | path | sim | string (date) | 20240915 | Data de referência para consulta no formato AAAAMMDD |
| `v` | query | não | integer (int32) | 2 | Versão do serviço. Exemplificada a última disponível. |

- **200** Retorna o resultado do mês das Sessões Plenárias a partir da data informada até o último dia do mês. — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/resultado/veto/dispositivo/{codigo}`

**Resultado da Votação Nominal de um Dispositivo do Veto (em Vetos Parciais)**

`operationId`: `resultadoVetoVotacaoDispositivo`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int32) | 30582 | Código do Dispositivo do Veto |
| `v` | query | não | integer (int32) | 7 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/resultado/veto/materia/{codigo}`

**Resultado da Votação Nominal do Veto a um Projeto de Lei**

`operationId`: `resultadoVeto`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int32) | 132990 | Código da Matéria |
| `v` | query | não | integer (int32) | 7 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/resultado/veto/{codigo}`

**Resultado da Votação Nominal de Veto**

`operationId`: `resultadoItemVeto`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int32) | 11762 | Código do Veto |
| `v` | query | não | integer (int32) | 7 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/resultado/{data}`

**Obtém o Resultado da Sessão Plenária na data informada**

Retorna o Resultado dos Itens de Pauta das Sessões Plenárias na data informada.

`operationId`: `resultadoDia`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `data` | path | sim | string (date) | 20241015 | Data de referência para consulta no formato AAAAMMDD |
| `v` | query | não | integer (int32) | 2 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/tiposSessao`

**Lista os Tipos de Sessão Plenária**

`operationId`: `listaTiposSessao`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/votacao/nominal/{ano}`

**(DEPRECATED) Votações Nominais por ano**

Substitua pelo serviço de listagem de votos disponível em [/dadosabertos/votacao](#/Votação/votacoes)

`operationId`: `listaVotacoesAno` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `ano` | path | sim | integer (int32) | 2023 | Ano de referência desejado, no formato AAAA. |

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/votacao/orientacaoBancada/{dataInicio}/{dataFim}`

**Orientação de Bancada para Votação de Matéria das Sessões que ocorreram em um período**

`operationId`: `orientacaoBancadaPeriodo`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `dataInicio` | path | sim | string | 20231212 | Data de início do período da consulta no formato AAAAMMDD |
| `dataFim` | path | sim | string | 20231220 | Data de fim do período da consulta no formato AAAAMMDD |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/plenario/votacao/orientacaoBancada/{dataSessao}`

**Orientação de Bancada para Votação de Matéria das Sessões que ocorreram em uma data**

`operationId`: `orientacaoBancadaData`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `dataSessao` | path | sim | string | 20220209 | Data de referência da consulta no formato AAAAMMDD |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

## Processo

### GET `/dadosabertos/autor/lista/atual`

**Lista Parlamentares Autores de Processos em tramitação no Senado Federal ou no
Congresso Nacional, com o quantitativo de processos de sua autoria.
**

`operationId`: `autoresMateriasEmTramitacao`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/autor/tiposAutor`

**(DEPRECATED) Lista os Tipos de Autor**

Substitua pelo serviço em [/dadosabertos/processo/tipos-autor](#Processo/tiposAutor)

`operationId`: `tiposAutorMateria` — **DEPRECADO**

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/materia/assuntos`

**(DEPRECATED) Lista de Assuntos de Matérias Legislativas (Proposições)**

Substitua pelo serviço em [/dadosabertos/processo/assuntos](#/Processo/assuntosProcesso)

`operationId`: `assuntos` — **DEPRECADO**

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/materia/atualizacoes/{codigo}`

**(DEPRECATED) Atualizações mais recentes de uma Matéria**

Substitua pelo serviço de detalhes do processo em [/dadosabertos/processo/{idProcesso}](#/Processo/detalhesProcesso)

`operationId`: `atualizacoes` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | string | 140534 | Código da matéria |
| `numdias` | query | não | string | 30 | Número de dias a considerar (X): atualizações ocorridas nos últimos X dias - X por default é 30. Estão disponíbeis as atualizações dos últimos 30 dias. |
| `v` | query | não | integer (int32) | 5 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`, `*/*`

### GET `/dadosabertos/materia/atualizadas`

**(DEPRECATED) Lista as Matérias que foram incluídas ou sofreram atualização nos últimos dias (default = 5)**

Substitua pelos serviços de listagem e detalhes de processo - [/dadosabertos/processo](#/Processo/processos) e [/dadosabertos/processo/{idProcesso}](#/Processo/detalhesProcesso)

`operationId`: `atualizadas` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `numdias` | query | não | integer (int32) | 5 | Número de dias a considerar (X): matérias alteradas nos últimos X dias - X por default é 5. Há dados de até 30 dias |
| `alteracao` | query | não | string |  | Tipo de alteração da matéria. Veja lista em /dadosabertos/materia/tiposatualizacoes |
| `codigo` | query | não | integer (int64) |  | Código da matéria |
| `sigla` | query | não | string | PL | Sigla do subtipo da matéria. Veja lista em /dadosabertos/materia/subtipos |
| `numero` | query | não | string |  | Número da matéria |
| `ano` | query | não | integer (int32) |  | Ano da matéria |
| `codAssuntoGeral` | query | não | integer (int64) |  | Código do assunto geral da matéria |
| `codAssuntoEspecifico` | query | não | integer (int64) |  | Código do assunto específico da matéria. Veja lista em /dadosabertos/materia/assuntos |
| `termo` | query | não | string |  | Termo a ser pesquisado na indexação da matéria |
| `v` | query | não | integer (int32) | 5 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/materia/autoria/{codigo}`

**(DEPRECATED) Autoria da Matéria**

Substitua pelo serviço de detalhes do processo em [/dadosabertos/processo/{idProcesso}](#/Processo/detalhesProcesso)

`operationId`: `autoria` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 131506 | Código da Matéria |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`, `*/*`

### GET `/dadosabertos/materia/classes`

**(DEPRECATED) Lista as Classificações de Matérias Legislativas**

Substitua pelo serviço em [/dadosabertos/processo/classes](#/Processo/classesProcesso)

`operationId`: `classes` — **DEPRECADO**

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/materia/decisoes`

**(DEPRECATED) Lista os Tipos de Decisões em votações de Matérias Legislativas**

Substitua pelo serviço em [/dadosabertos/processo/tipos-decisao](#/Processo/tiposDecisao)

`operationId`: `decisoes` — **DEPRECADO**

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/materia/destinos`

**(DEPRECATED) Lista os Destinos possíveis de Matérias Legislativas**

Substitua pelo serviço em [/dadosabertos/processo/destinos](#/Processo/destinosProcesso)

`operationId`: `destinos` — **DEPRECADO**

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/materia/distribuicao/autoria`

**Distribuição de autoria de matérias (por comissão e/ou parlamentar)**

`operationId`: `distribuicaoAutoria_1`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `siglaComissao` | query | não | string | CCJ | Sigla da comissão |
| `codParlamentar` | query | não | integer (int64) | 3830 | Código do parlamentar |
| `v` | query | não | integer (int32) | 5 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/materia/distribuicao/autoria/{siglaComissao}`

**Distribuição de autoria de matérias em uma comissão**

`operationId`: `distribuicaoAutoria`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `siglaComissao` | path | sim | string | CCJ | Sigla da comissão |
| `codParlamentar` | query | não | integer (int64) | 3830 | Código do parlamentar |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/materia/distribuicao/relatoria/{sigla}`

**Distribuição de relatoria de matérias em uma comissão**

`operationId`: `distribuicaoRelatoria`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `sigla` | path | sim | string | CCJ | Sigla da comissão |
| `v` | query | não | integer (int32) | 2 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/materia/emenda/{idDomaEmenda}`

**(DEPRECATED) Detalhes da Emenda - por ID do Documento da Emenda**

Substitua pelo serviço em [/dadosabertos/processo/emenda](#/Processo/emendasProcesso)

`operationId`: `emenda` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `idDomaEmenda` | path | sim | integer (int64) | 7950411 | Identificação do Documento Manifestação da Emenda |
| `v` | query | não | integer (int32) | 5 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`, `*/*`

### GET `/dadosabertos/materia/emendas/{codigo}`

**(DEPRECATED) Emendas da Matéria**

Substitua pelo serviço em [/dadosabertos/processo/emenda](#/Processo/emendasProcesso)

`operationId`: `emendas` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 135064 | Código da Matéria |
| `v` | query | não | integer (int32) | 6 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`, `*/*`

### GET `/dadosabertos/materia/legislaturaatual`

**(DEPRECATED) Lista as Matérias que estão em tramitação ou que tramitaram na Legislatura atual**

Substitua pelo serviço de listagem de processos em [/dadosabertos/processo](#/Processo/processos)

`operationId`: `legislaturaatual` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `tramitando` | query | não | string |  | (S ou N) - Retorna apenas as matérias que estão tramitando (S) ou apenas as que não estão (N).     Se o parâmetro não for informado, retorna ambas. |
| `sigla` | query | não | string | PEC | Sigla do subtipo da matéria. Veja lista em /dadosabertos/materia/subtipos |
| `numero` | query | não | string | 1 | Número da matéria |
| `ano` | query | não | integer (int32) |  | Ano da matéria |
| `v` | query | não | integer (int32) | 5 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`, `*/*`

### GET `/dadosabertos/materia/lista/comissao`

**(DEPRECATD) Lista as Matérias Legislativas localizadas em uma Comissão**

Substitua pelo serviço de listagem de processos em [/dadosabertos/processo](#/Processo/processos)

`operationId`: `listaMateriasComissao` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `materia` | query | não | integer (int32) | 141069 | Código da Matéria |
| `comissao` | query | não | string | CCJ | Sigla da Comissão |
| `situacao` | query | não | string | RELATORIA | Sigla da Situação da Matéria - veja tipos possíveis em /dadosabertos/materia/situacoes |
| `v` | query | não | integer (int32) | 2 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/materia/lista/prazo/{codPrazo}`

**(DEPRECATED) Matérias Legislativas que tramitam com Prazo determinado**

Substitua pelo serviço de prazos de Processos localizado em [/dadosaberto/processo/prazo](#/Processo/prazos)

`operationId`: `listaMateriasPrazo` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codPrazo` | path | sim | integer (int64) | 0 | Código do Tipo de Prazo (use 0 para todos tipos) - veja lista de Tipos em /dadosabertos/materia/tiposPrazo |
| `comissao` | query | não | string | CAE | Sigla da comissão |
| `tipo` | query | não | string | PL | Sigla da identificação |
| `v` | query | não | integer (int32) | 6 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/materia/lista/tramitacao`

**Total de Processos em tramitação no Senado Federal ou no Congresso Nacional por Tipo ou pelo Colegiado em que se encontra (Plenário ou Comissão)**

`operationId`: `listaMateriasEmTramitacao`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `sigla` | query | não | string | PL | Sigla do Subtipo de Proposição (Matéria) |
| `ano` | query | não | string | 2023 | Ano da Proposição |
| `comissao` | query | não | string | CCJ | Sigla da Comissão |
| `v` | query | não | integer (int32) | 2 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/materia/locais`

**(DEPRECATED) Lista os Entes Jurídicos possíveis de localização de Matérias Legislativas**

Substitua pelo serviço em [/dadosabertos/processo/entes](#/Processo/entesJuridicos)

`operationId`: `locais` — **DEPRECADO**

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/materia/movimentacoes/{codigo}`

**(DEPRECATED) Movimentação da Matéria, incluindo tramitação, prazos, despachos, situação etc.**

Substitua pelo serviço de detalhes do processo em [/dadosabertos/processo/{idProcesso}](#/Processo/detalhesProcesso)

`operationId`: `movimentacoes` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 95997 | Código da Matéria |
| `dataref` | query | não | string | 20120210 | Formato AAAAMMDD - Filtra ocorrências a partir da data especificada |
| `v` | query | não | integer (int32) | 7 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`, `*/*`

### GET `/dadosabertos/materia/ordia/{codigo}`

**(DEPRECATED) Sessões em que a Matéria foi pautada na Ordem do Dia**

Substitua pelo serviço de detalhes do processo em [/dadosabertos/processo/{idProcesso}](#/Processo/detalhesProcesso)

`operationId`: `ordia` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 116682 | Código da Matéria |
| `v` | query | não | integer (int32) | 4 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`, `*/*`

### GET `/dadosabertos/materia/pesquisa/lista`

**(DEPRECATED) Pesquisa básica de matérias**

Substitua pelo serviço de lista de processos disponível em [/dadosabertos/processo](#/Processo/processos)

Retorna as matérias que satisfazem aos parâmetros informados.

Atenção:
1. Se não informar o ano (da matéria ou da norma) nem o período de apresentação, será considerado o ano atual.
1. Para a pesquisa por período de apresentação, o limite é de 1 ano.

`operationId`: `pesquisaMateria` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `tramitando` | query | não | string | S | Indica se a matéria está tramitando (S) ou não (N) |
| `sigla` | query | não | string | MPV | Sigla do subtipo da matéria |
| `numero` | query | não | string |  | Número da matéria |
| `ano` | query | não | integer (int32) |  | Ano da matéria |
| `siglaComissaoReq` | query | não | string |  | Sigla da comissão do requerimento - para requerimentos de comissão após 2019 (REQ) |
| `nomeAutor` | query | não | string |  | Nome do autor da matéria |
| `dataInicioApresentacao` | query | não | string (date) |  | Data de início para pesquisa da data de apresentação da matéria, no formato AAAAMMDD |
| `dataFimApresentacao` | query | não | string (date) |  | Data de fim para pesquisa da data de apresentação da matéria, no formato AAAAMMDD |
| `codigoClasse` | query | não | integer (int64) |  | Código de classificação da matéria - veja lista de tipos em /dadosabertos/materia/classes |
| `codigoConteudo` | query | não | integer (int64) |  | Código do tipo de conteúdo da matéria - veja lista de tipos em /dadosabertos/materia/tiposNatureza |
| `tipoNorma` | query | não | string |  | Sigla do tipo da norma jurídica gerada |
| `numeroNorma` | query | não | string |  | Número da norma jurídica gerada |
| `anoNorma` | query | não | integer (int32) |  | Ano da norma jurídica gerada |
| `palavraChave` | query | não | string |  | Palavra chave para pesquisa no conteúdo e indexação da matéria |
| `v` | query | não | integer (int32) | 7 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`, `*/*`

### GET `/dadosabertos/materia/relatorias/{codigo}`

**(DEPRECATED) Relatorias da Matéria**

Substitua pelo serviço em [/dadosabertos/processo/relatoria](#/Processo/relatorias)

`operationId`: `relatorias_1` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 131506 | Código da Matéria |
| `v` | query | não | integer (int32) | 5 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`, `*/*`

### GET `/dadosabertos/materia/situacaoatual/tramitacao/{data}`

**(DEPRECATED) Situação atual e Localização das Matérias que tramitaram na Data informada**

Substitua pelos serviços de listagem e detalhes de processo - [/dadosabertos/processo](#/Processo/processos) e [/dadosabertos/processo/{idProcesso}](#/Processo/detalhesProcesso)

`operationId`: `situacaoatual_1` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `data` | path | sim | string | 20140410 | Data da Tramitação - formato AAAAMMDD |
| `v` | query | não | integer (int32) | 3 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`, `*/*`

### GET `/dadosabertos/materia/situacaoatual/{codigo}`

**(DEPRECATED) Situação e Localização atuais da Matéria**

Substitua pelo serviço de detalhes do processo em [/dadosabertos/processo/{idProcesso}](#/Processo/detalhesProcesso)

`operationId`: `situacaoatual` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 80406 | Código da Matéria |
| `v` | query | não | integer (int32) | 3 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`, `*/*`

### GET `/dadosabertos/materia/situacoes`

**(DEPRECATED) Situações possíveis de Matérias Legislativas**

Substitua pelo serviço disponível em [/dadosabertos/processo/tipos-situacao](#/Processo/tiposSituacao)

`operationId`: `situacoes` — **DEPRECADO**

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/materia/subtipos`

**(DEPRECATED) Subtipos e Siglas de Matérias Legislativas**

Substitua pelo serviço disponível em [/dadosabertos/processo/siglas](#/Processo/siglasIdentificacao)

`operationId`: `subtipos` — **DEPRECADO**

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/materia/textos/{codigo}`

**(DEPRECATED) Documentos apresentados na Matéria**

Substitua pelo serviço disponível em [/dadosabertos/processo/documento](#/Processo/documentosProcesso)

`operationId`: `textos` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 110428 | Código da Matéria |
| `v` | query | não | integer (int32) | 5 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`, `*/*`

### GET `/dadosabertos/materia/tiposEmenda`

**(DEPRECATED) Tipos de Emendas**

`operationId`: `tiposEmenda` — **DEPRECADO**

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/materia/tiposNatureza`

**(DEPRECATED) Tipos de Natureza das Matérias**

Substitua pelo serviço disponível em [/dadosabertos/processo/documento/tipos-conteudo](#/Processo/tiposConteudoDocumento)

`operationId`: `tiposNatureza` — **DEPRECADO**

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/materia/tiposPrazo`

**(DEPRECATED) Tipos de Prazos os quais Matérias Legislativas podem estar sujeitos**

Substitua pelo serviço disponível em [/dadosabertos/processo/prazo/tipos](#/Processo/tiposPrazo)

`operationId`: `tiposPrazos` — **DEPRECADO**

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/materia/tiposTurnoApresentacao`

**(DEPRECATED) Tipos de Turno de Apresentação de Matérias no Processo Legislativo**

`operationId`: `tiposTurnoApresentacao` — **DEPRECADO**

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/materia/tiposatualizacoes`

**(DEPRECATED) Tipos de Atualização que podem ocorrer em Matérias Legislativas**

Substitua pelo serviço disponível em [/dadosabertos/processo/tipos-atualizacao](#/Processo/tiposAtualizacao)

`operationId`: `tiposatualizacoes` — **DEPRECADO**

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/materia/tramitando`

**(DEPRECATED) Lista as Matérias que estão tramitando**

Substitua pelo serviço de listagem de processos em [/dadosabertos/processo](#/Processo/processos)

`operationId`: `tramitando` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `data` | query | não | string | 20190701 | Filtra as matérias cuja última atualização é igual ou posterior à data informada - formato AAAAMMDD |
| `hora` | query | não | string | 140000 | Filtra apenas as matérias cuja hora da última atualização é igual ou posterior à hora informada. Deve ser informado apenas se a data também for informada. Formato HHMISS, onde HH é no padrão 24 horas, MI representa os minutos, com 2 dígitos, e SS representa os segundos, com 2 dígitos |
| `sigla` | query | não | string |  | Sigla do subtipo da matéria |
| `numero` | query | não | string |  | Número da matéria |
| `ano` | query | não | integer (int32) |  | Ano da matéria |
| `v` | query | não | integer (int32) | 4 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`, `*/*`

### GET `/dadosabertos/materia/vetos/antesrcn`

**Vetos anteriores à RCN 1/2013 em tramitação**

`operationId`: `vetosAntesRcn`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/materia/vetos/aposrcn`

**Vetos posteriores à RCN 1/2013 em tramitação**

`operationId`: `vetosAposRcn`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/materia/vetos/encerrados`

**Vetos com tramitação encerrada**

`operationId`: `vetosEncerrados`

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/materia/vetos/{ano}`

**Relação de Vetos presidenciais por ano**

`operationId`: `vetosPorAno`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `ano` | path | sim | integer (int32) | 2023 | Ano do Veto |

- **default** Redirecionamento (status code 307) para o arquivo XML, JSON ou CSV da lista — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/materia/votacoes/{codigo}`

**(DEPRECATED) Votações de uma Matéria**

Substitua pelo serviço de listagem de votos disponível em [/dadosabertos/votacao](#/Votação/votacoes)

`operationId`: `votacoes_1` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 137178 | Código da Matéria |
| `v` | query | não | integer (int32) | 6 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`, `*/*`

### GET `/dadosabertos/materia/{codigo}`

**(DEPRECATED) Detalhes da Matéria por código**

Substitua pelo serviço de detalhes do processo em [/dadosabertos/processo/{idProcesso}](#/Processo/detalhesProcesso)

`operationId`: `detalhes_1` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 110428 | Código da Matéria |
| `v` | query | não | integer (int32) | 7 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`, `*/*`

### GET `/dadosabertos/materia/{sigla}/{numero}/{ano}`

**(DEPRECATED) Detalhes da Matéria por Sigla, Número, Ano e Comissão**

Substitua pelos serviços de listagem e detalhes de processo - [/dadosabertos/processo](#/Processo/processos) e [/dadosabertos/processo/{idProcesso}](#/Processo/detalhesProcesso)

`operationId`: `detalhes` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `sigla` | path | sim | string | REQ | Sigla do Tipo da Proposição |
| `numero` | path | sim | string | 1 | Número da Proposição |
| `ano` | path | sim | integer (int32) | 2019 | Ano da Proposição |
| `comissao` | query | não | string | CCJ | Sigla da Comissão (somente para requerimentos de Comissão - sigla REQ) |
| `v` | query | não | integer (int32) | 7 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`, `*/*`

### GET `/dadosabertos/processo`

**Lista Processos Legislativos**

Processos Legislativos que tramitam ou já tramitaram no Senado Federal ou Congresso Nacional.
É obrigatório informar pelo menos um dos seguintes parâmetros:
 * numero
 * ano
 * idProcesso
 * codigoMateria
 * tramitando (com valor S - default se nenhum outro parâmetro obrigatório for informado)
 * tramitouLegislaturaAtual (com valor S)
 * codigoParlamentarAutor
 * codigoClasse
 * codigoAssuntoEspecifico
 * sigla + siglaEnteIdentificador
 * dataInicioApresentacao
 * dataFimApresentacao
 * dataInicioDeliberacao
 * dataFimDeliberacao
 * numeroNorma
 * anoNorma
 * numdias

 Caso nenhum desses parâmetros seja informado, retornará somente Processos que atualmente estão em
tramitação (tramitando=S).

`operationId`: `processos`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `sigla` | query | não | array<string> |  | Sigla identificadora do processo - veja a lista de siglas em /processo/siglas |
| `numero` | query | não | string |  | Número do processo |
| `ano` | query | não | integer (int32) |  | Ano do processo |
| `idProcesso` | query | não | array<integer (int64)> |  | Id do processo |
| `codigoMateria` | query | não | integer (int64) |  | Código legado da matéria do MATE |
| `tramitando` | query | não | string enum(N, S) |  | Processo está tramitando atualmente? S - Sim, N - Não (Encerrado) |
| `tramitouLegislaturaAtual` | query | não | string enum(N, S) |  | Processo tramitou na legislatura atual? S - Sim, N - Não |
| `codigoColegiadoTramitando` | query | não | integer (int64) |  | Código do colegiado onde o processo tramita atualmente - veja a lista de colegiados em /comissao/lista |
| `siglaSituacao` | query | não | string |  | Sigla da situação atual do processo - veja a lista de situações em /processo/tipos-situacao |
| `situacao` | query | não | string |  | Situação atual do processo (descrição) - veja a lista de situações em /processo/tipos-situacao |
| `autor` | query | não | string |  | Nome do autor do processo |
| `codigoParlamentarAutor` | query | não | integer (int64) |  | Código do parlamentar autor |
| `siglaTipoDocumento` | query | não | array<string> |  | Sigla do tipo do documento iniciador do processo - veja a lista de tipos em /processo/documento/tipos |
| `siglaTipoConteudo` | query | não | array<string> |  | Sigla do tipo de conteúdo do documento iniciador do processo - veja a lista de tipos em /processo/documento/tipos-conteudo |
| `codigoClasse` | query | não | integer (int64) |  | Código da classe do processo. Veja a lista de classes em /processo/classes |
| `codAssuntoGeral` | query | não | integer (int64) |  | Código do assunto geral - veja a lista de tipos em /processo/assuntos |
| `codAssuntoEspecifico` | query | não | integer (int64) |  | Código do assunto específico - veja a lista de tipos em /processo/assuntos |
| `termo` | query | não | string |  | Termo livre a ser consultado entre as palavras-chaves do processo |
| `casa` | query | não | string |  | Casa do ente/comissão/colegiado identificador do processo ('SF', 'CN') |
| `siglaEnteIdentificador` | query | não | string |  | Sigla do ente/comissão/colegiado identificador do processo - veja a lista de entes em /processo/entes |
| `dataInicioApresentacao` | query | não | string (date) |  | Apresentados a partir da data informada, no formato AAAA-MM-DD. Retorna até no máximo 1 ano após a     data informada se nenhum outro parâmetro obrigatório for informado |
| `dataFimApresentacao` | query | não | string (date) |  | Apresentados até a data informada, no formato AAAA-MM-DD. Retorna até no máximo 1 ano antes da data     informada se nenhum outro parâmetro obrigatório for informado. |
| `dataInicioDeliberacao` | query | não | string (date) |  | Deliberados a partir da data informada, no formato AAAA-MM-DD. Retorna até no máximo 1 ano após a     data informada se nenhum outro parâmetro obrigatório for informado |
| `dataFimDeliberacao` | query | não | string (date) |  | Deliberados até a data informada, no formato AAAA-MM-DD. Retorna até no máximo 1 ano antes da data     informada se nenhum outro parâmetro obrigatório for informado. |
| `siglaTipoDeliberacao` | query | não | string |  | Sigla do tipo de deliberação - veja a lista de tipos em /processo/tipos-decisao |
| `tipoNorma` | query | não | string |  | Tipo da norma gerada - veja a lista de tipos em /legislacao/tiposNorma |
| `numeroNorma` | query | não | string |  | Número da norma gerada |
| `anoNorma` | query | não | integer (int32) |  | Ano da norma gerada |
| `numdias` | query | não | integer (int32) |  | Atualizadas nos últimos N dias. O máximo é 30. |
| `alteracao` | query | não | string |  | Tipo de atualização - veja a lista de tipos em /processo/tipos-atualizacao. Considerado apenas quando numdias é informado. |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/json`, `application/x-ndjson`, `application/xml`, `text/csv`

### GET `/dadosabertos/processo/assuntos`

**Lista os Assuntos Gerais e Específicos de que tratam os Processos Legislativos**

`operationId`: `assuntosProcesso`

- **200** OK — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/processo/classes`

**Lista a Hierarquia de Classificações de Processos Legislativos**

`operationId`: `classesProcesso`

- **200** OK — `application/json`, `application/xml`

### GET `/dadosabertos/processo/destinos`

**Lista os Destinos possíveis de Processos Legislativos**

`operationId`: `destinosProcesso`

- **200** OK — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/processo/documento`

**Documentos apresentados no Processo Legislativo**

Lista os Documentos apresentados em Processos Legislativos.
É obrigatório informar pelo menos um dos seguintes parâmetros:
 * idDocumento
 * idProcesso
 * codigoMateria
 * dataInicio + dataFim (intervalo deve ser de até 6 meses no máximo se nenhum outro parâmetro
   obrigatório for informado)
 * codigoParlamentarAutor
 * idEnteAutor
 * codigoColegiado + sigla
 * codigoColegiado + siglaTipo
 * siglaColegiado + sigla
 * siglaColegiado + siglaTipo

Caso nenhum desses parâmetros for informado, retornará somente documentos apresentados em um dos
seguintes intervalos de 6 meses:
 * HOJE - 6 meses, se dataInicio e dataFim não forem informadas
 * dataFim - 6 meses, se dataInicio não for informada
 * dataInicio + 6 meses, se dataFim não for informada

`operationId`: `documentosProcesso`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `idDocumento` | query | não | integer (int64) |  | Id do documento |
| `idProcesso` | query | não | integer (int64) |  | Id do processo no qual o documento foi apresentado |
| `codigoMateria` | query | não | integer (int64) |  | Código legado da matéria do MATE |
| `dataInicio` | query | não | string (date) |  | Documentos apresentados a partir desta data, no formato AAAA-MM-DD |
| `dataFim` | query | não | string (date) |  | Documentos apresentados até esta data, no formato AAAA-MM-DD |
| `codigoParlamentarAutor` | query | não | integer (int64) | 825 | Código do parlamentar autor do documento |
| `idEnteAutor` | query | não | integer (int64) |  | Id do ente autor |
| `codigoColegiado` | query | não | integer (int64) | 34 | Código do colegiado no qual o documento foi apresentado |
| `siglaColegiado` | query | não | string |  | Sigla do colegiado no qual o documento foi apresentado |
| `sigla` | query | não | string |  | Sigla da identificação do documento |
| `siglaTipo` | query | não | string | REQUERIMENTO | Sigla do tipo de documento |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/json`, `application/x-ndjson`, `application/xml`

### GET `/dadosabertos/processo/documento/tipos`

**Lista os Tipos de Documentos que podem ser apresentados em Processos Legislativos**

`operationId`: `tiposDocumento`

- **200** OK — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/processo/documento/tipos-conteudo`

**Lista os Tipos de Conteúdo Informacional que os Documentos Legislativos podem conter**

`operationId`: `tiposConteudoDocumento`

- **200** OK — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/processo/emenda`

**Lista as Emendas apresentadas em um Processo Legislativo**

Lista as Emendas apresentadas à Proposição.
É obrigatório informar pelo menos um dos parâmetros.
Caso nenhum dos parâmetros for informado, retornará somente documentos apresentados
em um dos seguintes intervalos de 1 ano:
 * HOJE - 1 ano, se dataInicio e dataFim não forem informadas
 * dataFim - 1 ano, se dataInicio não for informada
 * dataInicio + 1 ano, se dataFim não for informada

`operationId`: `emendasProcesso`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `idEmenda` | query | não | integer (int64) |  | Id da emenda |
| `idDocumento` | query | não | integer (int64) |  | Id do documento da emenda |
| `idProcesso` | query | não | integer (int64) |  | Id do processo emendado |
| `codigoMateria` | query | não | integer (int64) |  | Código legado da matéria emendada do MATE |
| `dataInicio` | query | não | string (date) |  | Emendas apresentadas a partir desta data, no formato AAAA-MM-DD |
| `dataFim` | query | não | string (date) |  | Emendas apresentadas até esta data, no formato AAAA-MM-DD |
| `codigoParlamentarAutor` | query | não | integer (int64) | 5979 | Código do parlamentar autor da emenda |
| `codigoColegiado` | query | não | integer (int64) | 40 | Código do colegiado no qual a emenda foi apresentada |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/json`, `application/x-ndjson`, `application/xml`, `text/csv`

### GET `/dadosabertos/processo/entes`

**Lista os Entes Jurídicos que podem participar como autores ou instâncias de tramitação ou de expedição de Documentos e Processos**

`operationId`: `entesJuridicos`

- **200** OK — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/processo/prazo`

**Lista os Prazos Regimentais ou Constitucionais definidos no rito de tramitação de um Processo Legislativo**

Lista os prazos estabelecidos para processos legislativos.
É obrigatório informar pelo menos um dos seguintes parâmetros:
 * idProcesso
 * codigoMateria
 * dataReferencia (filtro padrão com data atual se nenhum dos outros parâmetros obrigatórios for
   informado)
 * dataInicio + dataFim (intervalo deve ser de até 1 ano no máximo se nenhum outro parâmetro
   obrigatório for informado)

Caso nenhum desses parâmetros for informado, retornará somente Prazos atualmente
vigentes (dataReferencia=HOJE).

`operationId`: `prazos`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `idProcesso` | query | não | integer (int64) | 1158177 | Id do Processo sobre o qual o prazo foi estabelecido |
| `codigoMateria` | query | não | integer (int64) |  | Código legado da Matéria |
| `idTipoPrazo` | query | não | integer (int64) |  | Id do Tipo de Prazo |
| `dataReferencia` | query | não | string (date) |  | Prazos vigentes nesta data, no formato AAAA-MM-DD |
| `dataInicio` | query | não | string (date) |  | Prazos iniciados a partir desta data, no formato AAAA-MM-DD |
| `dataFim` | query | não | string (date) |  | Prazos iniciados até esta data, no formato AAAA-MM-DD |
| `codigoColegiado` | query | não | integer (int64) | 34 | Código do Colegiado no qual o Prazo foi determinado |
| `sigla` | query | não | string | PEC | Sigla da Identificação do Processo |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/json`, `application/x-ndjson`, `application/xml`, `text/csv`

### GET `/dadosabertos/processo/prazo/tipos`

**Tipos de Prazos de Processos Legislativos**

Lista os Tipos de Prazos aos quais os Processos podem estar sujeitos

`operationId`: `tiposPrazo`

- **200** OK — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/processo/relatoria`

**Relatorias de Processos Legislativos**

Lista os Relatores designados para Processos Legislativos nas Comissões ou Plenário.
É obrigatório informar pelo menos um dos seguintes parâmetros:
 * idProcesso
 * codigoMateria
 * codigoParlamentar
 * dataReferencia (filtro padrão com data atual se nenhum dos outros parâmetros obrigatórios for
   informado)
 * dataInicio + dataFim (intervalo deve ser de até 1 ano no máximo se nenhum outro parâmetro
   obrigatório for informado)

Caso nenhum desses parâmetros for informado, retornará somente Relatorias atualmente
abertas (dataReferencia=HOJE).

`operationId`: `relatorias`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `idProcesso` | query | não | integer (int64) | 8774796 | Id do processo relatado |
| `codigoMateria` | query | não | integer (int64) |  | Código legado da matéria do MATE |
| `sigla` | query | não | string |  | Sigla identificadora do processo - veja a lista de siglas em /processo/siglas |
| `numero` | query | não | string |  | Número do processo |
| `ano` | query | não | integer (int32) |  | Ano do processo |
| `siglaSituacao` | query | não | string |  | Sigla da situação atual do processo - veja a lista de situações em /processo/tipos-situacao |
| `tramitando` | query | não | string |  | Processo está tramitando atualmente? S - Sim, N - Não (Encerrado) |
| `dataReferencia` | query | não | string (date) |  | Relatorias abertas nesta data, no formato AAAA-MM-DD |
| `dataInicio` | query | não | string (date) |  | Relatorias designadas a partir desta data, no formato AAAA-MM-DD |
| `dataFim` | query | não | string (date) |  | Relatorias designadas até esta data, no formato AAAA-MM-DD |
| `codigoParlamentar` | query | não | integer (int64) | 6009 | Código do parlamentar relator |
| `codigoColegiado` | query | não | integer (int64) | 34 | Código do colegiado da relatoria |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/json`, `application/x-ndjson`, `application/xml`, `text/csv`

### GET `/dadosabertos/processo/siglas`

**Tipos e Siglas de Documentos e Processos Legislativos**

`operationId`: `siglasIdentificacao`

- **200** OK — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/processo/tipos-atualizacao`

**Tipos de Atualização que podem ocorrer em Processos Legislativos**

`operationId`: `tiposAtualizacao`

- **200** OK — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/processo/tipos-autor`

**Tipos de Autores de Documentos e Processos Legislativos**

`operationId`: `tiposAutor`

- **200** OK — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/processo/tipos-decisao`

**Tipos de Decisões que podem ocorrer em Processos Legislativos**

`operationId`: `tiposDecisao`

- **200** OK — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/processo/tipos-situacao`

**Tipos de Situações (estado) possíveis em Processos Legislativos**

`operationId`: `tiposSituacao`

- **200** OK — `application/json`, `application/xml`, `text/csv`

### GET `/dadosabertos/processo/{id}`

**Detalhes de um Processo Legislativo por código do Processo**

Detalhes de um Processo Legislativo, como identificação, ementa, explicação da ementa,
indexação, autoria, data de apresentação, data de leitura, classificação, assunto,
outros números, materias anexadas, materias relacionadas, decisão, destino,
norma gerada, entre outros.

`operationId`: `detalhesProcesso`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `id` | path | sim | integer (int64) | 1449240 | ID do Processo |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/json`, `application/xml`

### GET `/dadosabertos/senador/{codigo}/autorias`

**(DEPRECATED) Lista as matérias de Autoria de um Senador**

Substitua pelo serviço de listagem de processos em [/dadosabertos/processo](#/Processo/processos)

`operationId`: `autoriaSenador` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int32) | 4981 | Código do Senador |
| `sigla` | query | não | string | PLS | Filtra autoria pela sigla da matéria |
| `numero` | query | não | string | 40 | Filtra autoria pelo número da matéria |
| `ano` | query | não | integer (int32) | 2018 | Filtra autoria pelo ano da matéria |
| `tramitando` | query | não | string | S | Filtra autoria de matérias que estão tramitando (S) ou com tramitação encerrada (N) |
| `primeiro` | query | não | string | S | Filtra autorias onde o Senador é o primeiro autor (S) ou que seja coautor (N) |
| `v` | query | não | integer (int32) | 7 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/senador/{codigo}/relatorias`

**(DEPRECATED) Obtém as matérias de Relatoria de um Senador**

Substitua pelo serviço disponível em [/dadosabertos/processo/relatoria](#/Processo/relatorias)

`operationId`: `relatoriaSenador` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 5322 | Código do Senador |
| `sigla` | query | não | string | PLS | Filtra relatoria pela sigla da matéria |
| `numero` | query | não | string | 40 | Filtra relatoria pelo número da matéria |
| `ano` | query | não | integer (int32) | 2018 | Filtra relatoria pelo ano da matéria |
| `tramitando` | query | não | string | S | Filtra relatoria de matérias que estão tramitando (S) ou com tramitação encerrada (N) |
| `comissao` | query | não | string | CDH | Filtra relatoria na Comissão pela sigla |
| `v` | query | não | integer (int32) | 6 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

## Votação

### GET `/dadosabertos/senador/{codigo}/votacoes`

**(DEPRECATED) Obtém as Votações Nominais de um Senador**

Substitua pelo serviço de listagem de votos disponível em [/dadosabertos/votacao](#/Votação/votacoes)

`operationId`: `votacaoSenador` — **DEPRECADO**

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int64) | 5322 | Código do Senador |
| `sigla` | query | não | string | PEC | Filtra votações pela sigla da matéria |
| `numero` | query | não | string | 40 | Filtra votações pelo número da matéria |
| `ano` | query | não | integer (int32) | 2022 | Filtra votações pelo ano da matéria |
| `tramitando` | query | não | string | S | Filtra votações de matérias que estão tramitando (S) ou com tramitação encerrada (N) |
| `v` | query | não | integer (int32) | 7 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/votacao`

**Votos Nominais de Parlamentares em Processos Legislativos**

Permite filtrar pela Sessão, Proposição, Parlamentar e Voto.
A lista de votos individualizados é apenas para votações nominais. Para as votações secretas são apresentados apenas os totais.
É obrigatório informar pelo menos um dos seguintes parâmetros:
 * codigoSessao
 * idProcesso
 * codigoMateria
 * numero
 * ano
 * codigoParlamentar
 * dataInicio + dataFim (intervalo deve ser de até 1 ano no máximo se nenhum outro parâmetro
   obrigatório for informado)

Caso nenhum desses parâmetros for informado, retornará somente as votações dos últimos 12
meses (dataFim=HOJE).

`operationId`: `votacoes`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigoSessao` | query | não | integer (int64) |  | Código da sessão da votação |
| `dataInicio` | query | não | string (date) |  | Votações realizadas a partir desta data, no formato AAAA-MM-DD |
| `dataFim` | query | não | string (date) |  | Votações realizadas até esta data, no formato AAAA-MM-DD |
| `idProcesso` | query | não | integer (int64) | 7761651 | ID do processo votado |
| `codigoMateria` | query | não | integer (int64) |  | Código legado da matéria do MATE |
| `sigla` | query | não | string |  | Sigla da proposição |
| `numero` | query | não | string |  | Número da proposição |
| `ano` | query | não | integer (int32) |  | Ano da proposição |
| `codigoParlamentar` | query | não | integer (int64) | 825 | Código do parlamentar votante |
| `nomeParlamentar` | query | não | string |  | Nome do parlamentar votante |
| `siglaVotoParlamentar` | query | não | string | Sim | Sigla do voto |
| `v` | query | não | integer (int32) | 2 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/json`, `application/x-ndjson`, `application/xml`, `text/csv`

### GET `/dadosabertos/votacaoComissao/comissao/{siglaComissao}`

**Votações de Matérias nas Comissões do Senado Federal e Congresso Nacional**

`operationId`: `votacaoPorComissao`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `siglaComissao` | path | sim | string | CCJ | Sigla da Comissão |
| `dataInicio` | query | não | string |  | Data de início para pesquisa no formato AAAAMMDD |
| `dataFim` | query | não | string |  | Data de fim para pesquisa no formato AAAAMMDD |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/votacaoComissao/materia/{sigla}/{numero}/{ano}`

**Votações de Matérias nas Comissões por Identificação da Matéria**

`operationId`: `votacaoPorProposicao`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `sigla` | path | sim | string | PLS | Sigla do Tipo da Proposição |
| `numero` | path | sim | string | 171 | Número da Proposição |
| `ano` | path | sim | integer (int32) | 2012 | Ano da Proposição |
| `comissao` | query | não | string |  | Sigla da Comissão |
| `dataInicio` | query | não | string |  | Data de início para pesquisa no formato AAAAMMDD |
| `dataFim` | query | não | string |  | Data de fim para pesquisa no formato AAAAMMDD |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

### GET `/dadosabertos/votacaoComissao/parlamentar/{codigo}`

**Votações nas Comissões por Parlamentar**

`operationId`: `votacaoPorParlamentar`

| Parâmetro | Em | Obrig. | Tipo | Exemplo | Descrição |
|---|---|---|---|---|---|
| `codigo` | path | sim | integer (int32) | 4988 | Código do Parlamentar |
| `comissao` | query | não | string | CRE | Sigla da Comissão |
| `dataInicio` | query | não | string |  | Data de início para pesquisa no formato AAAAMMDD |
| `dataFim` | query | não | string |  | Data de fim para pesquisa no formato AAAAMMDD |
| `v` | query | não | integer (int32) | 1 | Versão do serviço. Exemplificada a última disponível. |

- **200** OK — `application/xml`, `application/json`, `text/csv`

## Schemas

### ApresentacaoNoProcessoDto

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | integer (int64) | Id do processo |
| `identificacao` | string | Identificação do processo |
| `tramitando` | string | Status de tramitação do processo |
| `papelNoProcesso` | string | Papel do documento no processo |

### AutorDto

| Campo | Tipo | Descrição |
|---|---|---|
| `autor` | string | Autor do documento |
| `sexo` | string | Sexo do autor |
| `siglaTipo` | string | Sigla do tipo de autor |
| `descricaoTipo` | string | Descrição do tipo de autor |
| `ordem` | integer (int32) | Ordem do autor |
| `outrosAutoresNaoInformados` | string | Outros autores não informados |
| `codigoParlamentar` | integer (int64) | Código do parlamentar |
| `uf` | string | UF do autor |
| `siglaPartido` | string | Sigla do partido do autor |
| `partido` | string | Partido do autor |
| `siglaCargo` | string | Sigla do cargo do autor |
| `cargo` | string | Cargo do autor |
| `idEnte` | integer (int64) | ID do ente do autor |
| `siglaEnte` | string | Sigla do ente do autor |
| `casaEnte` | string | Casa do ente do autor |
| `nomeEnte` | string | Nome do ente do autor |

### DataBuffer

Tipo: 

### DecisaoDto

| Campo | Tipo | Descrição |
|---|---|---|
| `data` | string | Data da decisão |
| `idTipo` | integer (int64) | Id do tipo da decisão |
| `descricaoTipo` | string | Descrição do tipo da decisão |
| `codigoColegiado` | integer (int64) | Código do colegiado |
| `casa` | string | Sigla da casa legislativa |
| `siglaColegiado` | string | Sigla do colegiado |
| `nomeColegiado` | string | Nome do colegiado |

### InformeLegislativoDto

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | integer (int64) | ID do informe |
| `idEvento` | integer (int64) | ID do evento |
| `numeroAutuacao` | integer (int32) | Número de autuação |
| `data` | string | Data do informe |
| `texto` | string | Texto do informe |
| `codigoColegiado` | integer (int64) | Código do colegiado do informe |
| `casaColegiado` | string | Casa do colegiado do informe |
| `siglaColegiado` | string | Sigla do colegiado do informe |
| `nomeColegiado` | string | Nome do colegiado do informe |
| `idEnteAdm` | integer (int64) | ID do ente administrativo do informe |
| `casaEnteAdm` | string | Casa do ente administrativo do informe |
| `siglaEnteAdm` | string | Sigla do ente administrativo do informe |
| `nomeEnteAdm` | string | Nome do ente administrativo do informe |

### ObservacaoDto

| Campo | Tipo | Descrição |
|---|---|---|
| `codigo` | integer (int64) | Código da observação |
| `observacao` | string | Observação |

### VotoDto

| Campo | Tipo | Descrição |
|---|---|---|
| `codigoParlamentar` | integer (int64) | Código do parlamentar |
| `nomeParlamentar` | string | Nome do parlamentar |
| `sexoParlamentar` | string | Sexo do parlamentar |
| `siglaPartidoParlamentar` | string | Sigla do partido do parlamentar |
| `siglaUFParlamentar` | string | Sigla da UF do parlamentar |
| `siglaVotoParlamentar` | string | Sigla do voto do parlamentar |
| `descricaoVotoParlamentar` | string | Descrição do voto do parlamentar |

### documento

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | integer (int64) | Id do documento |
| `identificacao` | string | Identificação do documento |
| `dataDocumento` | string | Data do documento |
| `dataRecebimento` | string | Data de recebimento do documento no legislativo |
| `siglaTipo` | string | Sigla do tipo de documento |
| `descricaoTipo` | string | Descrição do tipo de documento |
| `autoria` | string | Autoria do documento |
| `descricao` | string | Descrição do documento |
| `urlDocumento` | string | URL do documento |
| `codigoColegiadoRecebedor` | integer (int32) | Código do colegiado recebedor |
| `casaRecebedora` | string | Casa do colegiado recebedor |
| `siglaColegiadoRecebedor` | string | Sigla do colegiado recebedor |
| `nomeColegiadoRecebedor` | string | Nome do colegiado recebedor |
| `idEnteRecebedor` | integer (int64) | ID do ente recebedor |
| `casaEnteRecebedor` | string | Casa do ente recebedor |
| `siglaEnteRecebedor` | string | Sigla do ente recebedor |
| `nomeEnteRecebedor` | string | Nome do ente recebedor |
| `autores` | array<AutorDto> | Autores do documento |
| `apresentadoNosProcessos` | array<ApresentacaoNoProcessoDto> | Processos nos quais o documento foi apresentado |

### emenda

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | integer (int64) | Id da emenda |
| `idDocumentoEmenda` | integer (int64) | Id do documento da emenda |
| `urlDocumentoEmenda` | string | URL do documento da emenda |
| `descricaoDocumentoEmenda` | string | Descrição do documento da emenda |
| `idCiEmenda` | integer (int64) | Id do conteúdo informacional da emenda |
| `idCiEmendado` | integer (int64) | Id do conteúdo informacional emendado |
| `idProcesso` | integer (int64) | Id do processo emendado |
| `dataApresentacao` | string | Data de apresentação da emenda |
| `codigoColegiado` | integer (int64) | Código do colegiado de apresentação da emenda |
| `casa` | string | Casa legislativa de apresentação da emenda |
| `siglaColegiado` | string | Sigla do colegiado de apresentação da emenda |
| `nomeColegiado` | string | Nome do colegiado de apresentação da emenda |
| `autoria` | string | Autoria da emenda |
| `numero` | string | Número da emenda |
| `identificacao` | string | Identificação da emenda |
| `tipo` | string enum(EMENDA_PARCIAL, EMENDA_TOTAL, SUBEMENDA) | Tipo da emenda |
| `turnoApresentacao` | string enum(NORMAL, PRIMEIRO, SEGUNDO, SUPLEMENTAR) | Turno de apresentação da emenda |
| `decisoes` | array<DecisaoDto> | Decisões tomadas sobre a emenda |
| `subemendas` | array<emenda> | Subemendas da emenda |

### lideranca

| Campo | Tipo | Descrição |
|---|---|---|
| `codigo` | integer (int64) | Codigo da lideranca |
| `casa` | string | Casa legislativa (CN, CD ou SF) |
| `idTipoUnidadeLideranca` | integer (int32) | ID do tipo de unidade de liderança |
| `siglaTipoUnidadeLideranca` | string | Sigla do tipo de unidade de liderança |
| `descricaoTipoUnidadeLideranca` | string | Descrição do tipo de unidade de liderança |
| `codigoParlamentar` | integer (int64) | Código do parlamentar |
| `codigoDeputado` | integer (int64) | Código do deputado (sistema da Câmara) |
| `nomeParlamentar` | string | Nome do parlamentar |
| `dataDesignacao` | string (date) | Data de designação da liderança |
| `dataTermino` | string (date) | Data de término da liderança |
| `formaTratamentoParlamentar` | string | Forma de tratamento do parlamentar |
| `siglaTipoLideranca` | string | Sigla do tipo de liderança |
| `descricaoTipoLideranca` | string | Descrição do tipo de liderança |
| `numeroOrdemViceLider` | integer (int32) | Número de ordem do vice-líder |
| `codigoBloco` | integer (int64) | Código do bloco |
| `siglaBloco` | string | Sigla do bloco |
| `nomeBloco` | string | Nome do bloco |
| `codigoPartido` | integer (int64) | Código do partido |
| `siglaPartido` | string | Sigla do partido |
| `nomePartido` | string | Nome do partido |
| `codigoPartidoFiliacao` | integer (int64) | Código do partido de filiação |
| `siglaPartidoFiliacao` | string | Sigla do partido de filiação |
| `nomePartidoFiliacao` | string | Nome do partido de filiação |
| `uf` | string | UF do parlamentar |
| `observacoes` | array<ObservacaoDto> | Observações da liderança |

### prazo

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | integer (int64) | Id do prazo |
| `idProcesso` | integer (int64) | Id do processo |
| `idTipoPrazo` | integer (int64) | Id do tipo de prazo regulado |
| `tipoPrazo` | string | Tipo de prazo regulado |
| `fundamentoLegal` | string | Fundamento legal |
| `codigoColegiado` | integer (int64) | Código do colegiado |
| `siglaColegiado` | string | Sigla do colegiado |
| `nomeColegiado` | string | Nome do colegiado |
| `casa` | string | Casa do colegiado |
| `siglaTipoFase` | string | Sigla do tipo de fase |
| `descricaoTipoFase` | string | Descrição do tipo de fase |
| `prorrogado` | string | Indica se o prazo foi prorrogado |
| `inicioPrazo` | string | Data de início do prazo |
| `fimPrazo` | string | Data de fim do prazo |

### processo

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | integer (int64) | Id do processo |
| `codigoMateria` | integer (int64) | Código legado da matéria do MATE |
| `identificacao` | string | Identificação do processo |
| `apelido` | string | Apelido do processo |
| `objetivo` | string | Objetivo do processo |
| `casaIdentificadora` | string | Casa identificadora do processo |
| `enteIdentificador` | string | Ente identificador do processo |
| `tipoConteudo` | string | Tipo de conteúdo do processo |
| `ementa` | string | Ementa do processo |
| `idDocumento` | integer (int64) |  |
| `tipoDocumento` | string | Tipo de documento do processo |
| `dataApresentacao` | string (date) | Data de apresentação do processo |
| `idItemDigital` | integer (int64) |  |
| `autoria` | string | Autoria do processo |
| `tramitando` | string | Indica se o processo está tramitando |
| `situacaoAtual` | string | Situação atual da proposição |
| `dataSituacaoAtual` | string (date) | Data da situação atual do processo |
| `dataDeliberacao` | string (date) | Data de deliberação do processo |
| `siglaTipoDeliberacao` | string | Sigla do tipo de deliberação do processo. Veja a lista de tipos em /processo/tipos-decisao |
| `normaGerada` | string | Norma gerada pelo processo |
| `ultimaInformacaoAtualizada` | string | Última informação atualizada do processo |
| `dataUltimaAtualizacao` | string (date-time) | Data da última atualização do processo |
| `urlDocumento` | string | URL do documento inicial do processo |

### relatoria

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | integer (int64) | Id da relatoria |
| `casaRelator` | string | Casa do relator |
| `idTipoRelator` | integer (int64) | Id do tipo de relator |
| `descricaoTipoRelator` | string | Descrição do tipo de relator |
| `dataDesignacao` | string | Data de designação |
| `dataDestituicao` | string | Data de destituição |
| `descricaoTipoEncerramento` | string | Descrição do tipo de encerramento |
| `idProcesso` | integer (int64) | Id do processo |
| `numeroAutuacao` | string | Número de autuação |
| `codigoMateria` | integer (int64) | Código da matéria |
| `identificacaoProcesso` | string | Identificação do processo |
| `ementaProcesso` | string | Ementa do processo |
| `autoriaProcesso` | string | Autoria do processo |
| `dataApresentacaoProcesso` | string | Data de apresentação do processo |
| `tramitando` | string | Indica se o processo está tramitando |
| `codigoParlamentar` | integer (int64) | Código do parlamentar |
| `nomeParlamentar` | string | Nome do parlamentar |
| `nomeCompleto` | string | Nome completo do parlamentar |
| `sexoParlamentar` | string | Sexo do parlamentar |
| `formaTratamentoParlamentar` | string | Forma de tratamento do parlamentar |
| `urlFotoParlamentar` | string | URL da foto do parlamentar |
| `urlPaginaParlamentar` | string | URL da página do parlamentar |
| `emailParlamentar` | string | Email do parlamentar |
| `siglaPartidoParlamentar` | string | Sigla do partido do parlamentar |
| `ufParlamentar` | string | UF do parlamentar |
| `codigoColegiado` | integer (int64) | Código do colegiado |
| `siglaCasa` | string | Sigla da casa |
| `siglaColegiado` | string | Sigla do colegiado |
| `nomeColegiado` | string | Nome do colegiado |
| `codigoTipoColegiado` | integer (int64) | Código do tipo de colegiado |
| `dataFimColegiado` | string | Data de fim do colegiado |

### sessaoVotacao

| Campo | Tipo | Descrição |
|---|---|---|
| `codigoSessao` | integer (int64) | Código da sessão |
| `casaSessao` | string | Casa da sessão |
| `codigoSessaoLegislativa` | integer (int64) | Código da sessão legislativa |
| `siglaTipoSessao` | string | Sigla do tipo de sessão |
| `numeroSessao` | integer (int32) | Número da sessão |
| `dataSessao` | string | Data da sessão |
| `idProcesso` | integer (int64) | ID do processo |
| `codigoMateria` | integer (int64) | Código da matéria |
| `identificacao` | string | Identificação da proposição |
| `sigla` | string | Sigla da proposição |
| `numero` | string | Número da proposição |
| `ano` | integer (int32) | Ano da proposição |
| `dataApresentacao` | string | Data de apresentação |
| `ementa` | string | Ementa da proposição |
| `codigoSessaoVotacao` | integer (int64) | Código da sessão de votação |
| `sequencialVotacao` | integer (int64) | Sequencial da votação no SVE |
| `sequencialSessao` | integer (int32) | Sequencial da sessão |
| `votacaoSecreta` | string | Indica votação se a votação foi secreta (S ou N) |
| `descricaoVotacao` | string | Descrição da votação |
| `resultadoVotacao` | string | Resultado da votação |
| `totalVotosSim` | integer (int32) | Total de votos sim (votação secreta) |
| `totalVotosNao` | integer (int32) | Total de votos não (votação secreta) |
| `totalVotosAbstencao` | integer (int32) | Total de abstenções (votação secreta) |
| `informeLegislativo` | InformeLegislativoDto | Informe legislativo descrevendo o resultado da votação |
| `votos` | array<VotoDto> | Votos dos parlamentares (votação nominal) |

### unidade

| Campo | Tipo | Descrição |
|---|---|---|
| `codigo` | integer (int64) |  |
| `horaExibicao` | string |  |
| `dataUnidade` | string |  |
| `descricao` | string |  |
| `nomeOrador` | string |  |
| `descricaoOrador` | string |  |
| `duracaoVideo` | string |  |
| `duracaoAudio` | string |  |
| `enderecoThumbnail` | string |  |
| `enderecoVideo` | string |  |
| `enderecoAudio` | string |  |
