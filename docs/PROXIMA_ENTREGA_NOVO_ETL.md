# Próxima entrega: o novo ETL grava direto em `stg` e confere cada fonte

Este documento é o roteiro da entrega que fecha a Fase 7 do plano (`PLANO_REFATORACAO_BANCO_DE_DADOS.md`). Foi escrito para quem for fazer a entrega não precisar redescobrir nada: o que existe hoje, o que mudar, em que ordem, o que conferir a cada passo e o que **não pode** se perder.

A API e as telas não mudam nesta entrega. Ela mexe só na forma de carregar os dados. Se alguma resposta da API mudar, é defeito.

## 1. Em linguagem simples

Hoje o ETL funciona assim: lê os arquivos baixados das fontes oficiais (Câmara, Senado, TSE), cria um objeto em Python para cada partido, político, mandato, proposição e voto, e grava um por um no banco, nas tabelas do schema `stg`. Depois, funções do próprio banco (`etl.merge_cadastro` e `etl.merge_legislativo`) transformam essas tabelas nas tabelas finais (`core` e `leg`), que são as que a API lê.

Isso funciona e está testado, mas tem três problemas:

1. **É lento e pesado.** Gravar objeto por objeto leva muito mais tempo que despejar o arquivo inteiro de uma vez.
2. **A conferência é parcial.** Não há, para cada fonte, um relatório do tipo "chegaram 513 deputados, entraram 513; o total de votos bate com o que a fonte informou; sobrou ninguém sem partido". Os problemas aparecem depois, na tela.
3. **Há duas maneiras de fazer a mesma coisa.** A Câmara em lote (proposições e autores) e o histórico de mandatos da Câmara já usam o modelo bom (copiar o arquivo para `stg`, rodar uma função de fusão, registrar a execução). O resto ainda usa o modelo antigo. Manter os dois custa caro.

A entrega leva todas as fontes para o modelo bom e aposenta o `db_loader.py` (hoje com 1.450 linhas).

## 2. O que existe hoje (estado da `main`)

### Fluxo
```
arquivos em etl/data/processed ──► db_loader.py (ORM, um registro por vez) ──► stg.*  ──► etl.merge_cadastro / etl.merge_legislativo ──► core.* e leg.*
arquivos da Câmara em lote     ──► camara_bulk_loader.py (COPY)           ──► stg.camara_* ──► etl.merge_camara_bulk ──► leg.*      (modelo bom)
histórico de mandatos da Câmara ─► camara_historico_loader.py             ──► stg.camara_historico ──► etl.merge_camara_historico ──► core.mandato (modelo bom)
```

### As seis etapas do `db_loader.load_all` (o que será substituído)
1. Partidos políticos → `stg.partidos_politicos`
2. Políticos (presidentes, deputados, senadores) → `stg.politicos`
3. Filiações partidárias → `stg.filiacoes_partidarias`
4. Mandatos e gabinete presidencial → `stg.mandatos`, `stg.membros_gabinete` (e os ex-parlamentares de `parlamentares_legislaturas_anteriores.json`)
5. Proposições e autores → `stg.proposicoes`, `stg.proposicoes_autores`
6. Sessões de votação, votos, deliberações e orientações → `stg.sessoes_votacao`, `stg.votos_parlamentares`, `stg.votacoes_proposicao`, `stg.votos_nominais`, `stg.orientacoes_partidarias`; presença em `stg.registros_presenca`

Arquivos de entrada principais (`etl/data/processed`): `deputados_camara.json`, `senadores_senado.json`, `presidentes_historico.json`, `filiacoes_partidarias.csv`/`.json`, `parlamentares_legislaturas_anteriores.json`, `proposicoes_2023.json`, `proposicoes_senado.json`, `sessoes_votacao_2023.json`, `sessoes_votacao_senado.json`, `votos_nominais_2023.json`, `votos_nominais_senado.json`, o diretório `votacoes/` e `presenca_plenario_dias.json.gz`.

