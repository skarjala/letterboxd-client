# Contributing

## Workflow

1. Branch from `main`.
2. Keep changes scoped to one PR-sized concern.
3. Run the test suite in the project conda environment before opening a PR.
4. Avoid unrelated refactors, especially in runtime modules that are not part of your change.

## Local Setup

```bash
conda run -p /Users/sandeepkarjala/pythonenv python -m pip install -e .[dataframes]
conda run -p /Users/sandeepkarjala/pythonenv python -m unittest discover -s tests -v
```

## Release Discipline

- Update `CHANGELOG.md` for user-visible changes.
- Keep release/process changes in metadata files and workflows unless a runtime fix is required.
- Prefer small, reviewable pull requests with a clear test signal.
