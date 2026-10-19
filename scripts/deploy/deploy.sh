#!/usr/bin/env bash
# Deploy automático do LegisData no servidor: roda a cada poucos minutos (timer do systemd do usuário) e, quando há
# commit novo na main com as imagens publicadas no GHCR, faz nesta ordem:
#   1. backup do banco (pg_dump) -> 2. atualiza o código (ff-only) -> 3. migrações -> 4. carga das séries econômicas
#   -> 5. sobe as imagens novas -> 6. confere a saúde; se falhar, volta para as imagens anteriores.
# O banco só é tocado depois do backup, e o estado só avança quando tudo termina bem (a próxima execução tenta de novo).
set -Eeuo pipefail

# LEGISDATA_DIR aponta para o checkout do projeto. O timer o recebe do systemd; numa execução manual vem do mesmo arquivo.
[[ -z "${LEGISDATA_DIR:-}" && -f "$HOME/.legisdata-deploy/ambiente" ]] && . "$HOME/.legisdata-deploy/ambiente"
RAIZ="${LEGISDATA_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ESTADO_DIR="${DEPLOY_STATE_DIR:-$HOME/.legisdata-deploy}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
REDE="${DEPLOY_NETWORK:-legisdata_default}"
REGISTRO="${DEPLOY_REGISTRY:-ghcr.io/saulozitos}"
GUARDAR_BACKUPS="${DEPLOY_KEEP_BACKUPS:-14}"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

log() { printf '%s [deploy] %s\n' "$(date '+%F %T')" "$*"; }

mkdir -p "$ESTADO_DIR" "$BACKUP_DIR"
# Os dumps têm o banco inteiro: só o dono lê (inclusive os de execuções anteriores).
chmod 700 "$BACKUP_DIR"
chmod 600 "$BACKUP_DIR"/legisdata_*.dump 2>/dev/null || true
# Depois de se reexecutar (abaixo) o lock já está aberto no descritor 9, herdado do processo anterior.
if [[ -z "${_LEGISDATA_DEPLOY_REEXEC:-}" ]]; then
  exec 9>"$ESTADO_DIR/deploy.lock"
  flock -n 9 || { log "outra execução em andamento"; exit 0; }
fi

cd "$RAIZ"
git fetch -q origin main
# Numa reexecução o alvo é o da primeira execução: o script e o commit implantado não podem divergir.
ALVO="${_LEGISDATA_DEPLOY_ALVO:-$(git rev-parse origin/main)}"
TAG="${ALVO:0:7}"
ATUAL="$(cat "$ESTADO_DIR/ultimo_sha" 2>/dev/null || true)"
if [[ "$ATUAL" == "$ALVO" ]]; then
  exit 0
fi

# As imagens são publicadas só depois do CI passar; sem elas não há o que implantar ainda.
for img in legisdata-backend legisdata-frontend; do
  if ! docker pull -q "$REGISTRO/$img:$TAG" >/dev/null 2>&1; then
    log "imagem $img:$TAG ainda não publicada (CI em andamento ou falhou); tento de novo na próxima"
    exit 0
  fi
done
log "implantando $TAG (anterior: ${ATUAL:0:7})"
[[ $DRY_RUN -eq 1 ]] && { log "dry-run: imagens existem, nada alterado"; exit 0; }

