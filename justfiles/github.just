# Squash-merge the current branch's PR, bypassing the review rule as org admin
gh-merge:
    #!/usr/bin/env zsh
    set -e
    # No PR number: gh resolves it from the checked-out branch, which is the
    # one the editor is showing.
    pr=$(gh pr view --json number,baseRefName,state,title)
    num=$(jq -r .number <<<"$pr")
    base=$(jq -r .baseRefName <<<"$pr")
    state=$(jq -r .state <<<"$pr")
    if [[ "$state" != "OPEN" ]]; then
      echo "PR #$num is $state, nothing to merge."
      exit 1
    fi
    # A PR stacked on another branch merges its parent's commits too, and
    # strands the rest when the parent lands separately.
    if [[ "$base" != "main" ]]; then
      echo "PR #$num targets '$base', not main. Retarget it before merging:"
      echo "  gh pr edit $num --base main"
      exit 1
    fi
    echo "Merging #$num — $(jq -r .title <<<"$pr")"
    # --squash because the org ruleset requires linear history; --admin to
    # bypass the review rule, which a solo author cannot satisfy.
    gh pr merge "$num" --squash --admin
    echo "Merged #$num into main."

# Fetch origin and cut a new branch off the latest origin/main. name: a bare branch name.
[positional-arguments]
gh-fresh-branch name:
    #!/usr/bin/env zsh
    set -e
    # `just gh-fresh-branch name=foo` passes the whole `name=foo`.
    NAME="${1#name=}"
    if [[ ! "$NAME" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ ]]; then
      echo "not a bare branch name: '$NAME'"
      exit 1
    fi
    # Uncommitted work may matter: it is left for the user, never stashed.
    if [[ -n "$(git status --short)" ]]; then
      echo "The working tree is not clean. Commit or discard first:"
      git status --short
      exit 1
    fi
    git fetch origin --prune
    for REF in "refs/heads/$NAME" "refs/remotes/origin/$NAME"; do
      if git rev-parse --verify --quiet "$REF" >/dev/null; then
        echo "branch $NAME already exists (${REF#refs/}). Switch to it instead:"
        echo "  git switch $NAME"
        exit 1
      fi
    done
    # Off origin/main rather than main, which may be checked out in another
    # worktree: git refuses to check out one branch twice.
    git checkout -b "$NAME" origin/main
    # Keep the local main ref current too; this fails harmlessly where main
    # is checked out elsewhere.
    git fetch --quiet origin main:main 2>/dev/null || true
    git log --oneline -3

# Commit everything, push to a same-named remote branch, and open a PR against main or add to its open one. body may span lines.
[positional-arguments]
gh-commit-and-pr title body="":
    #!/usr/bin/env zsh
    set -e
    TITLE="$1"
    BODY="$2"
    if [[ -z "$TITLE" ]]; then
      echo "usage: just gh-commit-and-pr <title> [body]"
      exit 1
    fi
    BRANCH=$(git rev-parse --abbrev-ref HEAD)
    if [[ "$BRANCH" == "main" ]]; then
      echo "On main. Cut a branch first: just gh-fresh-branch <name>"
      exit 1
    fi
    # Everything in the tree lands, whichever session wrote it. The one
    # hard stop is a file that looks like a credential. .envrc is direnv
    # config and .env.example is a template, so neither counts.
    FILES=$(git status --porcelain --untracked-files=all | sed -E 's/^.{3}//; s/^.* -> //')
    if [[ -z "$FILES" ]]; then
      echo "Nothing to commit."
      exit 1
    fi
    SECRETS=$(echo "$FILES" \
      | grep -E '(^|/)(\.env(\..+)?|credentials[^/]*|[^/]+\.(key|pem|pfx|p12))$' \
      | grep -vE '(^|/)\.env\.example$' || true)
    if [[ -n "$SECRETS" ]]; then
      echo "Refusing to commit what looks like a credential:"
      echo "$SECRETS"
      exit 1
    fi
    git add -A
    ARGS=(-m "$TITLE")
    if [[ -n "$BODY" ]]; then
      ARGS+=(-m "$BODY")
    fi
    git commit --quiet "${ARGS[@]}"
    # -u origin HEAD, never a bare push: gh-fresh-branch leaves the upstream
    # at origin/main, so a bare push would aim the work at main.
    git push -u origin HEAD
    # A branch that already has an open PR just gains the commit.
    URL=$(gh pr view --json url,state --jq 'select(.state == "OPEN") | .url' 2>/dev/null || true)
    if [[ -n "$URL" ]]; then
      echo "Pushed to $URL"
      exit 0
    fi
    gh pr create --base main --head "$BRANCH" --title "$TITLE" --body "$BODY"
