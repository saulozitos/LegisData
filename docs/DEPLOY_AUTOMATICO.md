# Deploy automático no servidor

Todo commit que entra na `main` e passa no CI é implantado sozinho em https://legisdata.top/.

## Como funciona

1. O workflow `Build & Publish Containers` publica as imagens `legisdata-backend` e `legisdata-frontend` no GHCR com as tags
   `latest` e o SHA curto do commit (7 caracteres), mas só depois do `CI Quality Gate` passar.
2. No servidor, um timer do systemd **do usuário** (`legisdata-deploy.timer`, a cada 2 minutos) roda
   `scripts/deploy/deploy.sh`. Sem commit novo ou sem imagens publicadas para o SHA, ele sai sem fazer nada.
3. Com commit novo e imagens prontas, o script primeiro confere se a cópia dele que o timer executa é a mesma do commit
   a implantar; se for diferente, instala a do commit e se reexecuta uma vez (assim uma mudança no próprio deploy, como
   uma carga nova, vale já no deploy que a traz). Depois faz, nesta ordem:
   1. `pg_dump` (formato custom) em `~/backups`, guardando os 14 mais recentes. Backup vazio aborta o deploy. Se uma
      tentativa anterior do mesmo commit já deixou o dump (de antes das migrações), ele é reaproveitado: um deploy
      quebrado repetido pelo timer não expulsa da rotação o último backup bom. O dump é gravado como `.dump.parcial` e só recebe o nome definitivo (e permissão 600) ao terminar bem, então um dump interrompido nunca é reaproveitado.
   2. `git merge --ff-only origin/main` no checkout do projeto (compose, dados do ETL e scripts). O cron diário regrava
      arquivos versionados de `etl/data/processed` no checkout, o que impediria o fast-forward; por isso o script
      descarta essas saídas locais antes do merge (o próximo cron as gera de novo). Fora dessa pasta, mudança local
      continua impedindo o merge de propósito.
   3. `alembic upgrade head` num contêiner da imagem nova, na rede do compose.
   4. Carga das séries econômicas, dos mandatos presidenciais, da composição do Congresso, da PNAD e das finanças
      (`economia_loader`, `presidencia_loader`, `composicao_loader`, `pnad_loader` e, das finanças, só o que a função
      `decidir_financas` manda: tudo se o `fin` está vazio ou se o timer ainda não assumiu nenhuma fonte; só a CEAP
      ou só as emendas, conforme a que o timer ainda não assumiu; remuneração, patrimônio, doações, certidões e processos se o
      commit mudou os arquivos ou o código delas; nada caso contrário. Uma fonte que o timer já assumiu nunca volta ao
      retrato do git), se o schema `eco` já existe.
      São idempotentes e rodam por `etl.pipelines.carga_economica.carregar_tudo` (a mesma função do
      `run_etl --load-economia`). Se um arquivo de curadoria estiver ausente ou citar um mandato que não existe no
      banco, a carga falha com as migrações já aplicadas e a imagem antiga ainda no ar (as tabelas novas são aditivas;
      só as rotas cujo arquivo foi removido do checkout pelo merge, como o `wage-disparity` antigo, respondem 404
      até a imagem nova subir); o estado não avança e a próxima execução repete até alguém corrigir. É uma decisão consciente: dado de curadoria
      inválido segura o deploy (nenhuma versão nova sobe sobre telas sem dados), em vez de publicar com a composição ou
      a PNAD desatualizadas; o log do deploy diz qual arquivo falhou.
   5. `IMAGE_TAG=<sha> docker compose up -d --no-build backend frontend`.
   6. Espera a API ficar saudável por até 3 minutos. Se não ficar, volta para a tag anterior e o estado não avança (a
      próxima execução tenta de novo). O banco já migrado não volta atrás: restaure o backup se preciso.
   A URL do banco (com a senha) vai ao contêiner por arquivo de ambiente temporário com permissão 600, não pela linha de
   comando.
4. O estado fica em `~/.legisdata-deploy` (`ultimo_sha`, `ultima_tag`, lock). Os logs vão para o journal do usuário.

