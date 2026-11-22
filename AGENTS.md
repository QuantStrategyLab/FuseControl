# AGENTS.md

Rules for AI assistants and maintainers in `QuantStrategyLab/FuseControl`. Reusable PR governance actions live in `Pigbibi/PrGovernance`.

## What this repository is

FUSE breaker specification and reference engine for QuantStrategyLab (`FUSE-1`).

## Layout

- `README.md` — FUSE-1 scope, coordination status, and safety posture.
- `.github/governance/policy.json` — PR governance policy (`pr-governance/v3`).

## Local checks

```sh
python3 -m unittest discover -s tests -p "test_*.py"
```

## Naming and documentation

- English is default; document filenames use lowercase kebab-case (`README.md`, `AGENTS.md`, `CLAUDE.md` keep standard casing).
- Update `README.md` only when user-visible behavior, CLI, or configuration changes; never append PR narration or sections after `## License`.

<!-- repository-files:begin -->
- Public repositories (with `LICENSE`) include `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, and issue/PR templates (`pull_request_template.md`).
- Public `SECURITY.md` covers disclosure only; never mix private rotation procedures into public files.
<!-- repository-files:end -->

## Do not

- Do not enable live trading, Kelly sizing, or stop-loss arming (`loss_breakers_armed: false`).
- Do not delete or archive active coordination branches or status notes.
- Do not commit `docs/plans/`, `docs/audits/`, `docs/changes/`, or `docs/acceptance-policy.md`.

<!-- content-boundary:begin -->
- Public material carries no real resource names or accounts: use synthetic placeholders (`<bucket>`, `<account-id>`).
- Judge whether a change is clean by `git diff` and `git ls-files`; `.gitignore` affects untracked files only.
<!-- content-boundary:end -->

## Commits and pull requests

- Use English Conventional Commits (`feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`, `build`) with headers ≤ 72 characters.
- Fill in PR template sections (`AI assistance`, `What changed`, `How verified`, `Risk`). R2 paths require green CI, `ai-review` on the exact head SHA, and one clearing label (`agent-approved` or `owner-approved`). Never push to `main` or use `--admin`.
