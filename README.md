# Run locally

```powershell
..\penv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Feature guide: [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

To create a historical dataset version before replacing the CSVs:

```powershell
python scripts\snapshot_dataset.py v1
```

Commit `data/snapshots/` with the updated dataset to enable version comparisons.

# Deploy

1. Merge `deploy/prod` into `main` on GitHub.
2. Create an app at [share.streamlit.io](https://share.streamlit.io).
3. Select `sk-agnihotri/org-chart-platform`, branch `main`, and file `app.py`.
4. Add the following under **Advanced settings → Secrets**, replacing the hashes with values from `python scripts\hash_password.py`:

```toml
ORGCHART_USERS_JSON = '[{"username":"admin","password_hash":"<admin-hash>","role":"admin"},{"username":"reviewer","password_hash":"<reviewer-hash>","role":"readonly"}]'
```

5. Deploy and open the generated app URL.

Review marks are session-only in this CSV-backed, read-only deployment; use a persistent shared store before relying on them across users or sessions.