### Peças que já existem e devem ser reaproveitadas
- Tabelas de controle em `etl`: `fonte`, `execucao` (estágio, status, linhas lidas/gravadas/rejeitadas), `arquivo_bruto` (URL, SHA-256, tamanho), `rejeito` (o que foi recusado e por quê) e `verificacao` (nome, passou/não, detalhe).
- O modelo de referência a copiar: `etl/pipelines/camara_bulk_loader.py` (`COPY` para `stg.camara_*`, registro em `etl.arquivo_bruto`, função `etl.merge_camara_bulk`).
- Funções de fusão: `etl.merge_cadastro` (~20 mil caracteres de SQL), `etl.merge_legislativo` (~16 mil), `etl.aplicar_linhagens`, `etl.resolver_partido_presenca`, `core.unificar_duplicadas`, `core.unificar_pessoas`.
- Resolvedor de pessoas: `etl/pipelines/pessoa_resolver.py` (`ResolvedorDePessoas`): identificador oficial primeiro, depois nome único, homônimo só se desfaz por mandato no ano. **Nunca atribuir por palpite.**
- Conferência da API contra o legado: `scripts/golden_snapshot.py` (grava as respostas da API e compara antes/depois).

## 3. O que fazer, em ordem

Cada pacote termina com a suíte verde e a comparação de dados descrita na seção 5. Não comece o seguinte antes de fechar o anterior.

### Pacote A: preparar o terreno (sem mudar comportamento)
- A.1 Registrar a execução. Toda carga passa a abrir uma linha em `etl.execucao` (estágio `CARREGAR`, depois `MERGE`) e a fechá-la com status, linhas lidas/gravadas/rejeitadas. Usar a mesma rotina que o `camara_bulk_loader` já usa; extraí-la para um módulo comum (`etl/utils/execucao.py`) em vez de copiar.
- A.2 Criar o módulo comum de `COPY`: recebe o arquivo (ou dados em memória já normalizados), a tabela `stg` de destino e as colunas; usa `cursor.copy_expert`; registra o arquivo em `etl.arquivo_bruto` com SHA-256. Copiar o padrão do `camara_bulk_loader`.
- A.3 Escrever o catálogo de verificações (seção 4) como funções puras com testes, ainda sem ligar nada.

### Pacote B: tabelas de staging "planas" (texto puro, sem regra de negócio)
Hoje `stg.politicos`, `stg.mandatos` etc. são tabelas relacionais com chave estrangeira entre si (herança do legado). O modelo bom usa tabelas planas por arquivo, em texto, sem chaves (como `stg.camara_proposicao`), e deixa toda regra para a função de fusão.
- B.1 Uma migração nova cria `stg.<fonte>_<recurso>` plano para cada arquivo de entrada (por exemplo `stg.camara_deputado`, `stg.senado_senador`, `stg.tse_filiacao`, `stg.camara_sessao_votacao`, `stg.camara_voto`, `stg.senado_voto`, `stg.camara_presenca_dia`). Colunas em texto, mais `execucao_id`.
- B.2 Um carregador por fonte (uma classe `Conector` que usa o `HttpClient` para baixar, quando aplicável, e o módulo de `COPY` para gravar).
- B.3 Reescrever `etl.merge_cadastro` e `etl.merge_legislativo` para lerem as tabelas planas, **mantendo a lógica atual** (copiar o texto da função do catálogo com `pg_get_functiondef` e adaptar só as origens). Não reescrever regra de negócio nesta entrega.
- B.4 Rodar o carregador novo **em paralelo** ao antigo num banco de teste e comparar `core`/`leg` (seção 5). Só depois ligar o novo como padrão.

