# 从 `create_all` 迁到纯 Alembic — 三步操作清单

面向当前 `backend/` 现状编写。执行前请先阅读 **第 0 节「现状与风险」**。

---

## 第 0 节：现状与风险（必读）

### 当前存在的三套改表机制

| 机制 | 位置 | 作用 | 问题 |
|------|------|------|------|
| `db.create_all()` | `app/__init__.py`、`run.py`、`Makefile`、`run.ps1` | 按模型**新建**表 | **不会**给已有表加列；与 Alembic 双轨 |
| `ensure_legacy_schema()` | `app/utils/db_compat.py` | 启动时补 `bound_cameras`、`labelmap` | 与 Alembic 双轨，难追溯版本 |
| Alembic | `migrations/versions/001、002` | 增量迁移 | **不完整**（见下） |

### Alembic 目录（已补齐）

```text
migrations/
├── alembic.ini
├── env.py
├── script.py.mako
├── README.md
└── versions/
    ├── 000_initial_core_tables.py
    ├── 001_update_algorithm_and_task_models.py
    ├── 002_add_settings_table.py
    └── 003_core_edge_nodes_and_columns.py   ← head
```

迁移链：`000 → 001 → 002 → 003`。`edge_nodes`、`bound_cameras`、`labelmap` 等由 `003` 创建，不再依赖 `db_compat`。

### 迁完后的目标状态

- **唯一改表入口**：`flask db migrate` + `flask db upgrade`
- 生产/日常启动：**不再**调用 `db.create_all()`、`ensure_legacy_schema()`
- `db_compat.py`、`patch_db.py`：仅作历史说明或删除，不再用于新环境

---

## 第一步：补齐 Alembic 脚手架并建立「基线」

> 目标：让 `flask db upgrade` 能跑通，且与**当前线上/本地真实库结构**一致。

### 1.1 备份数据库

```powershell
cd D:\work\src\sjic\backend
# 默认 SQLite 路径（见 config.py）
Copy-Item .\instance\app.db .\instance\app.db.bak.$(Get-Date -Format 'yyyyMMdd-HHmmss')
```

若使用 `DATABASE_URL` 指向 PostgreSQL，用对应工具做 dump。

### 1.2 初始化 Flask-Migrate（若缺少 env.py）

在 `backend` 目录执行：

```powershell
cd D:\work\src\sjic\backend
$env:FLASK_APP = "run.py"

# 若 migrations\env.py 已存在，跳过 init，只做后续步骤
flask db init
```

若提示 `Directory migrations already exists`：

- **不要**覆盖整个目录（会丢掉 `versions/001、002`）
- 仅从其他已初始化的 Flask 项目复制缺失的 `env.py`、`script.py.mako`、`alembic.ini`，或手动合并

### 1.3 统一模型导入（避免 autogenerate 漏表）

在 `migrations/env.py` 的 `run_migrations_online()` / `run_migrations_offline()` 之前，确保导入**全部**模型，例如：

```python
# migrations/env.py 内（示意）
from app import create_app
from app.extensions import db
import app.models  # 触发 models/__init__.py 里所有 Model 注册
```

`app/models/__init__.py` 应包含：`Camera`, `DetectionModel`, `Alert`, `Task`, `Algorithm`, `Log`, `Setting`, `EdgeNode`。

### 1.4 处理「已有库」vs「空库」两条路径

#### 路径 A — 已有生产/开发库（表已存在，由 create_all 建过）

1. 修复迁移链：新增 `000_baseline.py` **或** 将 `001` 的 `down_revision` 改为 `None`（二选一，团队统一即可）。
2. 生成**基线 revision**，把当前模型与库对齐，例如：

```powershell
flask db revision -m "baseline_schema" --autogenerate
# 生成 003_xxx.py 后，人工检查：
#   - 若 autogenerate 想 DROP/CREATE 已有表，应删掉危险操作，只保留「缺失的列/表」
```

3. 对**已经是最新结构**的库打 stamp（不执行 DDL）：

```powershell
flask db stamp head
```

4. 验证：

```powershell
flask db current
flask db history
```

#### 路径 B — 全新环境（空库）

```powershell
flask db upgrade
```

应一次性创建全部 Core 表，**无需** `create_all()`。

### 1.5 把 `db_compat` 里已有列收编进 Alembic

