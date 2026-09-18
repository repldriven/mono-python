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
