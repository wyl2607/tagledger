# Postgres Migration Runbook

## 中文

### 目标

在不改动现有 SQLite 源库的前提下，把业务表迁移到单机 Postgres，并完成可回滚的 ETL、备份和恢复闭环。

G6 只完成 Postgres cutover 与 `factory_id` schema 准备。运行时仍按单工厂使用；`factory_id` 不代表多工厂数据隔离已经上线。多工厂查询隔离、唯一约束收敛和跨厂权限边界必须在后续任务单独放行前保持关闭。

`user_sessions` 和 `security_secrets` 在 G6 中仍是全局安全表，不按 `factory_id` 分区。它们只存登录会话和系统密钥，不承载工厂业务身份；如果后续启用真实多工厂租户隔离，必须单独审查这两张表的作用域。

### 前提

1. 先备份 SQLite：`./scripts/backup_live_data.sh`
2. 安装依赖：`pip install -e ".[dev]"`
3. 准备 Postgres DSN：`postgresql://<user>:<pass>@<host>:5432/<db>`
4. `config/settings.yaml` 中配置：

```yaml
database:
  dsn: postgresql://<user>:<pass>@<host>:5432/<db>
```

### 迁移步骤

1. 先在目标 Postgres 跑 schema：
   - `DATABASE_URL=<postgres_dsn> ./.venv/bin/alembic upgrade head`
2. 执行一次性 ETL（不删除 SQLite）：
   - `./.venv/bin/python scripts/etl_sqlite_to_postgres.py --sqlite-url sqlite:////abs/path/app.db --postgres-url <postgres_dsn> --factory-id factory_a --report-json /tmp/g6_etl_report.json`
3. 对账：检查脚本输出里每张表 `source == target == post_commit_target`，且含 `id` 的表在 Postgres 报告 `sequence_reset: 1`。
4. 冒烟插入：ETL 后在 Postgres 上新建一条记录/库存行，确认主键不会与已迁移数据冲突。
5. 切换运行：设置 `DATABASE_URL=<postgres_dsn>` 或更新 `config/settings.yaml`。Postgres 启动时不会执行 `SQLModel.metadata.create_all`；如果没有 `alembic_version` 或不是 Alembic head，服务会直接失败并要求先跑迁移。
6. 回归验证：
   - `pytest backend/tests -q`
   - `./scripts/run_preflight.sh`

### 回滚

1. 停服务。
2. 把 DSN 改回 SQLite（`sqlite:///data/app.db`）。
3. 重启服务并运行验收脚本。
4. Postgres 侧可直接重建，不影响原 SQLite。

### 灾难恢复

- 备份（Postgres）：
  - macOS/Linux: `DATABASE_URL=<postgres_dsn> ./scripts/backup_live_data_pg.sh`
  - Windows: `.\scripts\backup_live_data_pg.ps1 -DatabaseUrl <postgres_dsn>`
- 恢复（Postgres）：
  - macOS/Linux:
    - `YES_I_UNDERSTAND_DATA_RISK=1 DATABASE_URL=<postgres_dsn> BACKUP_PATH=data/backups/app-YYYYMMDD-HHMMSS.dump ./scripts/restore_live_data_pg.sh`
  - Windows:
    - `.\scripts\restore_live_data_pg.ps1 -DatabaseUrl <postgres_dsn> -BackupPath .\data\backups\app-YYYYMMDD-HHMMSS.dump -YesIUnderstandDataRisk`

## Deutsch

### Ziel

Migration der Geschaeftstabellen nach Single-Node-Postgres ohne Aenderung der bestehenden SQLite-Quelldatenbank; inklusive ruecksetzbarer ETL-, Backup- und Restore-Kette.

G6 bereitet nur den Postgres-Cutover und die `factory_id`-Spalte vor. Die Laufzeit bleibt Single-Factory; `factory_id` bedeutet noch keine aktive Mehrwerk-Isolation. Mehrwerk-Query-Isolation, Unique-Constraint-Anpassungen und Berechtigungsgrenzen muessen bis zu einer spaeteren Freigabe deaktiviert bleiben.

`user_sessions` und `security_secrets` bleiben in G6 globale Sicherheitstabellen und werden nicht nach `factory_id` partitioniert. Sie enthalten Sitzungen und Systemgeheimnisse, keine werkslokale Geschaeftsidentitaet; echte Mehrwerk-Isolation muss diese Tabellen spaeter separat pruefen.

### Voraussetzungen

1. SQLite sichern: `./scripts/backup_live_data.sh`
2. Abhaengigkeiten: `pip install -e ".[dev]"`
3. Postgres-DSN vorbereiten: `postgresql://<user>:<pass>@<host>:5432/<db>`
4. In `config/settings.yaml` setzen:

```yaml
database:
  dsn: postgresql://<user>:<pass>@<host>:5432/<db>
```

### Migrationsablauf

1. Zielschema in Postgres ausrollen:
   - `DATABASE_URL=<postgres_dsn> ./.venv/bin/alembic upgrade head`