当前 `db_compat.py` 维护的列：

| 表 | 列 |
|----|-----|
| `edge_nodes` | `bound_cameras` |
| `detection_models` | `labelmap` |

在基线 revision 或单独 revision 中写明 `ADD COLUMN`（若基线已包含则跳过）。  
收编完成后，在文档中标记 `db_compat` 为 **deprecated**（第二步再停调用）。

### 1.6 把 `patch_db.py` 中历史补丁对照进迁移

`patch_db.py` 曾手动添加：

- `tasks.edge_node_id`、`tasks.run_status`
- `algorithms.model_id`、`algorithms.labels`

若你的库是靠 `create_all` + 模型定义的，可能已有这些列。用 SQLite 检查：

```powershell
sqlite3 .\instance\app.db "PRAGMA table_info(tasks);"
sqlite3 .\instance\app.db "PRAGMA table_info(algorithms);"
```

**原则**：以**当前 `app/models/*.py` 为准**生成一条「补齐缺失列」的 revision，不要重复 ADD。

### 1.7 第一步完成标准（Checklist）

- [ ] `migrations/env.py` 存在且能 `flask db upgrade`
- [ ] `flask db current` 显示 `head`
- [ ] 新克隆环境：仅 `upgrade` 即可用，不依赖 `create_all`
- [ ] `001`、`002` 与基线 revision 链条无分叉（`flask db heads` 只有 1 个 head）
- [ ] `db_compat` 中的列已全部出现在某个 revision 中

---

## 第二步：下线 `create_all` 与 `db_compat`

> 目标：应用启动不再隐式改表；改表必须走 migration。

### 2.1 修改 `app/__init__.py`

**删除或条件化**：

```python
db.create_all()
ensure_legacy_schema(app)
```

推荐改为配置开关（仅本地首次可选）：

```python
# config.py 增加
AUTO_CREATE_DB = os.environ.get('AUTO_CREATE_DB', 'false').lower() == 'true'

# __init__.py
if app.config.get('AUTO_CREATE_DB'):
    db.create_all()  # 仅开发应急，禁止生产开启
else:
    app.logger.info('Skipping create_all; use flask db upgrade')
```

生产、`docker-compose`、正式部署：**不设** `AUTO_CREATE_DB` 或设为 `false`。

### 2.2 修改 `run.py`

删除 `init_db()` 中的 `db.create_all()`，或改为提示：

```text
请执行: flask db upgrade
```

### 2.3 修改脚本入口

| 文件 | 原行为 | 改为 |
|------|--------|------|
| `Makefile` `init-db` | `db.create_all()` | `flask db upgrade` |
| `run.ps1` `init-db` | 同上 | 同上 |
| `run.bat` | 若有 `create_all` | 同上 |

示例 `Makefile`：

```makefile
init-db:
	cd $(BACKEND_DIR) && export FLASK_APP=run.py && flask db upgrade
```

### 2.4 停用 `db_compat` 与 `patch_db`

- `create_app()` 中移除 `ensure_legacy_schema(app)` 调用
- `scripts/migrate_legacy_schema.py`：标记废弃，或改为仅打印「请使用 flask db upgrade」
- `patch_db.py`：移到 `backend/scripts/legacy/`，README 注明**禁止**对新环境执行

### 2.5 部署流程写入 Runbook

**启动 backend 之前**（Docker entrypoint / systemd / 手动）：

```powershell
cd backend
$env:FLASK_APP = "run.py"
flask db upgrade
python run.py
```

### 2.6 第二步完成标准（Checklist）

- [ ] 冷启动 backend 不调用 `create_all` / `db_compat`
- [ ] `make init-db` / `.\run.ps1 init-db` 执行的是 `flask db upgrade`
- [ ] 团队成员文档已更新：新字段**禁止**手改 SQLite
- [ ] 现有环境跑过一次 `upgrade` 无报错

---

## 第三步：建立日常迁移规范（长期）

> 目标：多行业、多扩展表共存时，迁移可评审、可回滚、不冲突。

### 3.1 标准工作流（每次改模型）

