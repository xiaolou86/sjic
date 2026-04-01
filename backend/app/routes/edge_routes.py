from flask import Blueprint, jsonify, request, current_app
from app.extensions import db, socketio
from app.models import Alert
import os
from datetime import datetime
from config import Config

edge_bp = Blueprint('edge', __name__)

@edge_bp.route('/api/edge/alerts', methods=['POST'])
def receive_alert():
    """接收来自边缘设备的告警数据（图片 + JSON数据）"""
    try:
        # 获取表单中的告警信息 (multipart/form-data)
        camera_id = request.form.get('camera_id')
        alert_type = request.form.get('alert_type')
        confidence = request.form.get('confidence', 0.0)
        
        # 接收图像文件
        image_file = request.files.get('image')
        image_url = ""
        
        if image_file:
            # 保存到警报文件夹
            save_dir = Config.ALERT_FOLDER
            os.makedirs(save_dir, exist_ok=True)
            filename = f"edge_alert_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
            filepath = os.path.join(save_dir, filename)
            image_file.save(filepath)
            image_url = filename

        # 写入数据库
        alert = Alert(
            camera_id=camera_id,
            alert_type=alert_type,
            confidence=float(confidence),
            image_url=image_url
        )
        db.session.add(alert)
        db.session.commit()

        # 推送给前端 WebSocket 进行实时展示
        socketio.emit('new_alert', alert.to_dict())

        return jsonify({"success": True, "message": "Alert received successfully"}), 200

    except Exception as e:
        current_app.logger.error(f"Error receiving edge alert: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