# O timer executa a cópia instalada em $ESTADO_DIR, que pode ser mais antiga que o script da main. Antes de mexer em
# qualquer coisa, passa a usar o script do commit que será implantado (reexecuta uma única vez).
if [[ -z "${_LEGISDATA_DEPLOY_REEXEC:-}" ]] && git cat-file -e "$ALVO:scripts/deploy/deploy.sh" 2>/dev/null; then
  git show "$ALVO:scripts/deploy/deploy.sh" >"$ESTADO_DIR/deploy.sh.novo"
  if ! bash -n "$ESTADO_DIR/deploy.sh.novo"; then
    log "script de deploy do commit $TAG com erro de sintaxe; mantenho o atual"
  elif ! cmp -s "$ESTADO_DIR/deploy.sh.novo" "$ESTADO_DIR/deploy.sh"; then
    chmod 755 "$ESTADO_DIR/deploy.sh.novo" && mv "$ESTADO_DIR/deploy.sh.novo" "$ESTADO_DIR/deploy.sh"
    log "script de deploy atualizado para o da main; reexecutando"
    _LEGISDATA_DEPLOY_REEXEC=1 _LEGISDATA_DEPLOY_ALVO="$ALVO" exec "$ESTADO_DIR/deploy.sh" "$@"
  fi
  rm -f "$ESTADO_DIR/deploy.sh.novo"
fi

set -a
# shellcheck disable=SC1091
. "$RAIZ/.env"
set +a
PG_USER="${POSTGRES_USER:-politica_user}"
PG_DB="${POSTGRES_DB:-politica_db}"

# 1. backup antes de qualquer alteração (formato custom, restaurável com pg_restore)
# Uma tentativa anterior deste mesmo commit que falhou já deixou o backup de antes das migrações: reaproveita-o, para
# um deploy quebrado repetido pelo timer não encher a rotação com dumps de um banco já migrado e apagar o bom.
DUMP="$(ls -1t "$BACKUP_DIR"/legisdata_"${TAG}"_*.dump 2>/dev/null | head -n 1 || true)"  # *.dump.parcial não casa
if [[ -n "$DUMP" && -s "$DUMP" ]]; then
  log "backup deste commit já existe, reaproveitado: $DUMP"
