# Devlog

## 2026-10-26: Project setup (Phase 0)

**What I did:**
- Set up the project with git and uv (Python 3.12, src layout)
- Pushed the repo to GitHub
- Wrote my first function `find_vague_words` with pytest tests
- Added CI with GitHub Actions (pytest + ruff on every push)
- Added a README with a CI badge

**What I learned:**
- `git add` stages changes, `git commit` saves them
- `.gitignore` keeps `.venv` and `.env` out of the repo
- TDD: write a failing test first, then fix the code
- CI runs my tests on a clean machine, so I know the code works everywhere

**Where I got stuck:**
- I created `ambiguity.py` in the wrong folder, so Python could not import it. Code must go in `src/req_assistant/`.
- `split()` did not handle punctuation ("fast." was not found). I fixed it with a regex.
- CI failed because `setup-uv@v10` does not exist. The full tag `v10.3.2` was needed. I learned to read the error log.