O Watchtower foi removido: ele trocava a imagem da API sem backup, e a API aplica as migrações no boot.

## Instalação (uma vez, sem sudo)

Nenhum caminho, endereço ou credencial do servidor entra no repositório: o diretório do projeto fica só no arquivo
`~/.legisdata-deploy/ambiente` da máquina. O instalador lê os arquivos com `git show`, sem alterar o checkout:

```bash
cd <diretório do projeto no servidor>
git clean -fdq scripts            # só se sobrou cópia solta de uma instalação manual anterior
git fetch -q origin
f="$(mktemp)"; git show origin/main:scripts/deploy/instalar.sh >"$f"
bash "$f" origin/main; rm -f "$f"
```

O instalador grava o ambiente, instala o script e as units, marca o commit atual como já implantado, roda um dry-run,
remove o Watchtower e liga o timer. Pode ser executado de novo.

## Premissa do banco

O usuário do Postgres do deploy (`POSTGRES_USER`) precisa poder criar papéis e passar a posse de objetos a eles: as
migrações 0036 e 0037 criam `legisdata_leitura` e `legisdata_derivados`. Com a imagem oficial do Postgres esse usuário é
superusuário e nada precisa ser feito; num Postgres gerenciado sem superusuário, um administrador cria os dois papéis
(`NOLOGIN`) antes do deploy. Depois de cada carga o deploy também refaz os derivados do legislativo
(`etl.utils.manutencao.posprocessar_carga`), para a primeira requisição não pagar o refresh.

## Operação

- Ver o último ciclo: `journalctl --user -u legisdata-deploy.service -n 50`.
- Rodar na hora: `systemctl --user start legisdata-deploy.service`. Testar sem alterar nada: `~/.legisdata-deploy/deploy.sh --dry-run`.
- Pausar: `systemctl --user stop legisdata-deploy.timer`.
- Voltar uma versão (o rollback automático do `deploy.sh`, quando a API nova não fica saudável em 3 minutos, devolve só a imagem e registra um AVISO no log se a revisão do banco mudou naquele deploy): `IMAGE_TAG=<sha anterior> docker compose up -d --no-build backend frontend`. Se a migração mudou o schema, só a imagem não basta e o banco precisa voltar ao dump feito antes dela. As migrações 0034 (unificação de cadastros) e 0035 (aposentadoria das tabelas legadas) não têm volta pelo `downgrade`, e as 0036 e 0037 movem tabelas, renomeiam funções e criam objetos que a imagem antiga não conhece. Abaixo da versão que trouxe as migrações 0035 a 0037 isso vale sempre: a imagem antiga ainda cria no boot tabelas vazias do `public` (`log_execucao_cron`, `processos_judiciais`, `historico_mandatos`), grava o log do cron lá e o `upgrade_schema` dela não reconhece a revisão 0037. **Restaure o dump num banco vazio**, nunca por cima do banco migrado: `pg_restore --clean` sobre ele falha por dependência (as visões materializadas e os gatilhos da 0037 dependem das tabelas do dump e não estão nele), ignora o erro e deixa o schema misturado, e o próximo deploy para frente falha com "already exists". Ordem (apaga o banco atual: só com o dump à mão e conferido): 1) parar o backend e qualquer carga (`docker compose stop backend`); 2) apagar e recriar o banco vazio no contêiner do Postgres (`dropdb` e `createdb` com o usuário e o nome do `.env`); 3) `pg_restore -d <banco>` do dump (formato custom); 4) conferir a revisão (`alembic current` deve mostrar a anterior à 0035) e as pessoas; 5) subir a imagem anterior. O papel `legisdata_leitura` (e `legisdata_derivados`) é do cluster, não do banco: sobrevive, sem privilégios, e as migrações os recriam e reconcedem ao subir de novo. O deploy que traz essas migrações também cai no modo `estaticas` com recarga de finanças, porque qualquer migração nova conta como mudança do código da carga.
- Ensaio de restauração: `scripts/deploy/verificar_backup.sh [arquivo.dump]` restaura o backup mais recente (ou o indicado) num banco descartável dentro do contêiner do Postgres, confere a revisão do Alembic e se `core.pessoa` tem linhas, e apaga o descartável. Não toca no banco de produção e restaura num banco vazio, que é o mesmo caminho do rollback acima. Rode uma vez por mês: um backup que nunca foi restaurado não é backup. As migrações 0034 (unificação de cadastros duplicados) e 0035 (aposentadoria das tabelas legadas) não têm volta pelo `downgrade`, então o backup que o deploy faz antes das migrações é o único caminho de volta.
- Restaurar um backup: sempre num banco vazio, pelo mesmo caminho de "Voltar uma versão" (parar o backend, `dropdb` e `createdb` com o usuário e o nome do `.env`, `pg_restore -d <banco>` do dump em formato custom, conferir a revisão e as pessoas). Não use `pg_restore --clean --if-exists` por cima de um banco já migrado: as visões materializadas e os gatilhos da 0037 não estão no dump e o schema fica misturado. O ensaio mensal (`verificar_backup.sh`) faz exatamente esse caminho num banco descartável.