else
  DUMP="$BACKUP_DIR/legisdata_${TAG}_$(date +%Y%m%d_%H%M%S).dump"
  # O dump só ganha o nome definitivo depois de terminar bem; um pg_dump interrompido nunca vira "backup bom".
  rm -f "$BACKUP_DIR"/*.dump.parcial
  # umask só neste subshell: o resto do script (git merge, arquivos do checkout) mantém as permissões normais
  if ! (umask 077 && docker exec politica_postgres pg_dump -U "$PG_USER" -d "$PG_DB" -Fc >"$DUMP.parcial") ||
    [[ ! -s "$DUMP.parcial" ]]; then
    log "backup falhou ou veio vazio, abortando"
    rm -f "$DUMP.parcial"
    exit 1
  fi
  mv "$DUMP.parcial" "$DUMP"
  log "backup: $DUMP ($(du -h "$DUMP" | cut -f1))"
fi
# shellcheck disable=SC2012
ls -1t "$BACKUP_DIR"/legisdata_*.dump | tail -n +"$((GUARDAR_BACKUPS + 1))" | xargs -r rm -f

# 2. código (compose, dados do ETL, scripts). O cron diário regrava arquivos versionados de etl/data/processed no
# checkout; essas mudanças locais impediriam o fast-forward. Os arquivos voltam ao commit e o próximo cron os atualiza.
if ! git diff --quiet -- etl/data/processed || [[ -n "$(git ls-files --others --exclude-standard -- etl/data/processed)" ]]; then
  log "descartando saídas do cron em etl/data/processed antes de atualizar o código:"
  { git diff --name-only -- etl/data/processed; git ls-files --others --exclude-standard -- etl/data/processed; } |
    while read -r arquivo; do log "  $arquivo"; done
  git checkout -q -- etl/data/processed
  git clean -fdq -- etl/data/processed
fi
COMMIT_ANTERIOR="$(git rev-parse HEAD)"  # o compose deste commit é o que o rollback precisa (o novo pode ter outros volumes)
git merge --ff-only -q "$ALVO"

# A URL do banco (com a senha) vai por arquivo de ambiente 600, nunca na linha de comando (visível em `ps`)
URL_BANCO="postgresql+psycopg2://${PG_USER}:${POSTGRES_PASSWORD}@postgres:5432/${PG_DB}"
ENV_BANCO="$(mktemp)"
trap 'rm -f "$ENV_BANCO"' EXIT
chmod 600 "$ENV_BANCO"
printf 'ALEMBIC_DATABASE_URL=%s\nDATABASE_URL=%s\nPOSTGRES_PASSWORD=%s\n' "$URL_BANCO" "$URL_BANCO" "$POSTGRES_PASSWORD" >"$ENV_BANCO"
um_comando() { # roda um comando Python no contêiner da imagem nova, na rede do compose
  # LEGISDATA_ACEITAR_ENCOLHIMENTO=1 libera, só nesta execução, uma carga de finanças que reduz uma tabela a menos da metade
  docker run --rm --network "$REDE" --env-file "$ENV_BANCO" -e ENVIRONMENT=production -e DB_SSLMODE=disable \
    -e LEGISDATA_ACEITAR_ENCOLHIMENTO="${LEGISDATA_ACEITAR_ENCOLHIMENTO:-}" \
    -e LEGISDATA_FIN_TEM_DADOS="${LEGISDATA_FIN_TEM_DADOS:-}" -e LEGISDATA_FIN_PULAR="${LEGISDATA_FIN_PULAR:-}" \
    -e PYTHONPATH=/repo/backend:/repo -v "$RAIZ:/repo:ro" -w /app "$REGISTRO/legisdata-backend:$TAG" "$@" 9>&-
}

# 3. migrações e 4. carga das séries econômicas e da curadoria (idempotentes)
log "migrações"
docker run --rm --network "$REDE" --env-file "$ENV_BANCO" -e ENVIRONMENT=production -e DB_SSLMODE=disable \
  "$REGISTRO/legisdata-backend:$TAG" alembic upgrade head 9>&-
# Só depois que o schema `eco` existe (a migração 0025 em diante) e o código da carga está no checkout.
TEM_ECO="$(docker exec politica_postgres psql -U "$PG_USER" -d "$PG_DB" -tAc "select to_regclass('eco.observacao') is not null")"
if [[ "$TEM_ECO" == "t" && -f "$RAIZ/etl/pipelines/carga_economica.py" ]]; then
  log "carga de séries, mandatos, composição do Congresso e PNAD"
  # Finanças só é tolerada se `fin` já tem dados: aí a API nova segue servindo o que já estava lá. No primeiro deploy
  # (fin recém-criado e vazio) uma falha da carga aborta antes do `compose up` e o contêiner antigo continua no ar.
  LEGISDATA_FIN_TEM_DADOS="$(docker exec politica_postgres psql -U "$PG_USER" -d "$PG_DB" -tAc "select exists(select 1 from fin.emenda) or exists(select 1 from fin.despesa_cota)")"
  export LEGISDATA_FIN_TEM_DADOS
  # A atualização diária (legisdata-financas.timer) mantém CEAP e emendas do `fin` mais novas que os arquivos versionados.
  # Por isso o deploy só recarrega as finanças quando o `fin` está vazio ou quando este commit mudou os arquivos de
  # entrada ou o código da carga; senão devolveria o banco ao conteúdo dos arquivos do git, mais antigo.
  LEGISDATA_FIN_PULAR=""
  ENTRADAS_FINANCAS=(
    etl/data/processed/despesas_ceap_2019_2026.json etl/data/processed/emendas_parlamentares_2019_2026.json
    etl/data/processed/remuneracao_parlamentares.json etl/data/processed/declaracoes_patrimonio.json
    etl/data/processed/tse_doacoes_campanha.json etl/data/processed/certidoes_tse.json
    etl/pipelines/financas_loader.py etl/pipelines/loader_helpers.py etl/pipelines/pessoa_resolver.py
    backend/alembic/versions
  )
  if [[ "$LEGISDATA_FIN_TEM_DADOS" == "t" && -n "$ATUAL" ]] && git cat-file -e "$ATUAL^{commit}" 2>/dev/null &&
    git diff --quiet "$ATUAL" "$ALVO" -- "${ENTRADAS_FINANCAS[@]}"; then
    LEGISDATA_FIN_PULAR=1
    log "finanças: este commit não mudou os arquivos nem o código da carga; mantenho o fin atual"
  fi
  export LEGISDATA_FIN_PULAR
  um_comando python -c "
import os
from app.core.database import engine
from etl.pipelines.carga_economica import CARGAS, carregar_tudo
toleradas = ('financas',) if os.environ.get('LEGISDATA_FIN_TEM_DADOS') == 't' else ()
chaves = [c[0] for c in CARGAS if not (c[0] == 'financas' and os.environ.get('LEGISDATA_FIN_PULAR') == '1')]
for chave, resultado in carregar_tudo(engine, chaves=chaves, toleradas=toleradas).items():
    print(chave, resultado)
"
fi

# 5. imagens novas
ANTERIOR="$(cat "$ESTADO_DIR/ultima_tag" 2>/dev/null || docker inspect --format '{{.Config.Image}}' politica_api | sed 's/.*://')"
export IMAGE_TAG="$TAG"
docker compose up -d --no-build backend frontend

# 6. saúde; sem saúde em 3 minutos, volta para a tag anterior
for _ in $(seq 1 36); do
  estado="$(docker inspect --format '{{.State.Health.Status}}' politica_api 2>/dev/null || echo starting)"
  [[ "$estado" == "healthy" ]] && break
  sleep 5
done
if [[ "$estado" != "healthy" ]]; then
  log "API não ficou saudável ($estado); voltando para $ANTERIOR (backup: $DUMP)"
  # com o compose do commit anterior (o novo pode ter tirado volumes de que a imagem antiga precisa); se não der para
  # lê-lo, com o compose atual
  if git show "$COMMIT_ANTERIOR:docker-compose.yml" >"$ENV_BANCO.compose" 2>/dev/null; then
    IMAGE_TAG="$ANTERIOR" docker compose --project-directory "$RAIZ" -f "$ENV_BANCO.compose" up -d --no-build backend frontend
    rm -f "$ENV_BANCO.compose"
  else
    IMAGE_TAG="$ANTERIOR" docker compose up -d --no-build backend frontend
  fi
  exit 1
fi

# O timer executa a cópia em $ESTADO_DIR/deploy.sh (sobrevive a um `git merge` que mexa no script); atualiza-a aqui.
if [[ -f "$RAIZ/scripts/deploy/deploy.sh" ]] && ! cmp -s "$RAIZ/scripts/deploy/deploy.sh" "$ESTADO_DIR/deploy.sh"; then
  install -m 755 "$RAIZ/scripts/deploy/deploy.sh" "$ESTADO_DIR/deploy.sh.novo" && mv "$ESTADO_DIR/deploy.sh.novo" "$ESTADO_DIR/deploy.sh"
fi
# O timer das finanças executa a cópia em $ESTADO_DIR/atualizar_financas.sh; a mantém igual à do commit implantado.
if [[ -f "$RAIZ/scripts/deploy/atualizar_financas.sh" ]] && bash -n "$RAIZ/scripts/deploy/atualizar_financas.sh" &&
  ! cmp -s "$RAIZ/scripts/deploy/atualizar_financas.sh" "$ESTADO_DIR/atualizar_financas.sh"; then
  install -m 755 "$RAIZ/scripts/deploy/atualizar_financas.sh" "$ESTADO_DIR/atualizar_financas.sh.novo" &&
    mv "$ESTADO_DIR/atualizar_financas.sh.novo" "$ESTADO_DIR/atualizar_financas.sh"
fi
echo "$TAG" >"$ESTADO_DIR/ultima_tag"
echo "$ALVO" >"$ESTADO_DIR/ultimo_sha"
docker image prune -f >/dev/null 2>&1 || true
log "deploy de $TAG concluído"