2. Einmal-ETL ausfuehren (SQLite bleibt unveraendert):
   - `./.venv/bin/python scripts/etl_sqlite_to_postgres.py --sqlite-url sqlite:////abs/path/app.db --postgres-url <postgres_dsn> --factory-id factory_a --report-json /tmp/g6_etl_report.json`
3. Abgleich: pro Tabelle `source == target == post_commit_target`; Tabellen mit `id` muessen im Postgres-Bericht `sequence_reset: 1` zeigen.
4. Smoke-Insert: nach dem ETL eine neue Record-/Inventory-Zeile in Postgres anlegen und pruefen, dass der Primaerschluessel nicht mit migrierten IDs kollidiert.
5. Runtime-DSN auf Postgres umstellen. Beim Postgres-Start wird `SQLModel.metadata.create_all` nicht ausgefuehrt; ohne `alembic_version` oder ohne Head-Revision bricht der Dienst mit klarer Fehlermeldung ab.
6. Regression laufen lassen:
   - `pytest backend/tests -q`
   - `./scripts/run_preflight.sh`

### Rollback

1. Dienst stoppen.
2. DSN auf SQLite zurueckstellen (`sqlite:///data/app.db`).
3. Dienst starten und Abnahme ausfuehren.
4. Postgres kann unabhaengig neu aufgebaut werden.

### Disaster Recovery

- Postgres-Backup:
  - macOS/Linux: `DATABASE_URL=<postgres_dsn> ./scripts/backup_live_data_pg.sh`
  - Windows: `.\scripts\backup_live_data_pg.ps1 -DatabaseUrl <postgres_dsn>`
- Postgres-Restore:
  - macOS/Linux:
    - `YES_I_UNDERSTAND_DATA_RISK=1 DATABASE_URL=<postgres_dsn> BACKUP_PATH=data/backups/app-YYYYMMDD-HHMMSS.dump ./scripts/restore_live_data_pg.sh`
  - Windows:
    - `.\scripts\restore_live_data_pg.ps1 -DatabaseUrl <postgres_dsn> -BackupPath .\data\backups\app-YYYYMMDD-HHMMSS.dump -YesIUnderstandDataRisk`

## English

### Goal

Migrate business tables to single-node Postgres without mutating the existing SQLite source, with a rollback-safe ETL + backup/restore loop.

G6 only prepares Postgres cutover and the `factory_id` schema field. Runtime remains single-factory; `factory_id` does not mean multi-factory isolation is active. Multi-factory query scoping, unique constraint changes, and permission boundaries must stay disabled until a later approved task.

`user_sessions` and `security_secrets` remain global security tables in G6 and are not partitioned by `factory_id`. They hold login sessions and system secrets, not factory-local business identity; any future real multi-factory isolation must review their scope separately.

### Preconditions

1. Back up SQLite first: `./scripts/backup_live_data.sh`
2. Install deps: `pip install -e ".[dev]"`
3. Prepare Postgres DSN: `postgresql://<user>:<pass>@<host>:5432/<db>`
4. Set `config/settings.yaml`:

```yaml
database:
  dsn: postgresql://<user>:<pass>@<host>:5432/<db>
```

### Migration Steps

1. Apply schema on target Postgres:
   - `DATABASE_URL=<postgres_dsn> ./.venv/bin/alembic upgrade head`
2. Run one-shot ETL (SQLite remains unchanged):
   - `./.venv/bin/python scripts/etl_sqlite_to_postgres.py --sqlite-url sqlite:////abs/path/app.db --postgres-url <postgres_dsn> --factory-id factory_a --report-json /tmp/g6_etl_report.json`
3. Reconcile row counts (`source == target == post_commit_target` for each table), and verify tables with `id` report `sequence_reset: 1` on Postgres.
4. Smoke insert: after ETL, insert one new record/inventory row into Postgres and verify the primary key does not collide with migrated IDs.
5. Switch runtime DSN to Postgres. Postgres startup does not run `SQLModel.metadata.create_all`; if `alembic_version` is missing or not at head, the service fails clearly and requires `alembic upgrade head` first.
6. Run regression:
   - `pytest backend/tests -q`
   - `./scripts/run_preflight.sh`

### Rollback

1. Stop service.
2. Switch DSN back to SQLite (`sqlite:///data/app.db`).
3. Restart service and run acceptance.
4. Rebuild Postgres independently if needed.

### Disaster Recovery

- Postgres backup:
  - macOS/Linux: `DATABASE_URL=<postgres_dsn> ./scripts/backup_live_data_pg.sh`
  - Windows: `.\scripts\backup_live_data_pg.ps1 -DatabaseUrl <postgres_dsn>`
- Postgres restore:
  - macOS/Linux:
    - `YES_I_UNDERSTAND_DATA_RISK=1 DATABASE_URL=<postgres_dsn> BACKUP_PATH=data/backups/app-YYYYMMDD-HHMMSS.dump ./scripts/restore_live_data_pg.sh`
  - Windows:
    - `.\scripts\restore_live_data_pg.ps1 -DatabaseUrl <postgres_dsn> -BackupPath .\data\backups\app-YYYYMMDD-HHMMSS.dump -YesIUnderstandDataRisk`