## Atualização diária de CEAP e emendas (`legisdata-financas.timer`)

O `fin` não depende mais só do deploy: um segundo timer do usuário roda todo dia às 05:37 UTC (02:37 em Brasília; horário
não redondo, como pede a documentação da API do Senado) o script `~/.legisdata-deploy/atualizar_financas.sh`, que executa
`python -m etl.pipelines.financas_atualizacao` num contêiner da imagem da API que está no ar. O contêiner roda com o checkout
montado só para leitura e apenas `etl/data` gravável, na rede do compose, com limite de 2 GB de memória, sem capacidades
(`--cap-drop ALL`), sem privilégios novos e com o `.env` escondido (só recebe as credenciais do banco, por arquivo de
ambiente 600; o `Settings` do backend monta a URL e codifica a senha). O que ele faz:

1. Baixa a CEAP da Câmara e do Senado e as emendas do Portal da Transparência e regrava os arquivos de
   `etl/data/processed`. A CEAP de cada ano **já fechado** (depois de 1º de abril do ano seguinte) vem do cache em
   `etl/data/raw/ceap_por_ano` (fora do git) e não é baixada de novo até o cache vencer (90 dias); só o ano corrente, e o
   anterior até março, vão à rede. A primeira execução baixa todos os anos desde 2019, com 10 s de pausa entre os
   downloads da Câmara (ela responde 429 a CSVs anuais seguidos), e leva alguns minutos; as seguintes são leves. O cache
   não guarda CPF: a extração só mantém o CNPJ de 14 dígitos dos fornecedores e tira o CPF embutido dos nomes.
2. Cada fonte é independente. Um ano que falha ganha uma segunda tentativa depois de 90 s; um ano que volta vazio é falha
   (nunca "gasto zero"). Até março, o arquivo (ou a lista) do ano novo que a fonte ainda não publicou não derruba a CEAP: o ano
   fica de fora e o resumo registra `ceap_anos_sem_arquivo`, mas só se nem o arquivo processado anterior nem o
   `fin` tinham gasto daquele ano (um vazio depois de o ano já ter dados é falha, para não apagar dado). Se a nova baixa de um ano
   fechado falha e existe um cache vencido dele, o cache vencido serve de reserva e o resumo registra
   `ceap_anos_cache_vencido`. Uma lista de emendas com menos de 80% da anterior é tratada como
   download truncado. Se uma fonte falha, o arquivo e o `fin` dela ficam como estavam.
3. Só as fontes **gravadas** são recarregadas no `fin` (`financas_loader.carregar(chaves=...)`), com a proteção contra
   encolhimento e os erros do Postgres saneados. Nunca se recarrega uma fonte a partir de um arquivo que a extração não
   renovou, porque depois de um deploy esse arquivo é o retrato antigo do git. Se alguma fonte falhou, a execução termina
   com erro (o `systemd` registra) depois de recarregar a outra. Remuneração, patrimônio, doações, certidões e processos não entram.

