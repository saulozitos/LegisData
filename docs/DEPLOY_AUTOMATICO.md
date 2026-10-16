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
   4. Carga das séries econômicas, dos mandatos presidenciais, da composição do Congresso e da PNAD
      (`economia_loader`, `presidencia_loader`, `composicao_loader`, `pnad_loader`), se o schema `eco` já existe.
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
