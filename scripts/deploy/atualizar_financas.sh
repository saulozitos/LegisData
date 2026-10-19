#!/usr/bin/env bash
# Atualização diária das finanças no servidor (timer do systemd do usuário): baixa a CEAP e as emendas oficiais e
# recarrega o schema `fin`. Roda no contêiner da imagem da API que está no ar, com o checkout montado só para leitura
# e apenas `etl/data` gravável (arquivos extraídos e cache da CEAP por ano). Só o ano corrente (e o anterior até março)
# vai à rede; os anos fechados vêm do cache. Falha de extração preserva os arquivos e o `fin` como estavam.
set -Eeuo pipefail

[[ -z "${LEGISDATA_DIR:-}" && -f "$HOME/.legisdata-deploy/ambiente" ]] && . "$HOME/.legisdata-deploy/ambiente"
RAIZ="${LEGISDATA_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ESTADO_DIR="${DEPLOY_STATE_DIR:-$HOME/.legisdata-deploy}"
REDE="${DEPLOY_NETWORK:-legisdata_default}"

log() { printf '%s [financas] %s\n' "$(date '+%F %T')" "$*"; }

# O deploy também mexe em etl/data (descarta as saídas locais antes do merge): nunca os dois ao mesmo tempo. Usa o mesmo
# lock do deploy e espera até 30 minutos; o deploy, ao achar o lock ocupado, tenta de novo na próxima execução do timer.
mkdir -p "$ESTADO_DIR"
exec 9>"$ESTADO_DIR/deploy.lock"
flock -w 1800 9 || { log "deploy em andamento há mais de 30 minutos; tento amanhã"; exit 1; }

set -a
# shellcheck disable=SC1091
. "$RAIZ/.env"
set +a
PG_USER="${POSTGRES_USER:-politica_user}"
PG_DB="${POSTGRES_DB:-politica_db}"

IMAGEM="$(docker inspect --format '{{.Config.Image}}' politica_api)"
# A URL do banco (com a senha) vai por arquivo de ambiente 600, nunca na linha de comando (visível em `ps`)
ENV_BANCO="$(mktemp)"
trap 'rm -f "$ENV_BANCO"' EXIT
chmod 600 "$ENV_BANCO"
URL_BANCO="postgresql+psycopg2://${PG_USER}:${POSTGRES_PASSWORD}@postgres:5432/${PG_DB}"
printf 'DATABASE_URL=%s\nPOSTGRES_PASSWORD=%s\n' "$URL_BANCO" "$POSTGRES_PASSWORD" >"$ENV_BANCO"

log "atualizando CEAP e emendas ($IMAGEM)"
# --user: os arquivos gravados em etl/data ficam do dono do checkout. O lock (descritor 9) não passa para o contêiner.
docker run --rm --network "$REDE" --env-file "$ENV_BANCO" --user "$(id -u):$(id -g)" \
  -e ENVIRONMENT=production -e DB_SSLMODE=disable -e HOME=/tmp \
  -e PYTHONPATH=/repo/backend:/repo --memory 2g --cpus 2 \
  -v "$RAIZ:/repo:ro" -v "$RAIZ/etl/data:/repo/etl/data" -w /app \
  "$IMAGEM" python -m etl.pipelines.financas_atualizacao 9>&-
log "concluído"
