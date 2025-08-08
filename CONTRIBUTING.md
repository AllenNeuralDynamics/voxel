## Branching Strategy

This repository uses the following branching strategy:

- `main`: Contains production-ready code. Updated only for releases and hotfixes.
- `develop`: Default branch. Contains the latest development changes.
- `feature/*`: Used for developing new features. Branch off from and merge back into `develop`.
- `hotfix/*`: Used for critical bug fixes. Branch off from `main`, and merge to both `main` and `develop`.

Contributors should typically branch off from and create pull requests to `develop`.