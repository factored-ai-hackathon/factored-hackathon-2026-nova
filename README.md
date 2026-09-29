# Factored Hackathon 2026: AI contact center agent

A banking agent for the contact center (Spanish and Portuguese), built on the LATAM Bank dataset.
Goal: resolve more issues on the first contact, benchmark agents, track customer sentiment. Deadline: **Oct 5**.

## Start here
1. Follow **[docs/setup.md](docs/setup.md)** once (about 20 minutes).
2. Put your work in your folder:

| Folder | What goes there | Owner |
|---|---|---|
| `data/` | Cleaning and the data model (dbt SQL) | Iris |
| `ml/` | Notebooks and models | Iris |
| `backend/` | API and the agent | Paul, Esteban, Iris |
| `frontend/` | Chat UI | Esteban, Miguel |
| `evals/` | Tests of the agent and models | Miguel |
| `infra/` | AWS setup (Terraform) | Paul, Miguel |
| `docs/` | Architecture, decisions, data findings | everyone |

That's all you need to read today. The rest of `docs/` is reference.

## Daily workflow
```bash
git switch development && git pull    # 1. get the latest code
git switch -c yourname/what-you-do    # 2. new branch for your task
# ... work ...
git add .                             # 3. save your changes
git commit -m "Short description"
git push -u origin HEAD               # 4. upload, then open a Pull Request into development
```
Someone reviews the Pull Request and merges it. Prefer clicks? VS Code's **Source Control** panel does the same.

## Branches and deploys
```
your branch ──PR──▶ development ──PR (merge commit)──▶ main ──▶ deploy to AWS
 (tests run)         (tests run)                              (tests + deploy)
```
- **`development`** is where we work. It lives for the whole project: **never delete it**. Every Pull Request goes here.
- **`main`** is what is live at the demo link. Merging into `main` deploys to AWS automatically, so only a Pull Request from `development` goes there, when we want to release.
- **`development` → `main`:** merge with **"Create a merge commit"** (not squash or rebase), and **don't click "Delete branch"** afterwards. Squash or rebase would make the two branches drift apart.
- Tests run on every Pull Request. Only the parts you changed are tested (`frontend/`, `backend/`, `evals/`); docs changes run nothing.

## Five rules
1. **Never commit data, passwords or keys.** The repo is public. (Git already ignores `.csv`, `.parquet` and `.env`.)
2. **Don't change the original data.** Write results to new tables or files.
3. **Never push to `main` or `development`.** Always a branch and a Pull Request into `development`.
4. **Ask before creating anything in AWS.** We pay for it.
5. **Stuck for more than 30 minutes?** Ask in the team chat.