O script usa o mesmo lock do deploy (`~/.legisdata-deploy/deploy.lock`), esperando até 30 minutos, e o pipeline tem um lock
próprio (`etl/data/.financas.lock`) contra duas atualizações ao mesmo tempo (o timer e o `make daily`, por exemplo). Fora do
contêiner do timer (que já está atrás do lock do script), onde o processo enxerga o `deploy.lock` (`LEGISDATA_DEPLOY_LOCK`, ou
`DEPLOY_STATE_DIR`, ou `~/.legisdata-deploy`), o pipeline também o respeita: com o deploy em andamento, ou sem permissão para
abrir o arquivo, ou com `LEGISDATA_DEPLOY_LOCK` apontando para um arquivo que não existe, a execução FALHA (erro de configuração, exit 1, e o cron registra a etapa como falha); só com o deploy (ou outra atualização) de fato em andamento ela é pulada com sucesso, para não reverter o JSON no meio nem carregar o retrato do git como se fosse dado fresco.
O instalador recusa um `DEPLOY_STATE_DIR` diferente de `~/.legisdata-deploy` (as units instaladas usam esse caminho) e um caminho de projeto com caracteres de controle (o `EnvironmentFile` do systemd não os entende). O deploy também confere que o alvo herdado do ambiente é ancestral de `origin/main`.
Uma carga de CEAP que deixaria sem gasto um ANO que o `fin` já tem (por casa, Câmara ou Senado) é recusada sem tocar no banco, mesmo que a redução do total fique bem acima de 50%: uma carga manual desde 2018 seguida da atualização diária (que começa em 2019) apagaria o ano de 2018 inteiro. `LEGISDATA_ACEITAR_ENCOLHIMENTO=1` na linha de comando libera uma remoção legítima. Para levar ao `fin` arquivos extraídos por um `--ceap` de outra execução sem revogar a posse do timer, use `run_etl --load-economia --recarregar-ceap-emendas --arquivos-frescos`; sem `--arquivos-frescos` recarregar arquivos que a execução não extraiu é tratado como o retrato do git (grava `fresca=false`) e o deploy volta a semeá-los.
Quando um commit endurece a regra de saneamento (`loader_helpers.py` está nas listas do deploy), o primeiro ciclo depois do deploy refaz o download dos anos fechados: o cache por ano antigo é recusado de propósito (`_validar_registro` reaplica o saneamento ao que está em disco) e a atualização pedida pelo deploy o reconstrói; é uma vez só. Antes de
rodar, o script confere que a imagem no ar é a do commit do checkout; depois de um rollback do deploy eles divergem e ele
recusa a execução com uma mensagem clara.

**Interação com o deploy.** Como o `fin` passa a ficar mais novo que os arquivos versionados no git, o deploy decide assim
(função `decidir_financas` em `deploy.sh`, testada com `bash` e `git` de verdade):

- fonte sem dado no `fin` (primeiro deploy, migração ou operação que a esvaziou): o git semeia aquela fonte, e só ela, e o
  deploy dispara a atualização. A CEAP "tem dado" quando as 3 tabelas dela têm linhas; as emendas, quando `fin.emenda` tem;
- `fin` com dados e fonte já assumida pelo timer: **nunca** recarrega essa fonte a partir do git (recarregar apagaria as
  emendas novas, que voltariam com outro `uid`, e a CEAP regrediria até o dia seguinte). "Assumida" é uma linha em
  `etl.execucao` (estágio `CARREGAR`, status `OK`, `parametros = {carga, fresca, origem}`) que a carga de cada fonte grava
  NA MESMA TRANSAÇÃO dos dados, só se gravou linhas; `fresca = true` quando o dado veio de uma extração nova (o timer ou
  `run_etl --ceap`) e `false` quando veio do retrato do git (a semeadura do deploy ou `--recarregar-ceap-emendas`), o que
  revoga a posse: vale a ÚLTIMA linha de cada carga. Essas linhas não podem ser expurgadas como histórico comum, ou o
  deploy volta a semear do git em silêncio (cerca de 2 linhas por dia). Por isso ela volta junto com um `pg_restore` de dump antigo, some se
  a carga falhou (o cache de extração não serve: existe mesmo quando a carga falhou) e não depende de arquivo em disco
  (`git clean -x` não apaga nada). Cada fonte é uma transação: a CEAP entra e fica assumida mesmo que as emendas falhem.
  `run_etl --ceap --load-economia` bem-sucedido também registra as duas. Recarrega só remuneração, patrimônio, doações,
  certidões e processos, e apenas se o commit mudou os arquivos delas, o código da carga, `etl/utils` ou as migrações;
