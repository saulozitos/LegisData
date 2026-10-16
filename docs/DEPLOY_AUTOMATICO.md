# Deploy automático no servidor

Todo commit que entra na `main` e passa no CI é implantado sozinho em https://legisdata.top/.

## Como funciona

1. O workflow `Build & Publish Containers` publica as imagens `legisdata-backend` e `legisdata-frontend` no GHCR com as tags
   `latest` e o SHA curto do commit (7 caracteres), mas só depois do `CI Quality Gate` passar.
2. No servidor, um timer do systemd **do usuário** (`legisdata-deploy.timer`, a cada 2 minutos) roda
   `scripts/deploy/deploy.sh`. Sem commit novo ou sem imagens publicadas para o SHA, ele sai sem fazer nada.
3. Com commit novo e imagens prontas, o script faz, nesta ordem:
   1. `pg_dump` (formato custom) em `~/backups`, guardando os 14 mais recentes. Backup vazio aborta o deploy.
   2. `git merge --ff-only origin/main` no checkout do projeto (compose, dados do ETL e scripts).
   3. `alembic upgrade head` num contêiner da imagem nova, na rede do compose.
   4. Carga das séries econômicas e dos mandatos presidenciais (`economia_loader`, `presidencia_loader`), se o schema
      `eco` já existe. É idempotente.
   5. `IMAGE_TAG=<sha> docker compose up -d --no-build backend frontend`.
   6. Espera a API ficar saudável por até 3 minutos. Se não ficar, volta para a tag anterior e o estado não avança (a
      próxima execução tenta de novo). O banco já migrado não volta atrás: restaure o backup se preciso.
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