### Pacote C: aposentar o legado
- C.1 Remover `db_loader.py`, os modelos ORM de `stg` (`app/models/politician.py`, `legislative.py`, `Base` com schema `stg`), `loader_helpers` que só ele usava, as tabelas `stg` relacionais antigas (migração com `DROP`), e os testes que usavam SQLite com `schema_translate_map`.
- C.2 Remover `core.unificar_duplicadas` e a chamada em `staging_merge.merge_staging` **somente depois** de provar que a carga nova resolve a pessoa pelo identificador antes de criar uma (seção 4, ponto 1). Se não for provado, a função fica.
- C.3 Renomear `app/services/staging_merge.py` se o nome já não fizer sentido, e atualizar `docs/`.

### Pacote D: relatório e comando
- D.1 `etl.verificacao`: gravar o resultado de cada verificação por execução, com `passou` e o detalhe em JSON.
- D.2 Relatório final de cada execução (texto no terminal e linha em `etl.execucao`): fontes carregadas, linhas por tabela, rejeitos por motivo, verificações que falharam.
- D.3 Comando por estágio e por fonte (`python -m etl.run_etl --fonte camara-deputados --estagio carregar`), para reexecutar uma fonte sem tocar nas outras.
- D.4 Teste ponta a ponta: banco vazio → ETL completo → derivados atualizados → comparação com os dados de referência. Medir o tempo total e registrar no plano.

## 4. Pontos de atenção (o que não pode se perder nem estragar)

