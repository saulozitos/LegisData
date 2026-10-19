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
      (CEAP, emendas, remuneração e dados do TSE) (`economia_loader`, `presidencia_loader`, `composicao_loader`,
      `pnad_loader`, `financas_loader`), se o schema `eco` já existe.
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
git show origin/main:scripts/deploy/instalar.sh > /tmp/instalar.sh
bash /tmp/instalar.sh origin/main
```

O instalador grava o ambiente, instala o script e as units, marca o commit atual como já implantado, roda um dry-run,
remove o Watchtower e liga o timer. Pode ser executado de novo.

## Operação

- Ver o último ciclo: `journalctl --user -u legisdata-deploy.service -n 50`.
- Rodar na hora: `systemctl --user start legisdata-deploy.service`. Testar sem alterar nada: `~/.legisdata-deploy/deploy.sh --dry-run`.
- Pausar: `systemctl --user stop legisdata-deploy.timer`.
- Voltar uma versão: `IMAGE_TAG=<sha anterior> docker compose up -d --no-build backend frontend` (e restaurar o dump em
  `~/backups` se a migração mudou o schema).
- Restaurar um backup: `docker exec -i politica_postgres pg_restore -U politica_user -d politica_db --clean --if-exists < ~/backups/<arquivo>.dump`.

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
   (nunca "gasto zero"). Em janeiro, o arquivo do ano novo que a Câmara ainda não publicou (404) não derruba a CEAP: o ano
   fica de fora e o resumo registra `ceap_anos_sem_arquivo`. Uma lista de emendas com menos de 80% da anterior é tratada como
   download truncado. Se uma fonte falha, o arquivo e o `fin` dela ficam como estavam.
3. Só as fontes **gravadas** são recarregadas no `fin` (`financas_loader.carregar(chaves=...)`), com a proteção contra
   encolhimento e os erros do Postgres saneados. Nunca se recarrega uma fonte a partir de um arquivo que a extração não
   renovou, porque depois de um deploy esse arquivo é o retrato antigo do git. Se alguma fonte falhou, a execução termina
   com erro (o `systemd` registra) depois de recarregar a outra. Remuneração, patrimônio, doações e certidões não entram.

O script usa o mesmo lock do deploy (`~/.legisdata-deploy/deploy.lock`), esperando até 30 minutos, e o pipeline tem um lock
próprio (`etl/data/.financas.lock`) contra duas atualizações ao mesmo tempo (o timer e o `make daily`, por exemplo). Antes de
rodar, o script confere que a imagem no ar é a do commit do checkout; depois de um rollback do deploy eles divergem e ele
recusa a execução com uma mensagem clara.

**Interação com o deploy.** Como o `fin` passa a ficar mais novo que os arquivos versionados no git, o deploy decide assim
(função `decidir_financas` em `deploy.sh`, testada com `bash` e `git` de verdade):

- `fin` sem dados (primeiro deploy, ou migração que o esvaziou): semeia tudo dos arquivos do git e dispara a atualização;
- `fin` com dados: **nunca** recarrega CEAP e emendas a partir do git (recarregar apagaria as emendas novas, que voltariam
  com outro `uid`, e a CEAP regrediria até o dia seguinte). Recarrega só remuneração, patrimônio, doações e certidões, e
  apenas se o commit mudou os arquivos delas, o código da carga, `etl/utils` ou as migrações;
- se o commit mudou a extração ou a carga de CEAP e emendas, o deploy dispara `legisdata-financas.service` na hora (sem
  esperar a madrugada), quando a unit está instalada. Sem a unit, o log do deploy avisa que CEAP e emendas só se atualizam
  com o timer.

O deploy continua descartando as saídas locais de `etl/data/processed` antes do merge; a atualização diária as gera de novo.
O nome `despesas_ceap_2019_2026.json` é histórico: a partir de 2027 o arquivo também terá dados de 2027.

**Instalação** (uma vez, pelo usuário do servidor, junto do deploy): rodar de novo o `instalar.sh` do commit atual, que
agora também instala o script e as units `legisdata-financas.service/.timer` e liga o timer. O instalador confere o
`systemctl --user` antes de gravar qualquer coisa, mantém o estado do deploy se ele já existe (não marca como implantado um
commit que ainda não subiu) e termina com erro se um timer não ficar ativo:

```bash
cd <diretório do projeto no servidor>
git fetch -q origin
git show origin/main:scripts/deploy/instalar.sh > /tmp/instalar.sh
bash /tmp/instalar.sh origin/main
```

Depois, o `deploy.sh` mantém a cópia do script igual à do commit implantado. Para testar na hora:
`systemctl --user start legisdata-financas.service` e acompanhar com `journalctl --user -u legisdata-financas.service -f`.
Para pausar: `systemctl --user stop legisdata-financas.timer`.

O `make daily` (presença, votações, séries, IPPM e grafo) é outro agendador, ainda sem timer no servidor atual. Se um dia
ele for instalado, a etapa 1d dele já inclui esta atualização (o lock do pipeline impede a execução dupla) e o
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
passo, rode `make run-load-economia` no servidor depois do deploy, ou o `python -c` do passo 4 do script.

## Rollback da Entrega 3c (a API deixou de montar `etl/data`)

O `git merge` do deploy traz o `docker-compose.yml` novo antes da verificação de saúde, mas o script guarda o commit anterior (`COMMIT_ANTERIOR`) e, se a verificação falhar, sobe a tag anterior com o `docker-compose.yml` DESSE commit (lido por `git show`), que ainda monta `./etl/data` no contêiner da API. Com isso a imagem 3b volta com o volume de que precisa e as rotas de emendas e a CEAP do dossiê funcionam como antes. Só se o compose do commit anterior não puder ser lido o script usa o atual, e nesse caso a imagem 3b (que lê CEAP e emendas desses arquivos) responde 404 em `/emendas/resumo`, `/emendas/localidade/*` e `/emendas/autor/*` e mostra a CEAP e as emendas do dossiê vazias, sem erro 5xx: corrija para frente (o `fin` já está carregado) ou recoloque temporariamente o volume `./etl/data:/etl_data:ro` no compose.

Uma carga de finanças que falha (JSON malformado, tabela que encolheria a menos da metade) só é tolerada quando o `fin` já tem dados (o script confere que `fin.emenda` E `fin.despesa_cota` têm linhas, depois das migrações e antes da carga, e repassa o resultado como `LEGISDATA_FIN_TEM_DADOS`; a tolerância vale para as cargas `financas` e `financas_estaticas`): nesse caso o deploy segue, o erro aparece no log (`{'erro': ...}` no resultado da carga `financas`) e a API nova continua servindo o que já estava em `fin`. No primeiro deploy da 3c (a migração 0031 acabou de criar o `fin` vazio) a falha NÃO é tolerada: o deploy aborta antes do `docker compose up` e o contêiner antigo segue no ar com o volume `./etl/data`; as tabelas novas são aditivas, então abortar nesse ponto é seguro. Para qualquer erro do Postgres, tanto no log da carga individual quanto no erro final, o texto leva só o tipo, a mensagem principal e o nome da restrição (para erro de dado, o SQLSTATE e a coluna), nunca o `DETAIL` com os valores da linha; um arquivo que existe mas tem o tipo errado volta como `{'formato_invalido': 1}`, distinto de `{'arquivo_ausente': 1}`. O `fin` se atualiza no deploy (quando o commit mudou as entradas ou o código da carga), todo dia pela atualização diária de CEAP e emendas (seção abaixo), no ETL completo e em `run_etl --load-economia`. As demais cargas (séries, mandatos, composição, PNAD) continuam abortando o deploy. Depois de uma falha de finanças, corrija o arquivo ou, se a redução for legítima, rode `run_etl --load-economia`. Para aceitar uma redução legítima, rode o deploy uma única vez com a variável na linha de comando (`LEGISDATA_ACEITAR_ENCOLHIMENTO=1 ~/.legisdata-deploy/deploy.sh`); o script a repassa à carga. Nunca a deixe exportada no ambiente do timer nem em arquivo de ambiente: ela desliga a proteção das oito tabelas (as seis cargas, mais fornecedores e resumo da CEAP).
