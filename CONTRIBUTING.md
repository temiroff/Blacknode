# Contributing to Blacknode

Thank you for your interest in contributing.

## Ways to contribute

- **Bug reports** — open an issue with steps to reproduce, expected vs actual behavior, and your OS/Python/Node versions.
- **Feature requests** — open an issue describing the use case before writing code.
- **Code** — fork the repo, make your changes on a branch, and open a pull request.

## Development setup

```bash
# Backend
cd editor-server
pip install -r requirements.txt
python server.py

# Frontend (separate terminal)
cd editor
npm install
npm run dev
```

## Pull request guidelines

- One logical change per PR.
- Keep commit messages concise: subject line + optional body paragraph.
- If you add a new node type, include a short description in the PR body.
- Run `npm run build` in `editor/` before submitting to catch TypeScript errors.

## License

By contributing you agree that your changes will be licensed under the project's [AGPL-3.0 license](LICENSE).