- se o commit mudou a extração ou a carga de CEAP e emendas (qualquer módulo `etl` que elas importam: um teste confere
  as listas de `decidir_financas` contra as importações), o deploy dispara `legisdata-financas.service` na hora (sem
  esperar a madrugada), quando a unit está instalada. Sem a unit, o log do deploy avisa e registra o pedido em
  `~/.legisdata-deploy/financas_pendente`; o `instalar.sh` o cumpre ao ligar o timer;
- `fin` com dados mas fonte que o timer **ainda não carregou** (é o caso do primeiro deploy depois da 3c): o único dado
  novo que existe é o do git, então o deploy a semeia de novo e pede a atualização; assim as regras de saneamento do commit
  chegam ao `fin` sem esperar a madrugada. Por fonte: nenhuma assumida => modo `completa`; só as emendas assumidas =>
  `sem_emendas` (semeia a CEAP e as estáticas, sem reescrever as emendas); só a CEAP assumida => `sem_ceap`;
- a tolerância a uma carga de finanças que falha vale se o `fin` tem dado em QUALQUER das quatro tabelas da CEAP e das
  emendas; a escolha do que semear é por fonte (acima). Uma carga tolerada que falhou também grava `carga` em `financas_pendente` (e a hora da tentativa em
  `financas_carga_tentada`), e o deploy tenta de novo mesmo sem commit novo, no máximo uma vez por hora (`INTERVALO_DA_CARGA`; a tentativa é
  carimbada ANTES da carga, então qualquer falha dela, tolerada ou não, espera o intervalo), até a carga passar; a
  repetição não dispara de novo a atualização diária. O `--dry-run` nunca dispara o serviço, não limpa pendência nem
  carimba tentativa. Um pedido de atualização parado
  (`refrescar`) é cumprido na primeira execução do deploy em que a unit existir, ainda que o commit seja o mesmo. A decisão
  também considera como mudança do timer o `atualizar_financas.sh` e as units `legisdata-financas.*`.

`run_etl --load-economia` (e `make run-load-economia`) usa a MESMA política (`carga_economica.modo_de_semeadura`, que o
`decidir_financas` repete em bash; um teste compara as 16 combinações): só se semeia do git a fonte que o `fin` ainda não
tem ou que o timer ainda não assumiu; as demais ficam só com as cargas estáticas, porque os arquivos do git ficam atrás
da atualização diária e recarregá-los desfaria o trabalho dela. Para recarregar tudo dos arquivos (por exemplo, depois de
regerá-los à mão com `--ceap`), use `run_etl --load-economia --recarregar-ceap-emendas`. Em ambos os casos a carga de
CEAP e emendas registra, na própria transação, de onde veio o dado (extração fresca desta execução ou git). A atualização diária lê a liberação de encolhimento legítimo da mesma
forma que o deploy: `LEGISDATA_ACEITAR_ENCOLHIMENTO=1 ~/.legisdata-deploy/atualizar_financas.sh` na linha de comando (o
script a repassa ao contêiner), nunca exportada no ambiente do timer.

Para decidir se um ano do começo do ano "ainda não foi publicado" (vazio ou 404 até março), a atualização diária junta os
anos que o próprio `fin` já tem (o arquivo processado sozinho não serve: o deploy o devolve ao retrato do git) com os que o
arquivo processado traz (o `fin` sozinho também não: a carga pode ter falhado depois de o arquivo receber o ano); um vazio
em ano que qualquer um dos dois já tem é falha, e o dado não se perde. A extração manual (`run_etl --ceap`) usa o mesmo
cache por ano e a mesma proteção, e só dispara a carga completa (`--load-economia`) se a extração desta execução deu certo.
`--no-cache` baixa tudo de novo, mas continua gravando o cache e mantém a reserva do cache vencido.

