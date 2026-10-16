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
exec 9>"$ESTADO_DIR/deploy.lock"
flock -n 9 || { log "outra execução em andamento"; exit 0; }

cd "$RAIZ"
git fetch -q origin main
ALVO="$(git rev-parse origin/main)"
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

set -a
# shellcheck disable=SC1091
. "$RAIZ/.env"
set +a
PG_USER="${POSTGRES_USER:-politica_user}"
PG_DB="${POSTGRES_DB:-politica_db}"

# 1. backup antes de qualquer alteração (formato custom, restaurável com pg_restore)
DUMP="$BACKUP_DIR/legisdata_${TAG}_$(date +%Y%m%d_%H%M%S).dump"
docker exec politica_postgres pg_dump -U "$PG_USER" -d "$PG_DB" -Fc >"$DUMP"
[[ -s "$DUMP" ]] || { log "backup vazio, abortando"; rm -f "$DUMP"; exit 1; }
log "backup: $DUMP ($(du -h "$DUMP" | cut -f1))"
# shellcheck disable=SC2012
ls -1t "$BACKUP_DIR"/legisdata_*.dump | tail -n +"$((GUARDAR_BACKUPS + 1))" | xargs -r rm -f

# 2. código (compose, dados do ETL, scripts)
git merge --ff-only -q origin/main

URL_BANCO="postgresql+psycopg2://${PG_USER}:${POSTGRES_PASSWORD}@postgres:5432/${PG_DB}"
um_comando() { # roda um comando Python no contêiner da imagem nova, na rede do compose
  docker run --rm --network "$REDE" -e ENVIRONMENT=production -e POSTGRES_PASSWORD -e DB_SSLMODE=disable \
    -e ALEMBIC_DATABASE_URL="$URL_BANCO" -e DATABASE_URL="$URL_BANCO" -e PYTHONPATH=/repo/backend:/repo \
    -v "$RAIZ:/repo:ro" -w /app "$REGISTRO/legisdata-backend:$TAG" "$@"
}

# 3. migrações e 4. carga das séries econômicas (idempotentes)
log "migrações"
docker run --rm --network "$REDE" -e ENVIRONMENT=production -e POSTGRES_PASSWORD -e DB_SSLMODE=disable \
  -e ALEMBIC_DATABASE_URL="$URL_BANCO" -e DATABASE_URL="$URL_BANCO" "$REGISTRO/legisdata-backend:$TAG" alembic upgrade head
# Só depois que o schema `eco` existe (a migração 0025 em diante) e o código da carga está no checkout.
TEM_ECO="$(docker exec politica_postgres psql -U "$PG_USER" -d "$PG_DB" -tAc "select to_regclass('eco.observacao') is not null")"
if [[ "$TEM_ECO" == "t" && -f "$RAIZ/etl/pipelines/economia_loader.py" ]]; then
  log "carga de séries e mandatos presidenciais"
  um_comando python -c "
from app.core.database import engine
from etl.pipelines.economia_loader import carregar as series
from etl.pipelines.presidencia_loader import carregar as presidentes
print('séries:', len(series(engine)), 'presidentes:', presidentes(engine))
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
  IMAGE_TAG="$ANTERIOR" docker compose up -d --no-build backend frontend
  exit 1
fi

# O timer executa a cópia em $ESTADO_DIR/deploy.sh (sobrevive a um `git merge` que mexa no script); atualiza-a aqui.
if [[ -f "$RAIZ/scripts/deploy/deploy.sh" ]] && ! cmp -s "$RAIZ/scripts/deploy/deploy.sh" "$ESTADO_DIR/deploy.sh"; then
  install -m 755 "$RAIZ/scripts/deploy/deploy.sh" "$ESTADO_DIR/deploy.sh.novo" && mv "$ESTADO_DIR/deploy.sh.novo" "$ESTADO_DIR/deploy.sh"
fi
echo "$TAG" >"$ESTADO_DIR/ultima_tag"
echo "$ALVO" >"$ESTADO_DIR/ultimo_sha"
docker image prune -f >/dev/null 2>&1 || true
log "deploy de $TAG concluído"
