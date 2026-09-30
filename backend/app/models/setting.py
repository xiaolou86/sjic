from flask import current_app
from app.extensions import db
from datetime import datetime
from sqlalchemy.orm.attributes import flag_modified
import copy


class Setting(db.Model):
    __tablename__ = 'settings'

    id = db.Column(db.Integer, primary_key=True)
    config = db.Column(db.JSON, nullable=False, default=dict)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

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
            'log_level': 'INFO',
            'ui_theme': 'night-tech'
        },
        'branding': {
            'company_name': '',
            'product_name': '智算检测平台',
            'logo_filename': ''
        }
    }

    @classmethod
    def deep_merge(cls, base, override):
        """递归合并：override 覆盖 base，缺失键保留默认。"""
        result = copy.deepcopy(base) if base is not None else {}
        if not isinstance(override, dict):
            return result
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = cls.deep_merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    @classmethod
    def merged_config(cls, stored=None):
        return cls.deep_merge(cls.DEFAULT_CONFIG, stored or {})

    def __init__(self):
        super().__init__()
        current_app.logger.info("Creating new Setting instance")
        self.config = copy.deepcopy(self.DEFAULT_CONFIG)
        current_app.logger.info(f"Initial config: {self.config}")

    def to_dict(self):
        merged = self.merged_config(self.config)
        # 密码哈希只给登录校验用，不进设置接口和日志
        merged.pop('accounts', None)
        current_app.logger.info(f"Converting to dict, current config: {merged}")
        return merged

    def update(self, data):
        """更新设置（与默认值合并后写入）"""
        if self.config is None:
            current_app.logger.warning("Config was None, resetting to default")
            self.config = copy.deepcopy(self.DEFAULT_CONFIG)

        try:
            # 先与默认合并，再应用提交数据，确保新增配置节可写入
            base = self.merged_config(self.config)
            self.config = self.deep_merge(base, data or {})
            flag_modified(self, 'config')
        except Exception as e:
            current_app.logger.error(f"Error updating config: {str(e)}")
            raise
