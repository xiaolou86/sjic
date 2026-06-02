# Database migrations

Schema changes are managed with [Flask-Migrate](https://flask-migrate.readthedocs.io/) (Alembic).

## Revision chain

```text
000_initial_core_tables
  → 001_update_algorithm_and_task_models
  → 002_add_settings_table
  → 003_core_edge_nodes_and_columns   (head)
```

## Commands

```powershell
cd backend
$env:FLASK_APP = "run.py"
flask db upgrade          # apply all pending migrations
flask db current          # show current revision
flask db history          # show history
flask db migrate -m "core_xxx"   # autogenerate new revision (after model change)
```

## Existing database (created by old `create_all`)

If tables already exist and match current models:

```powershell
flask db stamp head
```

Then use only `flask db migrate` / `flask db upgrade` for future changes.

See [docs/DATABASE_MIGRATION.md](../docs/DATABASE_MIGRATION.md) for the full runbook.
