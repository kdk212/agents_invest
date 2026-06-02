#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_URL="${UPSTREAM_URL:-https://github.com/dragon1086/prism-insight.git}"
UPSTREAM_BRANCH="${UPSTREAM_BRANCH:-main}"
PREFIX="${PREFIX:-prism-insight}"
BRANCH_NAME="${BRANCH_NAME:-integrate-prism-insight}"

step() {
  printf '\n==> %s\n' "$1"
}

if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "현재 폴더가 Git 저장소가 아닙니다. agents_invest 저장소 루트에서 실행하세요." >&2
  exit 2
fi

if [ -n "$(git status --short)" ]; then
  echo "현재 작업트리에 변경사항이 있습니다:" >&2
  git status --short >&2
  echo "먼저 변경사항을 커밋하거나 별도 브랜치에서 정리한 뒤 다시 실행하세요." >&2
  exit 2
fi

step "Create integration branch"
current_branch="$(git branch --show-current)"
if [ "$current_branch" != "$BRANCH_NAME" ]; then
  git checkout -B "$BRANCH_NAME"
fi

step "Configure upstream remote"
if ! git remote | grep -qx "prism-upstream"; then
  git remote add prism-upstream "$UPSTREAM_URL"
fi

git fetch prism-upstream "$UPSTREAM_BRANCH"

step "Import upstream into ${PREFIX}/"
if [ -d "$PREFIX" ]; then
  echo "${PREFIX} 폴더가 이미 있습니다. 중복 병합을 막기 위해 중단합니다." >&2
  exit 2
fi

git read-tree --prefix="${PREFIX}/" -u "prism-upstream/${UPSTREAM_BRANCH}"

step "Stage imported upstream files"
git status --short

step "Commit import"
git commit -m "chore: import prism-insight upstream under ${PREFIX}"

step "Run local checks"
python -m pip install -e ".[test]"
python -m pytest -q
python -m runtime.preflight --json

printf '\n완료: PRISM-INSIGHT 원본이 %s/ 하위 폴더로 병합되었습니다.\n' "$PREFIX"
printf '다음 단계: docs/UPSTREAM_MERGE_PLAYBOOK_ko.md의 6단계에 따라 어댑터를 연결하세요.\n'
