# Run

From this folder in PowerShell:

```powershell
..\penv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts\generate_dataset.py --seed 42
```

Create a password hash for each account:

```powershell
$adminHash = python scripts\hash_password.py
$managerHash = python scripts\hash_password.py
$readerHash = python scripts\hash_password.py
```

Configure accounts and start the app:

```powershell
$users = @(
  @{ username = "admin"; password_hash = $adminHash.Trim(); role = "admin" },
  @{ username = "team-manager"; password_hash = $managerHash.Trim(); role = "manager"; company_ids = @("COMP-0001") },
  @{ username = "reviewer"; password_hash = $readerHash.Trim(); role = "readonly" }
)
$env:ORGCHART_USERS_JSON = ConvertTo-Json -InputObject $users -Compress
streamlit run app.py
```

Run tests:

```powershell
python -m pytest -q
```
