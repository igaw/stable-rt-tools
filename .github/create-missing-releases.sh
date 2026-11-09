#!/bin/bash
# Create the GitHub releases missing for v* tags.
#
# Usage: .github/create-missing-releases.sh [--create]
#
# Without --create it only shows what it would do. The notes are the
# changelog section of the version (docs/changes.rst), or the commit
# subjects since the previous tag for versions without one. The files
# attached are the ones published on PyPI, checked against their sha256.

set -euo pipefail

PROJECT=stable-rt-tools
create=false
case "${1:-}" in
    --create) create=true ;;
    "") ;;
    *) sed -n '2,9s/^# \{0,1\}//p' "$0"; exit 1 ;;
esac

cd "$(git rev-parse --show-toplevel)"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

mapfile -t tags < <(git tag -l 'v*' --sort=v:refname)
newest=${tags[-1]}

notes() {
    local tag=$1 prev=$2
    if python3 .github/release-notes.py "$tag" 2>/dev/null; then
        return
    fi
    echo "Changes since $prev:"
    echo
    git log --no-merges --format='- %s' "$prev..$tag" \
        | grep -v '^- stable-rt-tools: Version '
}

pypi_files() {
    local version=$1 dir=$2 json url sha file
    # a version not on PyPI gets no files
    json=$(curl -fsS "https://pypi.org/pypi/$PROJECT/$version/json") || return 0
    python3 -c '
import json, sys
for u in json.load(sys.stdin)["urls"]:
    print(u["url"], u["digests"]["sha256"], u["filename"])' <<< "$json" \
        > "$dir/urls"
    while read -r url sha file; do
        curl -fsSL -o "$dir/$file" "$url"
        echo "$sha  $dir/$file" | sha256sum --quiet -c -
        echo "$dir/$file" >> "$dir/files"
    done < "$dir/urls"
}

prev=
for tag in "${tags[@]}"; do
    if gh release view "$tag" >/dev/null 2>&1; then
        prev=$tag
        continue
    fi

    dir=$work/$tag
    mkdir -p "$dir"
    notes "$tag" "${prev:-$(git rev-list --max-parents=0 "$tag" | tail -1)}" \
        > "$dir/notes.md"
    : > "$dir/files"
    pypi_files "${tag#v}" "$dir"
    mapfile -t files < "$dir/files"
    latest=false
    [ "$tag" = "$newest" ] && latest=true

    echo "=== $tag (latest: $latest)"
    for f in "${files[@]}"; do echo "file: ${f##*/}"; done
    cat "$dir/notes.md"
    echo

    if $create; then
        gh release create "$tag" "${files[@]}" --verify-tag \
            --title "$PROJECT $tag" --notes-file "$dir/notes.md" \
            --latest="$latest"
    fi
    prev=$tag
done

$create || echo "Dry run, run with --create to create the releases."
