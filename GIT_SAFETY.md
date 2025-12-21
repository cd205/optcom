# Git Safety and Secrets Management

## Overview

This document explains the secrets management strategy and safe git workflow for the optcom-1 project.

## Secrets Management Strategy

### Current Setup: Local File-Based (Recommended)

We use **local JSON file** for secrets management (`config/credentials.json`) instead of external services because:

- ✅ Single VM deployment - no complex orchestration
- ✅ Already implemented with `CredentialsLoader` class
- ✅ Secure file permissions (`-rw-------`, owner-only access)
- ✅ Fast local access, no network overhead
- ✅ Simple debugging and troubleshooting

### Credentials File Structure

```json
{
  "database": {
    "postgresql": { "host": "...", "port": 5432, "database": "...", "user": "...", "password": "..." },
    "sqlite": { "path": "..." }
  },
  "gcp": { "project_id": "...", "instance_connection_name": "..." },
  "ibkr": { "username": "...", "password": "..." },
  "network": { "ssh_key": "..." },
  "web_scraping": { "credentials": "..." }
}
```

### When to Consider External Secrets Managers

Only consider these if your setup changes:

- **GCP Secret Manager** - if scaling to multiple VMs/containers
- **AWS Secrets Manager** - if migrating to AWS
- **HashiCorp Vault** - if running multiple services with dynamic secrets rotation
- **Doppler** - if collaborating with a team

## Files NEVER to Commit

### Credentials Files
```
config/credentials.json         # Main credentials file
.env, .env.*                   # Environment files
*.key, *.pem, *.p12           # Cryptographic keys
```

### Runtime Files
```
airflow_project/airflow.db     # Airflow metadata database
*.db, *.db-journal             # Any SQLite databases
__pycache__/                   # Python bytecode cache
*.pyc, *.pyo                   # Compiled Python
```

### IB Gateway Session Data
```
ibc-setup/tws/live-settings/**     # Live account session data
ibc-setup/tws/paper-settings/**    # Paper account session data
ibc-setup/logs/*.log               # Gateway logs
```

**Why?** These files contain:
- HSQLDB credentials (nia2.script, nia2.properties)
- Session tokens and authentication state
- Account identifiers and trading history
- 2FA authentication artifacts

### Development Files
```
*.ipynb                        # Jupyter notebooks (may contain output/secrets)
*.log                          # Log files (may contain credentials)
```

## Safe Commit Workflow

### Pre-Commit Checklist

Before every commit:

```bash
# 1. Check what files are staged
git status

# 2. Review changes in detail
git diff --cached

# 3. Verify no secrets in staged files
git diff --cached | grep -iE "(password|api_key|secret|token)" && echo "⚠️  WARNING: Potential secret detected!"

# 4. Ensure credentials.json is NOT staged
git status | grep credentials.json && echo "❌ STOP: credentials.json is staged!"
```

### Safe Commit Commands

```bash
# Stage specific files only (never use 'git add .')
git add airflow_project/dags/simple_trading_workflow.py
git add airflow_project/scripts/market_snapshots.py

# Commit with descriptive message
git commit -m "Add market snapshot functionality to Step 5"

# Push to remote
git push origin snapshot
```

### ⚠️ NEVER Do This

```bash
# ❌ DANGEROUS: Stages ALL files including untracked
git add .
git add -A

# ❌ DANGEROUS: Commits without review
git commit -am "quick fix"

# ❌ DANGEROUS: Force pushing (can expose secrets in history)
git push --force
```

### Safe Way to Add Multiple Files

```bash
# ✅ SAFE: Review changes first
git status

# ✅ SAFE: Add specific directories/files
git add airflow_project/dags/*.py
git add airflow_project/scripts/market_snapshots.py
git add CLAUDE.md

# ✅ SAFE: Review what's staged
git diff --cached

# ✅ SAFE: Commit after review
git commit -m "Descriptive commit message"
```

## Pull Request Workflow

### Creating a Safe PR

```bash
# 1. Create feature branch
git checkout -b feature/add-greeks-capture

# 2. Make changes to specific files
# ... edit files ...

# 3. Stage only relevant files
git add airflow_project/scripts/greeks_capture.py
git add database/add_options_greeks_table.sql

# 4. Review changes
git diff --cached

# 5. Commit
git commit -m "Add options greeks capture functionality"

# 6. Push to remote
git push origin feature/add-greeks-capture

# 7. Create PR on GitHub
# Review the PR diff on GitHub before merging
```

### PR Review Checklist

Before merging ANY PR:

- [ ] No `config/credentials.json` in diff
- [ ] No `.env` files in diff
- [ ] No `ibc-setup/tws/*-settings/` files in diff
- [ ] No `*.db` files in diff
- [ ] No `__pycache__/` or `*.pyc` files in diff
- [ ] No credentials visible in code (hardcoded passwords, API keys)
- [ ] All secrets loaded from `credentials.json` via `CredentialsLoader`

## Emergency: Secrets Accidentally Committed

If secrets are committed to git history:

### 1. Remove from Latest Commit (Not Pushed)
```bash
# Remove the file from staging
git reset HEAD config/credentials.json

# Amend the commit
git commit --amend
```

### 2. Remove from History (Already Pushed)

**⚠️ CRITICAL: Rotate all exposed credentials FIRST**

```bash
# Use git-filter-repo to remove from history
pip install git-filter-repo
git filter-repo --path config/credentials.json --invert-paths

# Force push (coordinate with team)
git push origin --force --all
```

### 3. Rotate Compromised Credentials

Immediately rotate:
- Database passwords
- IBKR credentials
- GCP service account keys
- SSH keys
- Any other exposed secrets

## Verification

### Check .gitignore is Working

```bash
# Should show NO output for these commands:
git ls-files | grep credentials.json
git ls-files | grep "\.env"
git ls-files | grep "tws/.*-settings/"
git ls-files | grep "\.db$"
git ls-files | grep "__pycache__"
```

### Test Credentials Loader

```bash
# Verify credentials are loaded correctly
python setup_credentials.py

# Should output:
# ✅ Credentials file found
# ✅ Credentials loader initialized
# ✅ PostgreSQL config loaded
# ✅ Environment variables set from credentials
# ✅ Database connection successful
```

## Best Practices

1. **Always review changes** before committing
2. **Never use `git add .`** - stage files explicitly
3. **Keep credentials.json secure** with file permissions `600`
4. **Use descriptive commit messages** explaining the "why"
5. **Create feature branches** for new work
6. **Review PRs thoroughly** before merging
7. **Test locally** before pushing
8. **Rotate credentials** if any exposure suspected

## Additional Resources

- Main documentation: [CLAUDE.md](CLAUDE.md)
- Security guidelines: [SECURITY.md](SECURITY.md)
- Credentials setup: [setup_credentials.py](setup_credentials.py)
- Database config: [database/database_config.py](database/database_config.py)
