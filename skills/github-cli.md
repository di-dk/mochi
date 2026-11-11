name: github-cli
description: Read GitHub issues, pull requests, CI checks and repos with the gh CLI in PowerShell

All commands go through run_powershell. gh is already installed and signed in.
1. Once per session: gh auth status
   If it fails, stop and ask the user to sign in. Never ask for, read or print a token.
2. Run inside the repo folder, or add -R owner/name to any command.
3. Pick the read command:
   Repo:    gh repo view            gh release list            gh run list --limit 10
   Issues:  gh issue list --state open --limit 20
            gh issue list --search "words"
            gh issue view 12 --comments
   PRs:     gh pr list              gh pr status
            gh pr view 34 --comments
            gh pr diff 34           gh pr checks 34
   Merged?  gh pr view 34 --json state,mergedAt,title,url
   CI log:  gh run view <run-id> --log-failed
   Other:   gh api repos/owner/name/<path>     (GET only, for things the commands above lack)
4. Add --json <fields> when you need exact data, e.g. --json number,title,state,url
5. Read the full thread with --comments before judging an issue or PR; decisions are in the comments.

RULES
- Read commands are free. Anything that CHANGES GitHub needs the user's yes first, every time:
  create, edit, close, reopen, comment, review, label, assign, merge, release, delete, fork,
  git commit, git push. Show the exact command and target, then wait.
- Before creating an issue or PR, search for duplicates with --search.
- Never say CI is green without a fresh gh pr checks. Never say merged without state and mergedAt.
- Every statement about GitHub state comes from a command you just ran, not from memory.
- Long output: add --limit, or ask for a few fields with --json.

Final answer: what you found, with issue/PR numbers, states and URLs, plus the commands you ran.
List any change you propose as a command waiting for the user's confirmation.