**Transição.** A cópia do `deploy.sh` instalada antes desta versão se reexecuta com o script novo sem a variável
`_LEGISDATA_DEPLOY_REPETICAO`: assume 0, o que dispara a atualização diária uma vez a mais numa repetição de carga. Máquinas
de desenvolvimento que rodaram a versão intermediária (marcadores em arquivo) podem apagar `etl/data/.financas_*_carregada`.
As linhas de `etl.execucao` gravadas por versões anteriores deste branch (chave `fonte` em vez de `carga`) continuam valendo:
as duas consultas leem `coalesce(parametros->>'carga', parametros->>'fonte')`, e a linha nova de uma fonte prevalece.

Os contêineres do deploy e da atualização escondem `.env` e `.git/config` (credencial de remote); num worktree, onde `.git` é
arquivo, não há `.git/config` a esconder e a montagem é omitida. O arquivo de ambiente com a senha vai para o
`XDG_RUNTIME_DIR` (tmpfs) quando existe; sem ele, para o diretório de estado (modo 700), e restos de execuções mortas com mais
de uma hora são apagados.

O deploy continua descartando as saídas locais de `etl/data/processed` antes do merge; a atualização diária as gera de novo.
O nome `despesas_ceap_2019_2026.json` é histórico: a partir de 2027 o arquivo também terá dados de 2027.

**Instalação** (uma vez, pelo usuário do servidor, junto do deploy): rodar de novo o `instalar.sh` do commit atual, que
agora também instala o script e as units `legisdata-financas.service/.timer` e liga o timer. O instalador confere o
`systemctl --user` antes de gravar qualquer coisa, mantém o estado do deploy se ele já existe (não marca como implantado um
commit que ainda não subiu) e termina com erro se um timer não ficar ativo:

```bash
cd <diretório do projeto no servidor>
git fetch -q origin
f="$(mktemp)"; git show origin/main:scripts/deploy/instalar.sh >"$f"
bash "$f" origin/main; rm -f "$f"
```

Depois, o `deploy.sh` mantém a cópia do script igual à do commit implantado. Para testar na hora:
`systemctl --user start legisdata-financas.service` e acompanhar com `journalctl --user -u legisdata-financas.service -f`.
Para pausar: `systemctl --user stop legisdata-financas.timer`.

O `make daily` (presença, votações, séries, IPPM e grafo) é outro agendador, ainda sem timer no servidor atual. Se um dia
ele for instalado, a etapa 1d dele já inclui esta atualização (o lock do pipeline impede a execução dupla e, no host do
deploy, ela é pulada quando enxerga o `deploy.lock` ocupado; o `legisdata-diario.service` roda como outro usuário, e para ele respeitar o deploy a unit precisa exportar `LEGISDATA_DEPLOY_LOCK` com um caminho que os dois usuários alcancem, o MESMO que o `deploy.sh` e o `atualizar_financas.sh` usam: os dois scripts leem a variável, com `$ESTADO_DIR/deploy.lock` como padrão, e o `chmod 700` do diretório de estado não vale para um arquivo fora dele) e o
`legisdata-financas.timer` pode ser removido; instale um só dos dois com o mesmo usuário, para o cache e os arquivos de
`etl/data` não ficarem com donos diferentes.

## Limites conhecidos

- Durante as migrações o contêiner antigo ainda atende. Uma migração que apaga tabela (como a 0027) faz as rotas que a
  usavam darem erro até a troca das imagens (segundos).
- O deploy não roda se o CI falhar, e isso é intencional: nenhuma imagem é publicada.

## Deploy que traz a mudança da própria carga (uma vez, na 3b)

O timer executa a cópia instalada em `~/.legisdata-deploy/deploy.sh`. Uma cópia anterior à 3b não tem a reexecução
automática nem a carga da composição do Congresso e da PNAD, então o deploy que traz a 3b, rodado por ela, aplicaria as
migrações e subiria as imagens com essas tabelas vazias (`/analytics/congress-composition` e `/analytics/social-classes`
dariam 404 até o próximo commit). **Antes de mesclar o PR**, instale no servidor o script da branch, a partir do
checkout do projeto:

