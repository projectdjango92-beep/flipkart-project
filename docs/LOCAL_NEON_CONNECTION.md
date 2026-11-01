# Local Neon connection on Windows

The application reads `DATABASE_URL` from the local `.env` file. That file is
ignored by Git and must remain private. SQLite stays active if the variable is
absent.

1. In Neon, copy the **pooled** PostgreSQL connection string. Do not paste it
   into source code, chat, a committed file, or a terminal command.
2. Open PowerShell in the project directory and run:

   ```powershell
   .\scripts\set_local_neon_url.ps1
   ```

3. Paste the URL at the hidden prompt. The script validates only its PostgreSQL
   prefix, replaces any previous `DATABASE_URL` entry in `.env`, and never
   displays the value.
4. Verify only the connection (no migrations, data import, or writes):

   ```powershell
   python manage.py verify_database --require-postgresql
   ```

5. When finished testing locally, delete just the `DATABASE_URL=` line from
   `.env` to return to SQLite. Do not delete `db.sqlite3`.

The verification command runs `SELECT 1` and read-only record counts. It does
not run migrations or alter database data. Never run the import commands in
`NEON_MIGRATION.md` as part of this connection-only check.

Run automated tests with the local-only test settings so Django never creates
a test database on Neon:

```powershell
python manage.py test --settings=config.test_settings
```