```powershell
cd D:\work\src\sjic\backend
$env:FLASK_APP = "run.py"

# 1. 改 app/models/*.py 或 app/extensions/*/models.py

# 2. 生成迁移（命名建议带前缀）
flask db migrate -m "core_alerts_add_metadata"
# 或
flask db migrate -m "exam_add_sessions"

# 3. 人工检查 migrations/versions/xxxx_*.py
#    - 删掉误报的 drop_table
#    - SQLite 下注意 batch_alter_table

# 4. 本地应用
flask db upgrade

# 5. 提交代码：模型 + migration 文件同 PR
```

### 3.2 命名约定（单仓库多业务）

```text
migrations/versions/
  20260508_core_xxx.py      # 平台表
  20260510_exam_xxx.py      # 驾考扩展（可选目录注释）
```

文件名或 `message` 中带 `core_` / `exam_` / `mining_`，便于 Code Review。

### 3.3 Core vs Extension 表规则

| 类型 | 迁移方式 | 示例 |
|------|----------|------|
| Core 表/列 | 所有环境 `upgrade` | `alerts`, `tasks`, `edge_nodes` |
| Extension 表 | 可全环境建空表；或文档注明仅驾考部署 | `exam_sites`, `exam_rooms` |
| 仅 JSON 可表达 | 优先不放 Core 列 | `algorithm_parameters`, `alerts.metadata` |

**禁止**：为矿山单独加 `tasks.xxx`、为驾考单独加 `tasks.yyy` 叠十列。

### 3.4 合并冲突处理

两人同时生成 migration 出现两个 head：

```powershell
flask db heads
flask db merge heads -m "merge_migrations"
flask db upgrade
```

### 3.5 回滚策略

- 开发环境：`flask db downgrade -1`（需 revision 写了 `downgrade()`）
- 生产：**优先**向前修复（新 revision 补列），避免 downgrade 丢数据

### 3.6 PR 检查清单（贴到 PR 模板）

- [ ] 包含 Alembic revision 文件
- [ ] 本地 `flask db upgrade` 通过
- [ ] 未修改 `db_compat.py` / `patch_db.py` 作为新方案
- [ ] 未在 `create_app` 恢复 `create_all`
- [ ] 若为 Core 表变更，已确认是否影响矿山/驾考所有部署

### 3.7 第三步完成标准（Checklist）

- [ ] 团队默认使用「第三节工作流」
- [ ] README / 部署文档指向本文
- [ ] 新功能（如 exam 表）第一条 migration 已按命名规范提交

---

## 附录 A：推荐目录结构（迁完后）

```text
backend/
├── app/
│   ├── models/              # Core 模型
│   └── extensions/
│       └── exam/models.py   # Extension 模型（未来）
├── migrations/
│   ├── env.py
│   ├── alembic.ini
│   ├── script.py.mako
│   └── versions/
│       ├── 001_...
│       ├── 002_...
│       └── 003_baseline_schema.py
├── docs/
│   └── DATABASE_MIGRATION.md   # 本文
└── scripts/
    └── legacy/
        └── patch_db.py         # 仅留档
```

## 附录 B：常用命令速查

```powershell
$env:FLASK_APP = "run.py"
flask db current          # 当前版本
flask db history          # 历史
flask db upgrade          # 应用到最新
flask db downgrade -1     # 回退一步（慎用）
flask db migrate -m "msg" # 根据模型差异生成 revision
flask db stamp head       # 已有库标记为最新（不执行 SQL）
flask db heads            # 检查是否多个 head
```

## 附录 C：与「行业扩展表」的关系

- **一个** `migrations/versions/` 链即可，不必为多行业拆多个 migrations 目录。
- 驾考表 `exam_*` 用独立 revision 添加；矿山部署可选择仍 `upgrade`（空表），与 Core 策略见平台架构文档。
- 改表冲突来自 **Core 表多人乱改**，不是「单仓库」本身；用 revision 命名 + PR 检查清单规避。

---

## 执行顺序总览

```text
第一步  补齐 Alembic + 基线 revision + stamp/upgrade  →  库结构与 head 一致
第二步  去掉 create_all / db_compat，改 init-db 脚本   →  启动不再隐式改表
第三步  团队规范 + 新功能只走 migrate                  →  长期可维护
```

建议用 **一个短迭代（如 0.5～1 天）** 完成第一、二步，第三步写入团队约定即可。

---

*文档版本：baseline head = revision `003`。若后续已执行迁移，请在本文件顶部记录实际 head revision id。*

