# Run locally

```powershell
..\penv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

# Deploy

1. Merge `deploy/prod` into `main` on GitHub.
2. Create an app at [share.streamlit.io](https://share.streamlit.io).
3. Select `sk-agnihotri/org-chart-platform`, branch `main`, and file `app.py`.
4. Add the following under **Advanced settings → Secrets**, replacing the hashes with values from `python scripts\hash_password.py`:

```toml
ORGCHART_USERS_JSON = '[{"username":"admin","password_hash":"<admin-hash>","role":"admin"},{"username":"reviewer","password_hash":"<reviewer-hash>","role":"readonly"}]'
```

5. Deploy and open the generated app URL.