1. **O `uid` público das pessoas não pode mudar.** O dossiê, os links compartilhados e as finanças são endereçados por ele. Hoje o `uid` vem do cadastro do legado (`stg.politicos.id`). Na carga nova, a pessoa deve ser resolvida pelo identificador oficial (Câmara/Senado) **antes** de criar uma nova; só cria se não existir. Foi exatamente a ausência disso que gerou os cadastros duplicados que a migração 0034 uniu (338 no banco de desenvolvimento). Se a carga nova criar a pessoa sem consultar o identificador, a duplicata volta.
2. **A migração 0034 não tem volta.** Ela une cadastros no banco de destino. Não mexa nela. Faça backup antes de qualquer migração desta entrega (o deploy já faz `pg_dump`; rode `scripts/deploy/verificar_backup.sh` antes de começar).
3. **Nenhum CPF em lugar nenhum (decisão D3).** O staging novo não pode ter coluna de CPF, mesmo vazia. A guarda de arquivos versionados continua valendo. Não coloque CPF real, nem sintético com dígito verificador válido, em testes.
4. **Só fonte oficial e rastreável (D7).** Cada linha de `stg` precisa apontar para o arquivo de origem (`etl.arquivo_bruto`). Linha sem fonte registrada não entra (hoje isso é a regra `autor_fonte`/`allow_unverified` do `db_loader`; preserve o comportamento).
5. **Janela de dados a partir de 1995-01-01 (D8).** Conferir nas verificações.
6. **Desconhecido é nulo, nunca zero.** Ao converter texto em número no `COPY`/fusão, campo vazio vira `NULL`, não `0`.
7. **Idempotência.** Rodar duas vezes seguidas não pode mudar nenhuma linha. Provar por contagem e por checksum por tabela (seção 5).
8. **Os derivados pré-calculados dependem dos gatilhos.** `leg.mv_autoria_pontuada_unica` e `leg.mv_coautoria_par` são refeitas por `leg.atualizar_derivados()` quando um gatilho por comando marca `leg.pontuacao_controle.sujo`. Cargas em massa disparam o gatilho uma vez por comando (barato). O gatilho é `BEFORE` e trava a linha de controle até o commit de quem escreve: as escritas nas dependências passam a ser uma transação por vez, uma escrita espera o fim de um refresh em curso (alguns segundos) e, como toda carga pega a trava de controle antes de qualquer linha de dado, duas cargas concorrentes não entram em deadlock. A garantia só vale se a primeira escrita da transação for numa dependência: toda transação de carga que escreve em `core.pessoa` ou em outra tabela antes de uma dependência começa com `derivados_service.reservar_derivados(conexao)` (`SELECT leg.reservar_derivados()`), como fazem hoje `staging_merge.merge_staging`, `camara_bulk_loader.mesclar`, `camara_historico_loader.carregar` e `presidencia_loader.carregar` (um teste confere que cada um reserva antes de escrever). O `TRUNCATE` de uma dependência fica fora da garantia. **Não desligue gatilhos para acelerar a carga**; e depois da carga, chame `garantir_atualizados` ou deixe a primeira leitura refazer. Se uma tabela nova passar a influenciar a pontuação ou a rede, ela entra na lista `DEPENDENCIAS` da migração 0037 e no teste `test_derivados.py`.
9. **`ANALYZE` depois da carga** (`etl.utils.manutencao.analisar_banco`) continua sendo chamado pelo `run_etl`. Mantenha.
10. **O deploy não pode quebrar.** `scripts/deploy/deploy.sh` roda migrações e `python -m etl.run_etl --load-economia`; o timer diário roda `etl.pipelines.financas_atualizacao`; `decidir_financas` e a semeadura de `fin` leem `etl.execucao`. Qualquer mudança em nomes de comandos, flags ou na tabela `etl.execucao` exige ajustar `deploy.sh`, `atualizar_financas.sh`, `docs/DEPLOY_AUTOMATICO.md` e os testes `test_scripts_deploy.py` na mesma entrega.
11. **Presença em plenário** (`leg.presenca`, particionada) tem carga própria (`presenca_leg_loader`) e já usa o modelo bom. Não duplicar. `etl.resolver_partido_presenca` resolve o partido depois da carga: manter a ordem.
12. **Homônimos.** Não relaxe o resolvedor para "ganhar" linhas. Linha sem pessoa identificada vai para `etl.rejeito` com motivo (`HOMONIMO_NAO_DESAMBIGUADO`, `NAO_CADASTRADO`), não é atribuída por palpite.
13. **Datas de mandato e filiação.** O intervalo de filiação em `core.filiacao` é semiaberto (`daterange`): a API subtrai um dia para mostrar o último dia. Preserve essa convenção ao carregar.
14. **Rejeitos viram relatório, não somem.** Hoje a fusão grava rejeitos em `etl.rejeito` (136 na carga do banco de desenvolvimento). A carga nova deve produzir o mesmo conjunto de rejeitos ou menos, e cada diferença precisa ser explicada.
15. **Teste que depende de Postgres.** A suíte usa o Postgres descartável (`make test-db-up`, porta 5433). Nunca rode duas suítes ao mesmo tempo. A suíte do ETL leva cerca de 10 minutos e a do backend cerca de 18.
16. **Cuidado com o banco certo.** O `backend/.env` define `DATABASE_URL`, que **vence** `POSTGRES_DB`. Para trabalhar numa cópia do banco, sobrescreva `DATABASE_URL` e confira `SELECT current_database()` antes de qualquer comando que escreva. Esta regra existe porque, numa entrega anterior, comandos pensados para uma cópia rodaram no banco de desenvolvimento.

## 5. Como provar que nada foi perdido

Siga o roteiro que funcionou nas entregas 4a e 4b:

1. **Cópia do banco real.** `CREATE DATABASE verif_novo TEMPLATE politica_db` (com a API parada), `DATABASE_URL` apontando para a cópia, e a guarda `assert current_database() == 'verif_novo'`.
2. **Duas cópias lado a lado.** Uma carregada pelo caminho antigo, outra pelo novo, a partir dos **mesmos arquivos**.
3. **Contagens e checksums por tabela** de `core.*` e `leg.*` nas duas cópias: o número de linhas e um resumo (`md5(string_agg(... ORDER BY chave))`) das colunas de negócio. Diferença de contagem precisa ser explicada linha a linha; diferença de checksum com a mesma contagem também.
4. **API contra API.** Subir a API sobre cada cópia e comparar as respostas dos endpoints principais com `scripts/golden_snapshot.py` ou com o comparador usado nas entregas anteriores: `/politicians` (lista e dossiês de uma amostra de pelo menos 13 pessoas, incluindo senadores, ex-parlamentares e presidentes), `/parties`, `/parties/ippm-ranking`, `/legislative/*`, `/analytics/*`. Diferença de `id` interno e de ordem de lista com empate é aceitável; qualquer outra precisa de explicação escrita no plano.
5. **Idempotência.** Rodar a carga nova duas vezes seguidas na mesma cópia e provar que contagens e checksums não mudam.
6. **Banco vazio.** `make test-db-up` + migrações + ETL completo reproduz o estado esperado sem intervenção manual (critério de pronto da Fase 7).
7. **Desempenho.** Registrar o tempo da carga completa antes e depois. A meta é ser mais rápido; se for mais lento, investigar antes de entregar.

