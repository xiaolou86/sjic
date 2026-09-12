from flask import current_app
from app.extensions import db
from datetime import datetime
import json
from sqlalchemy.orm.attributes import flag_modified

class Setting(db.Model):
    __tablename__ = 'settings'
    
    id = db.Column(db.Integer, primary_key=True)
    config = db.Column(db.JSON, nullable=False, default=dict)  # 存储所有配置项
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # 默认配置
    DEFAULT_CONFIG = {
        'external_alert_api': {
            'url': '',
            'token': '',
            'secret': ''
        },
        'alert': {
            'retention_days': 30,
            'image_quality': 95
        },
        'system': {
            'log_level': 'INFO'
        }
    }

    def __init__(self):
        super().__init__()
        current_app.logger.info("Creating new Setting instance")
        self.config = self.DEFAULT_CONFIG.copy()
        current_app.logger.info(f"Initial config: {self.config}")

    def to_dict(self):
        current_app.logger.info(f"Converting to dict, current config: {self.config}")
        return self.config

    def update(self, data):
        """更新设置"""
        current_app.logger.info(f"Updating config with data: {data}")
        current_app.logger.info(f"Current config before update: {self.config}")

        # 确保 config 不是 None
        if self.config is None:
            current_app.logger.warning("Config was None, resetting to default")
            self.config = self.DEFAULT_CONFIG.copy()

        # 递归更新配置
        def update_dict(current, new):
            for key, value in new.items():
                if key in current:
                    if isinstance(value, dict) and isinstance(current[key], dict):
                        update_dict(current[key], value)
                    else:
                        current_app.logger.info(f"Updating {key}: {current[key]} -> {value}")
                        current[key] = value

        try:
            update_dict(self.config, data)
            current_app.logger.info(f"Config after update: {self.config}")
            
            # 显式标记 config 字段已被修改
            flag_modified(self, 'config')
            
        except Exception as e:
            current_app.logger.error(f"Error updating config: {str(e)}")
            raise
