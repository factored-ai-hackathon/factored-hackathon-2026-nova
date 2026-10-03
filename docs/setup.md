# Setup (Mac and Windows)

Copy and paste the commands in order. **Mac:** Terminal app. **Windows:** PowerShell.
Ask Paul for **your personal AWS access key** first (sent privately, never in chat groups or email threads).

## 1. Install tools (once)

**Mac** (install [Homebrew](https://brew.sh) first if you don't have it):
```bash
brew install git uv awscli
brew install --cask visual-studio-code
```
**Windows:**
```powershell
winget install --id Git.Git -e
winget install --id astral-sh.uv -e
winget install --id Amazon.AWSCLI -e
winget install --id Microsoft.VisualStudioCode -e
```
Close and reopen the terminal afterwards. In VS Code, install the **Python** and **Jupyter** extensions.

## 2. Get the code (once)
```bash
git clone https://github.com/factored-ai-hackathon/factored-hackathon-2026-nova.git
cd factored-hackathon-2026-nova
git config --global user.name "Your Name"
git config --global user.email "your-github-email@example.com"
```

## 3. Python environment (once)
```bash
uv sync
uv run nbstripout --install
```
`uv sync` downloads Python and all libraries. `nbstripout` removes data from notebooks before you commit them.
Run `uv sync` again whenever someone adds a library.

## 4. AWS access key (once)
```bash
aws configure
```
Answers: your **Access Key ID** · your **Secret Access Key** · region `us-east-2` · format `json`.

Check it works (it should print the account and your user name):
```bash
aws sts get-caller-identity
```
(Already use other AWS accounts on this laptop? Run `aws configure --profile hackathon` instead and set `AWS_PROFILE=hackathon` in your terminal.)

Your key is **personal**. Never share it or paste it in code, notebooks, `.env` files, chats or screenshots. If you think it leaked, tell Paul right away so he can disable it.

## Every day
Go to the project folder and put `uv run` in front of Python tools. Nothing to activate.
```bash
cd factored-hackathon-2026-nova
uv run jupyter lab
```

## Use the data
Open VS Code with `code .`, create a notebook in `ml/notebooks/`, choose the `.venv` kernel (created by `uv sync`), and run:
```python
import awswrangler as wr

df = wr.athena.read_sql_query(
    "SELECT * FROM fact_interaction",
    database="latam_curated",
    workgroup="hackathon",
)
df.head()
```
Or write SQL in the AWS console: **Athena** → workgroup `hackathon`.

To rebuild the data model after changing SQL in `data/dbt/`, see [data/dbt/README.md](../data/dbt/README.md): set `DBT_DEV_NAME` to your name and `uv run dbt build` writes to your own `latam_curated_dev_<name>`. `latam_curated` is only rebuilt by the data pipeline when changes reach `main`.

## If something fails
| Message | Fix |
|---|---|
| `Unable to locate credentials` | Run step 4 again |
| `ModuleNotFoundError` / `command not found: dbt` | Run `uv sync`, and start the command with `uv run` |
| `InvalidClientTokenId` / `SignatureDoesNotMatch` | The key was mistyped: run step 4 again |
| `AccessDenied` | Your user is missing a permission: send Paul the full message |
| `command not found` / `is not recognized` | Close and reopen the terminal |
| Windows: `running scripts is disabled` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

Still stuck? Ask in the team chat.
