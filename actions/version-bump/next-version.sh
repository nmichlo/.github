#!/usr/bin/env bash
# Prints the tag that merging commit SHA of REPO asks for, or nothing: the
# bump keyword of the title of the pull request it merged, applied to the
# highest vX.Y.Z tag (v0.0.0 if none). Pushes nothing, so it can be run by
# hand: `GH_TOKEN=... next-version.sh owner/repo <sha>`.
#
#   next-version.sh REPO SHA [TITLE]
#
# TITLE, if given, is used rather than looked up (the closed-pull-request
# event carries it).
set -euo pipefail

repo="$1"
sha="$2"
title="${3:-}"

if [ -z "${title}" ]; then
  # the pull requests whose merge put SHA on the default branch. A squash or
  # rebase merge's merge_commit_sha is the commit it left on top, which is
  # the one pushed; other pull requests that merely contain SHA are left out.
  title="$(gh api "repos/${repo}/commits/${sha}/pulls" \
    --jq ".[] | select(.merged_at != null and .merge_commit_sha == \"${sha}\") | .title" | head -n 1)"
fi
if [ -z "${title}" ]; then
  echo "no pull request merged ${sha}: nothing to release" >&2
  exit 0
fi
echo "pull request: ${title}" >&2

# the largest keyword in the title wins
case "${title}" in
  *'#major'*) bump='major' ;;
  *'#minor'*) bump='minor' ;;
  *'#patch'*) bump='patch' ;;
  *) echo "no #major/#minor/#patch in the title: nothing to release" >&2; exit 0 ;;
esac

# the highest release tag; pre-releases (v1.2.3-rc1) are not bumped from
last="$(gh api "repos/${repo}/git/matching-refs/tags/v" --paginate --jq '.[].ref' \
  | sed 's#^refs/tags/##' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -n 1 || true)"
IFS=. read -r major minor patch <<< "${last:-v0.0.0}"
major="${major#v}"
case "${bump}" in
  major) major=$((major + 1)); minor=0; patch=0 ;;
  minor) minor=$((minor + 1)); patch=0 ;;
  patch) patch=$((patch + 1)) ;;
esac
echo "bump: ${bump} from ${last:-v0.0.0}" >&2
echo "v${major}.${minor}.${patch}"
