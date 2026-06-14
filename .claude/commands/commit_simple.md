---
description: Generate a conventional-commit message for the current changes (does not run git)
---

Generate a git commit message based on the current changes.

**Important: ONLY generate and output the commit message in chat. Do NOT execute any git
commands (`git commit`, `git push`, `git add`, etc.).**

Steps:

1. Analyze the git diff — both staged and unstaged (`git status`, `git diff`,
   `git diff --cached`).
2. Write a message starting with a conventional-commit prefix (`feat`, `fix`, `docs`,
   `style`, `refactor`, `test`, `chore`).
3. Follow the summary line with bullet points describing the changes.
4. Keep descriptions general and readable to a third party — avoid internal jargon.
5. Focus on **what changed and why**, not line-level implementation detail.
6. Never include secrets, tokens, or connection strings.

Format:

```
<prefix>: <brief summary>

- <change 1>
- <change 2>
- <change 3>
```

Example output:

```
feat: Add Privy authentication integration

- Replace custom auth with Privy SDK
- Add email and Google OAuth login methods
- Update API client to use Privy access tokens
- Remove legacy authentication components
```

$ARGUMENTS
