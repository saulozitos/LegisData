# ETL simples: baixar, gravar sem duplicar, registrar a data de corte

O cadastro e o legislativo entram no banco por **uma carga direta**: o Python lê o arquivo da fonte oficial, a transação despeja o
conteúdo numa tabela temporária, um arquivo SQL grava em `core` e `leg` com `INSERT ... ON CONFLICT` pela chave natural, e a
execução fica registrada em `etl.execucao`. Não existe staging persistente, tabela de trabalho nem função de fusão. Os dados são
regeneráveis: o banco pode ser refeito do zero a partir das fontes, e rodar a carga de novo não muda nenhuma contagem.

## O fluxo de cada recurso

1. **Extrair** (separado): o extrator baixa da API ou do arquivo em lote e grava em `etl/data` (cache de download).
2. **Ler o corte**: `etl.corte` diz até que data cada `(fonte, recurso)` já foi baixado. Os extratores incrementais
   (`--bulk-ano-inicio`, `--votacoes-ano-inicio`) partem do ano anterior ao do corte; sem corte, da janela de dados (1995).
3. **Carregar** (`etl.carga.base.rodar`): abre a execução (`etl.execucao`, estágio `CARREGAR`); numa transação própria, a
   primeira instrução é `leg.reservar_derivados()` (evita deadlock entre cargas), depois vêm o `COPY` para `_in_*` (tabelas
   temporárias da transação), o SQL do recurso e o avanço do corte. Falhou, desfaz tudo (inclusive o corte) e a execução fica
   `ERRO`.
4. **Pós-processar**: `ANALYZE` e refresh dos derivados do legislativo (`posprocessar_carga`), uma vez no fim da esteira.

## Recursos, na ordem em que um depende do outro

| Recurso | Fonte | Chave natural | Destino |
|---|---|---|---|
| `partidos` | `ref.partido_semente` (banco) + siglas citadas nas fontes | `sigla_normalizada` | `core.partido`, `partido_alias`, `partido_posicao_ideologica`, `midia` |
| `pessoas` | deputados, senadores (e suas filiações por período), presidentes (curado), ex-parlamentares e quem votou | `CAMARA_ID` / `SENADO_ID` / `CURADORIA_ID` | `core.pessoa` (+ `_identificador`, `_nome`, `midia`), `mandato`, `mandato_situacao`, `mandato_partido` (senadores), `eleicao` |
| `camara_historico` | eventos por deputado (API da Câmara) | `uq_mandato_natural` | `mandato`, `mandato_situacao`, `mandato_partido` |
| `filiacoes` | derivada de `mandato_partido` e do partido na posse de cada mandato (sem arquivo) | refeita inteira a cada carga | `core.filiacao` |
| `camara_lote` | CSV anuais da Câmara (proposições e autores) | `id_camara` | `leg.proposicao`, `leg.autoria`, `core.entidade` |
| `proposicoes` | JSON da API da Câmara e do Senado | `id_camara` / `id_senado`; numeração única (2019+) | enriquece `leg.proposicao`; cria a que falta |
| `votacoes` | plenário de 2023 e arquivos anuais | `id_externo` da sessão; `(votacao, pessoa)` do voto | `leg.votacao`, `leg.voto`, `leg.orientacao` |

Comando: `python -m etl.carga.orquestra [--recurso X] [--allow-unverified]`, ou pela esteira (`python -m etl.run_etl --fonte ...`).

## Regras que o código garante (e os testes de `etl/tests/test_carga_direta.py` travam)

