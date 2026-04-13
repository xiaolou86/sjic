from datetime import datetime
from app.extensions import db

class EdgeNode(db.Model):
    __tablename__ = 'edge_nodes'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    mac_address = db.Column(db.String(30), unique=True, nullable=False)
    ip_address = db.Column(db.String(50))
    architecture = db.Column(db.String(20)) # e.g., 'rk3588', 'jetson', 'x86'
    status = db.Column(db.String(20), default='offline') # online, offline, fault
    last_heartbeat = db.Column(db.DateTime)
    hardware_status = db.Column(db.JSON) # CPU, RAM, GPU, current running tasks
    # 节点可用视频源列表（camera_id 列表）。用于：
    # - 任务创建时过滤“该节点可访问的视频源”
    # - 本地视频源（例如文件路径/USB索引）通常只能在对应节点上访问
    bound_cameras = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    tasks = db.relationship('Task', backref='edge_node', lazy=True)

    def to_dict(self):
        bound_camera_ids = []
        if isinstance(self.bound_cameras, list):
            bound_camera_ids = [int(x) for x in self.bound_cameras if str(x).strip() != ""]

        return {
            'id': self.id,
            'name': self.name,
            'mac_address': self.mac_address,
            'ip_address': self.ip_address,
            'architecture': self.architecture,
            'status': self.status,
            'last_heartbeat': self.last_heartbeat.strftime('%Y-%m-%d %H:%M:%S') if self.last_heartbeat else None,
            'hardware_status': self.hardware_status,
            'bound_camera_ids': bound_camera_ids,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }
