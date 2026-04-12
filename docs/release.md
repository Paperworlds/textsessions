# Plan: textsessions open source release prep

## Context

textsessions is functionally ready (122 tests, all features working). Need to fix stale docs, add missing files, update URLs, and add roadmap before making the repo public under paperworlds org.

## 1. Add LICENSE file

- MIT license, copyright paperworlds (match textaccounts pattern)

## 2. Fix pyproject.toml

- Add `[project.urls]` — Homepage, Repository, Issues
- URLs should use `github.com/paperworlds/textsessions`

## 3. Move GitHub repo to paperworlds org

- Transfer `pdonorio/textsessions` → `paperworlds/textsessions`
- Or create new repo and push (user decision)

## 4. Fix all `pdonorio` and `Paperworlds` references

- README.md: `pdonorio/claude-code-proxy` → `paperworlds/claude-code-proxy` (or remove if not public yet)
- README.md: all `Paperworlds` → `paperworlds`
- pyproject.toml: textaccounts git URL uses `Paperworlds` → `paperworlds`
- Verify no personal emails/paths in public files

## 5. Update README.md

- Quick start: `textsessions` → `textsessions view` (bare command now shows help)
- Add `textsessions add` to CLI reference
- Add `textsessions view --config` to CLI reference  
- Add `c` key to keyboard shortcuts table
- Remove `scan` from any references
- Requirements: note that textaccounts is a separate optional package, not "bundled in this repo"
- Add Roadmap section (like textaccounts has):
  - [ ] Publish to PyPI
  - [ ] Upgrade to Python 3.13
  - [ ] Bash/zsh shell support (currently fish only)
  - [ ] `textsessions doctor` — validate config, check for stale paths
  - [ ] Session export to markdown

## 6. Rewrite docs/onboarding.md

- Currently references `uv pip install -e src/textaccounts` (bundled era)
- Should reference `pip install textsessions[accounts]` and `textaccounts install`

## 7. Update docs/textaccounts.md

- Remove "ships as part of textsessions" — it's a separate package now
- Link to `github.com/paperworlds/textaccounts`
- Fix "see the textaccounts README" link (was `../src/textaccounts/README.md`, that dir is gone)

## 8. Add GitHub Actions CI

- `.github/workflows/test.yaml` — same pattern as textaccounts
- Run pytest on push/PR to main
- Python 3.12 (match requires-python)

## Files to modify

- `LICENSE` — create (MIT)
- `pyproject.toml` — add project.urls
- `README.md` — update quick start, add commands, add roadmap, fix URLs
- `docs/onboarding.md` — rewrite for separated textaccounts
- `docs/textaccounts.md` — update for separated package
- `docs/testing.md` — fix any `Paperworlds` casing
- `.github/workflows/test.yaml` — create

## Verification

1. `grep -ri 'pdonorio\|Paperworlds' README.md docs/ pyproject.toml` — no matches
2. `uv run pytest -x -q` — passes
3. LICENSE file exists
4. `.github/workflows/test.yaml` exists
5. README roadmap section present