- **Identidade.** A pessoa se acha pelo identificador oficial e, quando as fontes dão o CPF (detalhe do deputado na Câmara; `consulta_cand` do TSE, onde senador e presidente entram por nome civil + nascimento), pelo `CPF_HMAC`: o mesmo HMAC em dois cadastros é a mesma pessoa, mesmo com nome diferente (e funde duas pessoas já gravadas quando o HMAC comum chega depois). **CPF diferente prova pessoas diferentes**: nome civil + nascimento iguais não unem quem já tem `CPF_HMAC` distinto, e esse par não vira candidata a duplicidade. Sem chave configurada (ou com chave de menos de 32 caracteres) o ETL não gera `cpf_identificadores.json` e segue sem CPF. A chave não pode mudar sem refazer `cpf_identificadores.json` e `declaracoes_patrimonio.json`, e o HMAC já versionado no git não se apaga: vazamento da chave equivale a publicar os CPFs. Quem só consta nos votos e na presença do Senado (e os ex-senadores sem nascimento na lista por legislatura) ganha nome completo e nascimento de `senadores_dados_basicos.json` (detalhe `/senador/{codigo}`; o `senadores_basicos_extractor` é o único dono desse detalhe). O patrimônio declarado (`fin.declaracao_patrimonio`) liga a pessoa pelo id oficial, depois pelo `CPF_HMAC` que o extrator grava em cada declaração (só o HMAC; um HMAC de duas pessoas é ambíguo e não cai no nome, e homônimo com outro CPF conhecido é descartado) e só então pelo nome. Quem ainda fica sem CPF está listado em `docs/PENDENCIAS_CPF.md`. Id novo se liga a quem já existe quando o nome civil completo e a data de nascimento são iguais (deputado que virou senador = uma pessoa, dois ids). Nome sem data de nascimento, ou com data diferente, nunca une: vira linha em `core.pessoa_candidata_duplicidade`, para revisão humana (data diferente entra porque a mesma pessoa pode vir com a data errada em uma fonte). Quando uma pessoa tem mais de um id, cada coluna vem da fonte atual primeiro (prioridade 1) e a histórica só preenche o vazio, seja qual for o id que aparece primeiro.
- **Partido do senador por período.** Vem de `senadores_filiacoes.json` (`/senador/{codigo}/filiacoes`, `senadores_filiacoes_extractor`), cortado pelo mandato e gravado em `core.mandato_partido`; "Sem partido" não é partido (o período fica sem filiação). O partido que a lista informa (o atual) só vale como fallback, para o mandato sem períodos, quando a API não respondeu. Mandato que sobrepõe 1995 entra (a legislatura 49 termina em 1995-01-31) e a verificação `mandatos_que_chegam_a_1995` mede o fim do mandato.
- **Contagem medida.** `pessoas` e `votacoes` medem `gravadas` no banco (mandatos e ministros que sobraram; sessões e votos que entraram), então a verificação `contagens` (`lidas == gravadas + rejeitadas`) é real. Registro sem id oficial é rejeitado com motivo (`SEM_IDENTIFICADOR`); voto rejeitado tem motivo próprio (`VOTO_COM_OPCAO_INVALIDA`, `VOTO_SEM_SESSAO`, `VOTO_DE_SESSAO_REJEITADA`, `VOTO_DE_PARLAMENTAR_SEM_CADASTRO`, `VOTO_REPETIDO_NA_SESSAO`).
- **Desconhecido é `NULL`.** Proposição sem situação na fonte fica `SEM_INFORMACAO`; votação sem resultado fica com `aprovada`
  nulo (a tela mostra "Resultado n/d"); mandato sem data de início não existe; filiação só existe no período em que o partido é conhecido; partido
  desconhecido de uma fonte entra fora do catálogo com a própria sigla como nome; nunca "S.PART.", `2023-02-01` nem zero.
- **Rejeitar com motivo.** Cada linha que não entra tem motivo; `lidas == gravadas + rejeitadas`; os motivos vão agregados para
  `etl.rejeito`, e as rejeições de negócio do CSV da Câmara também por linha (chave natural).
- **Fonte atual vale sobre a histórica.** Os arquivos atuais corrigem o dado já gravado; os históricos só preenchem o vazio. O
  mandato de deputado da lista atual nunca sobrescreve o que o histórico por deputado gravou (datas e situações exatas).
- **Sem proveniência, não entra**: autoria
  de proposição só com `autor_fonte`. O CPF nunca é gravado: só o HMAC-SHA256 dele com a chave secreta `CPF_HMAC_KEY` (identificador `CPF_HMAC`).
- **Hora da votação sem fuso é a de Brasília**, inclusive para achar a filiação vigente no dia do voto.
- **Idempotência.** Rodar duas vezes não muda contagem nem `uid`; a filiação é refeita inteira a cada carga (a exclusão por
  período impede o `ON CONFLICT`), sempre a partir do que já está em `core`.

## Dados que vivem no banco (não no código)

Nome, espectro, ideologia, lema, número e logo dos partidos: `ref.partido_semente` (migração 0039, copiado do que era
`dados_partidos.py`). Pesos da metodologia: `param.peso`. Situações da Câmara, tipos de proposição e de autor, opções de voto:
`ref.*`. Presidentes e ministros da Fazenda: arquivo curado `presidentes_historico.json`, com fonte registrada.

## O que saiu

O schema `stg` inteiro, as funções `etl.preparar_*`, `etl.merge_*` e auxiliares, a ponte `core.mandato_legado`,
`leg.votacao_legado`, a coluna `leg.autoria.legado_id`, e os módulos `carga_cadastro`, `planas_*`, `staging_*`, `db_loader`,
`dados_partidos` (migração 0039; sem volta, os dados são regeneráveis). Nos testes do backend, `backend/tests/projecao/` leva as
linhas semeadas pelos modelos de teste a `core`/`leg` (só no banco de teste).

## Filiações

Não há arquivo de filiações. `core.filiacao` sai de dois dados oficiais já gravados: os períodos de partido por mandato
(`core.mandato_partido`, eventos da Câmara) e o partido na posse dos mandatos sem períodos (senadores, presidentes, lista atual).
No mesmo dia de início vale o período exato; períodos que se sobrepõem terminam na véspera do seguinte; trechos seguidos do
mesmo partido viram uma filiação. Fora disso a filiação é desconhecida (não há linha).

## Pendências conhecidas

- Trajetória partidária antes do primeiro mandato (e fora do Congresso) não existe nas fontes usadas: aparece como vazio.
- Deputado sem eventos de troca de partido no histórico da Câmara fica com o partido da lista atual no mandato inteiro (fallback do mandato sem períodos).
- Links antigos de sessão de votação do legado (`leg.votacao_legado`) deixaram de resolver com a 0039: os dados são regeneráveis e a rota responde "sessão não encontrada".
