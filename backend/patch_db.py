import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'instance', 'app.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # 增加 edge_node_id 列（作为外键不设 DEFAULT 防止报错）
    cursor.execute('ALTER TABLE tasks ADD COLUMN edge_node_id INTEGER')
    print("Added edge_node_id column.")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("edge_node_id already exists.")
    else:
        print("edge_node_id error:", e)

try:
    # 增加 run_status 列
    cursor.execute('ALTER TABLE tasks ADD COLUMN run_status VARCHAR(20) DEFAULT "stopped"')
    print("Added run_status column.")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("run_status already exists.")
    else:
        print("run_status error:", e)

conn.commit()

try:
    cursor.execute('ALTER TABLE algorithms ADD COLUMN model_id INTEGER')
    print("Added model_id to algorithms.")
except sqlite3.OperationalError as e:
    print("model_id error:", e)

try:
    cursor.execute('ALTER TABLE algorithms ADD COLUMN labels TEXT')
    print("Added labels to algorithms.")
except sqlite3.OperationalError as e:
    print("labels error:", e)

conn.commit()
conn.close()
print("Database patched successfully!")
