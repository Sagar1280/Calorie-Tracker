#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."
mkdir -p backups

stamp="$(date -u +%Y%m%d_%H%M%S)"
target="backups/calorie_${stamp}.dump"
tmp="${target}.tmp"
trap 'rm -f "$tmp"' EXIT

docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-acl' > "$tmp"
mv "$tmp" "$target"
trap - EXIT

ls -1t backups/calorie_*.dump 2>/dev/null | tail -n +15 | xargs -r rm -f

echo "Backup written to $target"
