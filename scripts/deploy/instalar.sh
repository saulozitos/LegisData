#!/usr/bin/env bash
# Instala o deploy automático no servidor, sem sudo e sem deixar arquivos no checkout.
#   uso (dentro do checkout do projeto):  git fetch -q origin
#                                          git show <ref>:scripts/deploy/instalar.sh > /tmp/instalar.sh
#                                          bash /tmp/instalar.sh <ref>        # ex.: origin/main
# Os arquivos vêm de `git show <ref>:...`, então o checkout não é alterado. Pode rodar de novo (idempotente).
set -Eeuo pipefail

REF="${1:-origin/main}"
RAIZ="$(git rev-parse --show-toplevel)"
DEST="$HOME/.legisdata-deploy"
UNITS="$HOME/.config/systemd/user"

echo "==> projeto: o checkout atual; ref: $REF"
git -C "$RAIZ" cat-file -e "$REF:scripts/deploy/deploy.sh" || { echo "ref sem scripts/deploy/deploy.sh (rode git fetch origin antes)"; exit 1; }

mkdir -p "$DEST" "$UNITS" "$HOME/backups"
echo "LEGISDATA_DIR=$RAIZ" >"$DEST/ambiente" && chmod 600 "$DEST/ambiente"
git -C "$RAIZ" show "$REF:scripts/deploy/deploy.sh" >"$DEST/deploy.sh" && chmod 755 "$DEST/deploy.sh"
git -C "$RAIZ" show "$REF:scripts/deploy/atualizar_financas.sh" >"$DEST/atualizar_financas.sh" && chmod 755 "$DEST/atualizar_financas.sh"
for u in legisdata-deploy.service legisdata-deploy.timer legisdata-financas.service legisdata-financas.timer; do
  git -C "$RAIZ" show "$REF:scripts/systemd/$u" >"$UNITS/$u"
done

echo "==> marcando o que já roda como implantado"
git -C "$RAIZ" fetch -q origin main
git -C "$RAIZ" rev-parse origin/main >"$DEST/ultimo_sha"
docker inspect politica_api --format '{{.Config.Image}}' | sed 's/.*://' >"$DEST/ultima_tag"

echo "==> teste sem alterar nada (dry-run)"
"$DEST/deploy.sh" --dry-run && echo "dry-run ok"

echo "==> parando o Watchtower (ele trocaria a API sem backup)"
docker rm -f politica_watchtower >/dev/null 2>&1 || true

echo "==> ligando o timer"
systemctl --user daemon-reload
systemctl --user enable --now legisdata-deploy.timer
systemctl --user enable --now legisdata-financas.timer
loginctl enable-linger "$USER" 2>/dev/null || echo "AVISO: enable-linger precisa de permissão; o timer só roda com sessão aberta"
systemctl --user list-timers legisdata-deploy.timer legisdata-financas.timer --no-pager
echo "==> pronto. Acompanhe com: journalctl --user -u legisdata-deploy.service -f"
echo "    e a atualização diária das finanças com: journalctl --user -u legisdata-financas.service -f"