```bash
git fetch -q origin
git show origin/refactor/db-entrega-3b-curados:scripts/deploy/deploy.sh > ~/.legisdata-deploy/deploy.sh
chmod 755 ~/.legisdata-deploy/deploy.sh
bash -n ~/.legisdata-deploy/deploy.sh && echo ok
```

Depois do merge o deploy roda com o script novo, que dali em diante se atualiza sozinho a cada deploy. Se esquecer o
passo, rode `make run-load-economia` no servidor depois do deploy. Ele semeia do git só a fonte que o `fin` não tem ou que o
timer ainda não assumiu (logo depois da transição, antes da primeira execução do timer, isso é a CEAP e as emendas
inteiras, gravadas como `fresca=false`); a fonte que o timer já assumiu não é desfeita. Ou rode o `python -c` do passo 4.

## Rollback da Entrega 3c (a API deixou de montar `etl/data`)

O `git merge` do deploy traz o `docker-compose.yml` novo antes da verificação de saúde, mas o script guarda o commit anterior (`COMMIT_ANTERIOR`) e, se a verificação falhar, sobe a tag anterior com o `docker-compose.yml` DESSE commit (lido por `git show`), que ainda monta `./etl/data` no contêiner da API. Com isso a imagem 3b volta com o volume de que precisa e as rotas de emendas e a CEAP do dossiê funcionam como antes. Só se o compose do commit anterior não puder ser lido o script usa o atual, e nesse caso a imagem 3b (que lê CEAP e emendas desses arquivos) responde 404 em `/emendas/resumo`, `/emendas/localidade/*` e `/emendas/autor/*` e mostra a CEAP e as emendas do dossiê vazias, sem erro 5xx: corrija para frente (o `fin` já está carregado) ou recoloque temporariamente o volume `./etl/data:/etl_data:ro` no compose.

Uma carga de finanças que falha (JSON malformado, tabela que encolheria a menos da metade) só é tolerada quando o `fin` já tem dados (o script confere se alguma das quatro tabelas, `fin.emenda`, `fin.despesa_cota`, `fin.despesa_cota_fornecedor` e `fin.despesa_cota_resumo`, tem linhas, depois das migrações e antes da carga, e repassa o resultado como `LEGISDATA_FIN_TEM_ALGUM_DADO`; a tolerância vale para a carga `financas`): nesse caso o deploy segue, o erro aparece no log (`{'erro': ...}` no resultado da carga `financas`) e a API nova continua servindo o que já estava em `fin`. No primeiro deploy da 3c (a migração 0031 acabou de criar o `fin` vazio) a falha NÃO é tolerada: o deploy aborta antes do `docker compose up` e o contêiner antigo segue no ar com o volume `./etl/data`; as tabelas novas são aditivas, então abortar nesse ponto é seguro. Para qualquer erro do Postgres, tanto no log da carga individual quanto no erro final, o texto leva só o tipo, a mensagem principal e o nome da restrição (para erro de dado, o SQLSTATE e a coluna), nunca o `DETAIL` com os valores da linha; um arquivo que existe mas tem o tipo errado volta como `{'formato_invalido': 1}`, distinto de `{'arquivo_ausente': 1}`. O `fin` se atualiza no deploy (quando o commit mudou as entradas ou o código da carga), todo dia pela atualização diária de CEAP e emendas (seção abaixo), no ETL completo e em `run_etl --load-economia`. As demais cargas (séries, mandatos, composição, PNAD) continuam abortando o deploy. Depois de uma falha de finanças, corrija o arquivo ou, se a redução for legítima, rode `run_etl --load-economia` (com `LEGISDATA_ACEITAR_ENCOLHIMENTO=1` na linha de comando); o deploy repete a carga sozinho até ela passar. Para aceitar uma redução legítima, rode o deploy uma única vez com a variável na linha de comando (`LEGISDATA_ACEITAR_ENCOLHIMENTO=1 ~/.legisdata-deploy/deploy.sh`); o script a repassa à carga. Nunca a deixe exportada no ambiente do timer nem em arquivo de ambiente: ela desliga a proteção das oito tabelas (as seis cargas, mais fornecedores e resumo da CEAP).