## 6. Definição de pronto

- `python -m etl.run_etl` (completo) em banco vazio reproduz o estado esperado; uma segunda execução imediata não altera nenhuma linha (contagem e checksum).
- Cada fonte grava uma linha em `etl.execucao`, o arquivo de origem em `etl.arquivo_bruto` e as verificações em `etl.verificacao`; o relatório final lista fontes, linhas, rejeitos e verificações que falharam.
- `db_loader.py`, os modelos ORM de `stg` e as tabelas `stg` relacionais antigas não existem mais; nenhum `import` aponta para eles.
- As duas suítes completas passam; a comparação da seção 5 está registrada em `PLANO_REFATORACAO_BANCO_DE_DADOS.md` com as diferenças aceitas e o porquê.
- O deploy, o timer diário e o ensaio de restauração continuam funcionando (`test_scripts_deploy.py` verde; `verificar_backup.sh` testado).

## 7. Riscos e o que fazer se algo der errado

| Risco | Como aparece | O que fazer |
|---|---|---|
| Pessoa duplicada volta | `core.pessoa` cresce após a carga; `GET /politicians` lista a mesma pessoa duas vezes | Parar. Conferir se a carga resolve pelo identificador antes de criar. Não reativar a unificação como remendo sem entender a causa |
| Mudança sutil em partido/mandato | Dossiê de uma pessoa muda de partido atual, ou aparece mandato a mais/a menos | Comparar `core.mandato` e `core.filiacao` por pessoa entre as duas cópias; a regra de fusão foi alterada sem querer |
| Votos ou presença a menos | Contagem de `leg.voto` ou `leg.presenca` menor que a original | Conferir as verificações de totais por fonte; olhar `etl.rejeito` |
| Carga mais lenta | Tempo total maior que o do `db_loader` | Medir por estágio (`COPY`, fusão, `ANALYZE`); suspeitar de gatilho dos derivados em loop ou de índice faltando em `stg` |
| Deploy falha | Timer/`deploy.sh` não encontra comando ou flag | Ajustar scripts e docs na mesma entrega; rodar `test_scripts_deploy.py` |
| Perda de dado | Qualquer contagem menor sem explicação | Restaurar o backup (`pg_restore`, ver `DEPLOY_AUTOMATICO.md`) e refazer; os dados são regeneráveis pelas fontes, mas o `uid` público só se preserva se a unificação for respeitada |

## 8. Fora do escopo desta entrega

- Qualquer mudança de contrato da API ou das telas.
- Novas fontes de dados.
- Regras de negócio novas (pesos do IALP, classificação de proposições).
- Trocar o `DataJudClient` para o `HttpClient`: entra no pacote B só se o conector do DataJud for criado, e deve seguir a regra registrada em `.claude/rules/etl.md`.

## Modelos do staging dentro do pacote da API

`StagingBase` (`backend/app/models/base.py`) e os modelos `stg` (`politician.py`, `legislative.py`) só servem ao ETL e aos
testes, mas moram em `app.models` e são exportados por ele, embora a API nunca leia o `stg`. Quando o `db_loader` sair, os
modelos `stg` saem junto; até lá, não importe `StagingBase` nem esses modelos em código da API.
