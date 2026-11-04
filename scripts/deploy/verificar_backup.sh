#!/usr/bin/env bash
# Ensaio de restauração: prova que o backup mais recente do deploy (pg_dump em ~/backups) restaura de verdade.
#
# Restaura o dump num banco descartável dentro do contêiner do Postgres, confere a revisão do Alembic e se as tabelas
# principais têm linhas, e apaga o banco descartável. Não toca no banco de produção. Rode de tempos em tempos (por
# exemplo, uma vez por mês): um backup que nunca foi restaurado não é backup.
#
# Uso: scripts/deploy/verificar_backup.sh [arquivo.dump]   (sem argumento, usa o mais recente de $BACKUP_DIR)
set -euo pipefail

[[ -z "${LEGISDATA_DIR:-}" && -f "$HOME/.legisdata-deploy/ambiente" ]] && . "$HOME/.legisdata-deploy/ambiente"
RAIZ="${LEGISDATA_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
CONTEINER="${POSTGRES_CONTAINER:-politica_postgres}"

log() { printf '%s [backup] %s\n' "$(date '+%F %T')" "$*"; }

set -a
# shellcheck disable=SC1091
. "$RAIZ/.env"
set +a
PG_USER="${POSTGRES_USER:-politica_user}"

# shellcheck disable=SC2012
DUMP="${1:-$(ls -1t "$BACKUP_DIR"/legisdata_*.dump 2>/dev/null | head -n 1 || true)}"
if [[ -z "$DUMP" || ! -s "$DUMP" ]]; then
  log "nenhum backup encontrado em $BACKUP_DIR"
  exit 1
fi
log "restaurando $DUMP"

BANCO="verificacao_restore_$$"
limpar() { docker exec "$CONTEINER" dropdb -U "$PG_USER" --if-exists "$BANCO" >/dev/null 2>&1 || true; }
trap limpar EXIT

docker exec "$CONTEINER" createdb -U "$PG_USER" "$BANCO"
# o descartável é uma cópia completa da produção: enquanto o ensaio roda, só o dono conecta
docker exec "$CONTEINER" psql -U "$PG_USER" -d postgres -qc "REVOKE CONNECT ON DATABASE \"$BANCO\" FROM PUBLIC"
# --no-owner e --no-acl: o banco descartável pertence a quem o criou e não repete os privilégios da produção; o conteúdo é
# o que importa (as funções SECURITY DEFINER rodam aqui como esse dono, que não é o papel dono dos derivados)
docker exec -i "$CONTEINER" pg_restore -U "$PG_USER" -d "$BANCO" --no-owner --no-acl <"$DUMP"

consulta() { docker exec "$CONTEINER" psql -U "$PG_USER" -d "$BANCO" -Atc "$1"; }
REVISAO="$(consulta 'SELECT version_num FROM alembic_version')"
PESSOAS="$(consulta 'SELECT count(*) FROM core.pessoa')"
if [[ -z "$REVISAO" || "$PESSOAS" -lt 1 ]]; then
  log "FALHOU: restaurado sem revisão do Alembic ou sem pessoas (revisão='$REVISAO', pessoas=$PESSOAS)"
  exit 1
fi
log "OK: revisão $REVISAO, $PESSOAS pessoas em core.pessoa; banco descartável removido"
