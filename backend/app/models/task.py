from flask import current_app
from app.extensions import db
from app.utils.calibration import save_calibration_frame
from datetime import datetime

class Task(db.Model):
    __tablename__ = 'tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    confidence = db.Column(db.Float, default=0.5)  # 通用参数
    alertThreshold = db.Column(db.Integer, default=5)  # 通用参数
    modelId = db.Column(db.Integer, db.ForeignKey('detection_models.id'))
    cameraId = db.Column(db.Integer, db.ForeignKey('cameras.id'))
    algorithm_id = db.Column(db.Integer, db.ForeignKey('algorithms.id'))
    # 驾考混合任务：各最多绑定一个已发布算法（一个模型）。单算法任务这两列为空。
    od_algorithm_id = db.Column(db.Integer, db.ForeignKey('algorithms.id'), nullable=True)
    pose_algorithm_id = db.Column(db.Integer, db.ForeignKey('algorithms.id'), nullable=True)
    algorithm_parameters = db.Column(db.JSON)  # 所有算法特定参数
    status = db.Column(db.String(20), default='stopped')
    # 边缘架构新增字段
    edge_node_id = db.Column(db.Integer, db.ForeignKey('edge_nodes.id'), nullable=True) # 指派给哪个边缘节点执行
    run_status = db.Column(db.String(20), default='stopped') # 边缘端实际的运行状态: syncing, running, stopped, error
    # 每日运行时段（HH:MM）；两者都设置则为定时任务，由调度器按窗口启停
    schedule_start = db.Column(db.String(8), nullable=True)
    schedule_end = db.Column(db.String(8), nullable=True)
    # 用户手动停止后不再自动拉起，直到再次手动启动
    schedule_paused = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def has_schedule(self):
        return bool((self.schedule_start or '').strip() and (self.schedule_end or '').strip())

    def is_exam_pipeline(self):
        return bool(self.od_algorithm_id or self.pose_algorithm_id)

    def to_dict(self):
        algo = None
        if self.algorithm_id:
            from app.models.algorithm import Algorithm
            algo = Algorithm.query.get(self.algorithm_id)
        return {
            'id': self.id,
            'name': self.name,
            'confidence': self.confidence,
            'alertThreshold': self.alertThreshold,
            'cameraId': self.cameraId,
            'algorithm_id': self.algorithm_id,
            'algorithm_type': algo.type if algo else None,
            'algorithm_engine': algo.resolved_engine() if algo else ('exam_pipeline' if self.is_exam_pipeline() else None),
            'od_algorithm_id': self.od_algorithm_id,
            'pose_algorithm_id': self.pose_algorithm_id,
            'pipeline': 'exam' if self.is_exam_pipeline() else 'single',
            'edge_node_id': self.edge_node_id,
            'run_status': self.run_status,
            'algorithm_parameters': self.algorithm_parameters,
            'status': self.status,
            'schedule_start': self.schedule_start,
            'schedule_end': self.schedule_end,
            'schedule_paused': bool(self.schedule_paused),
            'is_scheduled': self.has_schedule(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        } 

    def save_calibration_image(self):
        """保存标定图像"""
        current_app.logger.info(f"Saving calibration image")
        if not self.algorithm_parameters or 'calibration' not in self.algorithm_parameters:
            return
        current_app.logger.info(f"Saving calibration image")
        calibration = self.algorithm_parameters['calibration']
        if 'frame' not in calibration or not calibration['frame'] or calibration['frame'] == '':
            return
        current_app.logger.info(f"Saving calibration image")
        try:
            # 保存图像
            frame_data = calibration.pop('frame')  # 移除 frame 数据并获取它
            image_path = save_calibration_frame(frame_data, self.id)
            
            # 更新标定参数
            calibration['image_path'] = image_path
            
            # 更新任务参数
            self.algorithm_parameters['calibration'] = calibration

            current_app.logger.info(f"Saving calibration image algorithm_parameters: {self.algorithm_parameters}")
            current_app.logger.info(f"Saving calibration image to: {image_path}")

            db.session.commit()
            
        except Exception as e:
            current_app.logger.error(f"Error saving calibration image: {str(e)}")
            raise
