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

### Estado final da entrega (5 de novembro de 2026)

**Feito.** Os pacotes A a D foram entregues por inteiro, inclusive o `stg` plano com a fusão lendo-o (B.1 e B.3), a queda das tabelas relacionais (C.1) e a saída de `core.unificar_duplicadas` (C.2).

- **A (terreno):** `etl/utils/execucao.py`, `copia.py` e `verificacoes.py` (PR #57).
- **B.1 (tabelas planas):** uma tabela por arquivo de entrada, sem chave estrangeira, com `execucao_id` e o número da linha (migração 0040): `stg.curadoria_partido`, `curadoria_partido_conhecido`, `curadoria_presidente`, `curadoria_ministro_fazenda`, `camara_deputado`, `senado_senador`, `tse_filiacao`, `camara_proposicao_api`, `senado_proposicao_api`, `camara_sessao_plenario`, `camara_voto_plenario`, `senado_sessao_plenario`, `senado_voto_plenario`, `historico_parlamentar`, `historico_partido`, `historico_sessao` e `historico_voto`. O Python (`etl/pipelines/planas_cadastro.py`, `planas_proposicoes.py`, `planas_votacoes.py`) só lê o arquivo e copia por `COPY`: nenhuma consulta ao banco, nenhuma decisão sobre identidade. Só o que depende da própria linha é calculado lá (data, texto da pauta, biografia, classificação do eixo, a opção do voto). Cada carga substitui o conteúdo da tabela pelo do arquivo atual. Nenhum CPF passa daí (o arquivo de presidentes traz o campo e ele é descartado; `test_planas` confere).
- **B.2/B.3 (resolução e fusão):** `etl.preparar_staging()` roda na transação da fusão e monta as tabelas **temporárias** de trabalho `w_partidos`, `w_politicos`, `w_filiacoes`, `w_mandatos`, `w_gabinete`, `w_proposicoes`, `w_sessoes` e `w_votos` (as mesmas colunas das relacionais antigas). A identidade vem de `core`/`leg`: `etl.semear_cadastro()` reconstrói em `w_*` o que a fusão já gravou (a fusão é função determinística do staging; ali se faz o caminho inverso), e `etl.preparar_cadastro`, `etl.preparar_proposicoes`, `etl.garantir_historicos` e `etl.preparar_votacoes_*` aplicam por cima o que os arquivos trazem, com as regras que eram do carregador em Python (id oficial, depois nome único; filiação sem proveniência é rejeitada; proposição pelo id da casa; autor por id, nome exato, nome normalizado ou conjunto de palavras, sempre só quando único; mandato por legislatura). `etl.merge_cadastro` e `etl.merge_legislativo` ficaram como eram (o texto vem do catálogo, como na 0036 e na 0038) e passaram a ler `w_*`; a única mudança de lógica é o desempate de filiações com o mesmo início, em que a que já está em `core.filiacao` continua. O que o arquivo traz e a fusão rejeita (filiação sem proveniência, voto sem sessão, político ou opção) volta no resumo, com motivo, e vai para `etl.rejeito` na execução `PIPELINE`/`MERGE`.
- **B (carga sem ORM):** `etl/pipelines/carga_cadastro.py` (`CargaCadastro`) substitui o `DatabaseLoader`. Cada recurso (`partidos`, `politicos`, `filiacoes`, `parlamentares_historicos`, `proposicoes`, `votacoes_plenario`, `votacoes_historico`) abre a sua linha em `etl.execucao` (`CARREGAR`, `parametros['recurso']`), copia o arquivo para a(s) plana(s), registra os arquivos de origem em `etl.arquivo_bruto` (SHA-256 e caminho relativo), confere que o `COPY` entregou tudo (`*_copiada` em `etl.verificacao`) e fecha a linha com as contagens. Os mandatos de presidentes, deputados e senadores saem dos mesmos arquivos de `politicos` (por isso a fonte `mandatos` do `--fonte` carrega esse recurso). As verificações do que a fusão gravou (a partir de 1995, cobertura dos deputados e senadores da fonte) ficam na execução da fusão.
- **C.1 (aposentar o legado):** `db_loader.py`, `votacoes_loader.py`, os modelos ORM do `stg` e as oito tabelas relacionais (`stg.politicos`, `partidos_politicos`, `filiacoes_partidarias`, `mandatos`, `membros_gabinete`, `proposicoes`, `sessoes_votacao`, `votos_parlamentares`) saíram; também saíram o `stg_tabela`, as etapas em Python de políticos, filiações, mandatos, proposições e votações e o script de saneamento de autoria (a fusão refaz o vínculo a cada carga). **Congeladas, não apagadas:** as cinco tabelas que nenhuma carga escreve mais (`stg.proposicoes_autores`, `registros_presenca`, `votacoes_proposicao`, `votos_nominais`, `orientacoes_partidarias`) perderam as chaves estrangeiras para as que caíram, mas ficam, porque a fusão ainda as lê (relatores, presença do legado, votações e orientações) e apagá-las perderia dado de origem que nenhum arquivo atual reproduz (no banco de desenvolvimento: 343.736 registros de presença, 5.380 votos nominais, 6.326 autorias, 30 votações e 389 orientações). Se um dia o legado for aposentado por inteiro, essa é a decisão a tomar. Em teste, as oito de trabalho são tabelas comuns em `public` (só no banco de teste, `backend/tests/stg_models.py`) e a fusão as acha pelo `search_path`.
- **C.2:** `core.unificar_duplicadas` saiu (migração 0041, junto com a chamada em `staging_merge`). A prova está em "Medido": a pessoa é achada pelo identificador oficial antes de qualquer cadastro novo, o `uid` que já existe não muda e as tabelas de pessoa ficam idênticas às da carga anterior, duas rodadas seguidas. `core.unificar_pessoas` (a união em si) fica.
- **C.3:** `app/services/staging_merge.py` mantém o nome: continua sendo a fusão do staging (agora `merge_staging` prepara e funde numa transação só).
- **D (relatório e comando):** cada execução grava a verificação `contagens` e as que o carregador mediu em `etl.verificacao` (uma que não passa deixa a execução em `COM_ALERTA`); a esteira inteira tem a sua linha (`PIPELINE`/`TUDO`, migração 0039); `python -m etl.run_etl` imprime o relatório da rodada e `--relatorio` o repete. Comando por fonte e estágio: `python -m etl.run_etl --fonte votacoes --estagio carregar` (`--listar-fontes` mostra as fontes).

**Arquivos que ficam para você apagar** (cada um tem só uma linha de aviso, sem import que o use): `etl/pipelines/db_loader.py`, `etl/pipelines/votacoes_loader.py`, `etl/pipelines/stg_tabela.py`, `etl/pipelines/staging_cadastro.py`, `etl/pipelines/staging_votacoes.py`, `etl/scripts/fix_author_associations.py`, `etl/tests/test_db_loader.py`, `etl/tests/test_stg_tabela.py`, `etl/tests/stg_consulta.py`, `backend/app/models/politician.py` e `backend/app/models/legislative.py`. As migrações 0040 e 0041 têm volta (recriam as relacionais vazias e devolvem às funções as origens `stg.*`), mas **não restauram as linhas**: o deploy tira o `pg_dump` antes e a próxima carga repõe o staging.

**Medido** (cópias de verificação, nunca o banco de desenvolvimento). Do banco vazio só com migrações: a carga completa levou **253 s** (a antiga, 816 s) e uma recarga **206 s**; as contagens das tabelas de `core`, `leg`, `ref` e `param` são **iguais às da linha de base**, e o conteúdo, conferido por checksum de cada tabela de domínio por chave natural (pessoa, nome, partido, mandato, filiação, proposição, votação, voto, autoria e orientação), é **igual ao do carregador antigo** carregado dos mesmos arquivos. Sobre a cópia do dev com presença: 258 s e 230 s (a antiga, 268 s e 249 s), idempotente (o resumo da fusão é o mesmo nas duas rodadas), contagens iguais e checksums iguais em pessoa, nome, identificador, partido, mandato, situação, filiação, votação, voto, autoria, orientação e posição ideológica. Diferem só **14 proposições do legado** que a carga antiga deixava com eixo de impacto ou autor velhos (o `INSERT` pulava a linha porque o staging antigo guardava o id da Câmara numa linha e o do Senado noutra): a nova as atualiza, e 5 delas ganharam o autor certo. A preparação sozinha leva cerca de 56 s; o resto é a fusão, que não mudou.

**O que o relatório mostra com os dados reais** (a leitura é parte do valor): `filiacoes` rejeita as 1.190 do arquivo legado sem proveniência (`SEM_PROVENIENCIA`; no banco de desenvolvimento, as 1.019 que já estão em `core.filiacao` continuam lá, vindas da semente de cargas anteriores com `fonte`; do banco vazio não entra nenhuma até a extração do TSE rodar de novo); `parlamentares_historicos` rejeita 271 suplentes que nunca votaram; a fusão rejeita os votos que não viram linha (7.886 em 1.276.517, em qualquer das duas cópias) (sem sessão, político ou opção válida). A verificação `proposicoes_a_partir_de_1995` agora olha o que chegou a `leg.proposicao`: as 2 proposições de 1991 que a decisão D8 exclui não passam da fusão (`FORA_DA_JANELA_1995` em `etl.rejeito`). Por isso essas execuções saem `COM_ALERTA`: é o retrato do dado, não falha de carga. Um limiar ou a comparação com a execução anterior, para separar o esperado do novo, continua em aberto.

**Um registro, uma única vez:** numa das cargas de verificação da versão anterior deste trabalho, um `COPY` de votos falhou com um UUID com um caractere trocado (`...58f³7`). Não se repetiu em nenhuma das cargas desta versão (uma delas de 1,27 milhão de votos, várias vezes); trato como defeito de hardware ou do interpretador, mas fica anotado.

### Pacote A: preparar o terreno (sem mudar comportamento)

> **Estado:** feito. Os módulos comuns são `etl/utils/execucao.py` (`registrar_execucao`, `registrar_arquivo_bruto`), `etl/utils/copia.py` (`copiar_arquivo`, `copiar_linhas`, `esvaziar`, `transacao_de_carga`, `contar`, `contar_linhas_csv`, `colunas_da_tabela`) e `etl/utils/verificacoes.py` (catálogo puro, ainda não gravado em `etl.verificacao`: isso é o D.1; o campo `diferenca` é sempre `obtido - esperado`). `camara_bulk_loader`, `camara_historico_loader` e `presenca_leg_loader` já usam o `COPY` comum e a `transacao_de_carga`, e cada carga dos dois primeiros abre uma linha `CARREGAR` em `etl.execucao`. A presença **ainda não registra execução** de propósito: ela junta três fontes (eventos da Câmara, portal e Senado) numa transação só, e uma linha só não diria de qual veio cada contagem; ela passa a registrar uma execução por fonte quando o Pacote B separar os conectores. A execução é aberta e fechada em transações próprias, para uma carga desfeita ficar registrada como `ERRO` (só a classe da exceção). Ela só fecha `OK` quando as contagens foram preenchidas e fecham (`lidas == gravadas + rejeitadas`) e nada foi rejeitado; contagem ausente ou que não fecha vira `COM_ALERTA`, porque o `deploy.sh` lê `CARREGAR`+`OK`. No lote da Câmara, `lidas` vem das linhas dos arquivos e `gravadas` da contagem do staging, para a conferência detectar um `COPY` que perdesse linha. Falhar ao fechar a linha nunca derruba a carga nem impede o merge; a linha que ficou `EXECUTANDO` por mais de seis horas é fechada como `ERRO`/`INTERROMPIDA` na próxima abertura da mesma fonte e estágio. Os parâmetros da execução não podem usar as chaves `carga` e `fonte`, que o `deploy.sh` e a `semeadura_das_financas` leem para saber quem é dono dos dados de finanças. O `COPY` só aceita nome de tabela simples (minúsculas; o schema é obrigatório onde o nome vem do catálogo) e delimitador de um caractere. Em `copiar_linhas` vazio e `None` viram `NULL` (`FORCE_NULL`), inclusive numa tabela de uma coluna; em `copiar_arquivo` o conteúdo da fonte vai como está (um campo vazio entre aspas continua texto vazio). Uma carga que dure mais de seis horas deve passar `orfa_apos` maior ao registrar a execução. Duas mudanças pequenas de comportamento, ambas coerentes com "desconhecido é nulo": `stg.camara_legislatura` agora grava data vazia como `NULL` (antes `''`), e `etl.arquivo_bruto.execucao_id` passa a apontar para a execução que trouxe o arquivo (antes ficava `NULL`), o que obriga qualquer expurgo futuro de `etl.execucao` a apagar ou anular o arquivo antes.
- A.1 Registrar a execução. Toda carga passa a abrir uma linha em `etl.execucao` (estágio `CARREGAR`, depois `MERGE`) e a fechá-la com status, linhas lidas/gravadas/rejeitadas. Usar a mesma rotina que o `camara_bulk_loader` já usa; extraí-la para um módulo comum (`etl/utils/execucao.py`) em vez de copiar.
- A.2 Criar o módulo comum de `COPY`: recebe o arquivo (ou dados em memória já normalizados), a tabela `stg` de destino e as colunas; usa `cursor.copy_expert`; registra o arquivo em `etl.arquivo_bruto` com SHA-256. Copiar o padrão do `camara_bulk_loader`.
- A.3 Escrever o catálogo de verificações (seção 4) como funções puras com testes, ainda sem ligar nada.

### Pacote B: linha de base medida (4 de novembro de 2026)

O Pacote B começou pela prova de equivalência, para ter com o que comparar. Dois achados mudam o método da seção 5:

1. **A cópia do banco de dev não serve de ponto de partida.** O staging dela (1.570 mandatos, 1.066 políticos) não corresponde aos arquivos de hoje (2.345 mandatos, 1.427 políticos depois de recarregar). Rodar a carga antiga em cima da cópia falhou na fusão: `etl.merge_cadastro` apaga mandatos do legado que sumiram do staging, e `leg.presenca` os referencia (`presenca_mandato_id_fkey`, sem `ON DELETE`). Ou seja, a fusão do cadastro não tolera um staging que perdeu mandatos já referenciados pela presença; a carga nova tem de preservar esse caso ou a fusão tem de tratá-lo.
2. **O ponto de partida correto é um banco vazio só com as migrações** (critério de pronto da Fase 7), clonado por `CREATE DATABASE ... TEMPLATE` para o caminho antigo e o novo. Os `uid` públicos novos são aleatórios em cada carga, então a comparação entre dois bancos vazios é por chave natural (identificador oficial, sigla, número da proposição), nunca por `id` ou `uid`.

**Linha de base do caminho antigo** (`DatabaseLoader().load_all()` a partir do banco vazio, sem presença, lote e histórico): 816 s (13,6 min), concluiu sem erro. Contagens: `core.pessoa` 1.443, `core.pessoa_identificador` 1.456, `core.mandato` 2.125, `core.partido` 43, `leg.proposicao` 5.326, `leg.autoria` 3.614, `leg.votacao` 3.571, `leg.voto` 1.262.239; staging: 1.433 políticos, 2.112 mandatos, 5.328 proposições, 3.587 sessões, 1.268.631 votos.

**Lógica que a carga nova precisa reproduzir** (está no `db_loader`, não no SQL): a lista de partidos montada de cinco fontes mais os mapas curados (`PARTY_METADATA_MAP`, `PARTY_SPECTRUM_MAP`, `PARTY_LOGOS_MAP`), o descarte de número eleitoral repetido, a criação preguiçosa de partidos extintos citados só em filiações (`_ensure_party`, chamada também pelas etapas 4 e 6), o filtro de proveniência (`allow_synthetic`, `allow_unverified`: 1.190 filiações ficam de fora sem `--allow-unverified`) e os mapas de enumeração. Cada etapa tem de ser portada junto com a sua fatia da função de fusão e conferida contra esta linha de base.

### Pacote B: estado da primeira parte (4 de novembro de 2026; superado pelo estado final acima, que inclui B.1, B.3 e C.1)

> **Feito neste pacote:** (1) os partidos (etapa 1) passam por `COPY` e upsert em SQL (`staging_partidos.py`, mapas curados em `dados_partidos.py`), preservando o `id` do partido existente, que a fusão usa como `uid` público; (2) os votos nominais, o maior volume (1,26 milhão de linhas), passam por `COPY` para uma tabela temporária e `INSERT ... ON CONFLICT DO NOTHING` (`staging_votos.py`), nos dois caminhos (arquivos do plenário e histórico): um voto já gravado nunca é sobrescrito nem duplicado; (3) `DatabaseLoader.load_all` registra uma execução `CARREGAR` da fonte `LEGADO` em `etl.execucao` (status `ERRO` com só a classe da exceção quando falha; contagens de votos do plenário e do histórico, somadas por `ContagemDeVotos`: `lidas` = votos que as fontes trouxeram, inclusive os de sessão descartada; `rejeitadas` = sem sessão, sem político ou com opção desconhecida; `gravadas` = inseridas mais as que já existiam, então um voto repetido (no lote ou entre plenário e histórico) conta uma vez em cada entrega e `gravadas` pode passar o número de linhas distintas do staging, e o que fecha é `lidas == gravadas + rejeitadas`; `COM_ALERTA` quando há rejeitadas, como ocorre com os dados reais: 405 de 1.276.517; também sai `COM_ALERTA` quando um arquivo de votos é pulado inteiro (ilegível, sem proveniência ou só com um dos dois lados, sessões sem votos ou o contrário), porque os votos dele não entram em nenhuma contagem: `Execucao.com_alerta`, marcado pelo carregador); (4) o log traz o tempo de cada etapa; (5) a migração 0038 corrige a fragilidade da fusão descrita acima: `etl.merge_cadastro` deixa de apagar o mandato da fonte `LEGADO` que ainda é referenciado por `leg.presenca`, `core.mandato.nomeado_por_mandato_id` ou `core.mandato_situacao.substituto_mandato_id` (o mandato fica sem vínculo em `core.mandato_legado` e a próxima fusão tenta de novo; a carga registra no log quantos ficaram assim, e o nomeado órfão que o referencia só sai na fusão seguinte). As quatro situações (presença, nomeador, substituto e presença num mandato nomeado, que passa pelo segundo `DELETE`) têm teste cada uma, e o rebaixamento e a recusa de uma função editada fora das migrações também.
>
> **Mudança de dado servido, intencional:** as chaves de `PARTY_SPECTRUM_MAP` e `PARTY_FULL_NAMES` passam para maiúsculas (como as de logos e metadados), então a grafia "PC do B" passa a casar na consulta em maiúsculas e o partido recebe espectro `ESQUERDA` na próxima carga (antes ficava sem espectro).
>
> **Ponto em aberto:** com os dados reais toda carga `LEGADO/CARREGAR` sai `COM_ALERTA` (405 rejeitadas), então o status não separa a rejeição esperada (sessão sem proposição na janela, opção desconhecida) de uma regressão que a aumente. Um limiar ou a comparação com a execução anterior entra com o Pacote D (`etl.verificacao`), não aqui.
>
> **Medido** (banco vazio só com migrações, clonado por `CREATE DATABASE ... TEMPLATE`): carga completa **361 s** contra **816 s** da linha de base; as contagens de todas as 48 tabelas de `core`, `leg`, `stg`, `ref`, `param` e `etl` são iguais às da linha de base (a única diferença é `etl.execucao`, que ganhou a linha de execução); a segunda carga seguida dá as mesmas contagens (idempotente) em 198 s. Sobre a cópia do banco de dev (staging mais antigo, com presença): a carga conclui (antes falhava na fusão), 501 s, 123 s na segunda, mesmas contagens nas duas, e nenhum cadastro duplicado (`core.pessoa` 3.045 → 3.019, pela unificação de duplicadas que já existia).
>
> **Resolvida no estado final acima:** a resolução das etapas 2 a 5 e do histórico de ex-parlamentares foi para SQL (`etl.preparar_*`), conferida contra a carga anterior (contagens e checksums iguais), e o Pacote C andou depois dela.

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

## Modelos do staging

Resolvido: `StagingBase` e os modelos `stg` saíram de `app.models` (a API nunca leu o `stg`). Os modelos declarativos que restam são só de teste, em `backend/tests/stg_models.py`: as oito tabelas de trabalho da fusão (`w_*`, tabelas comuns em `public` apenas no banco de teste; em produção são temporárias) e as cinco tabelas congeladas de `stg`. Não importe nada disso em código da API nem do ETL.
