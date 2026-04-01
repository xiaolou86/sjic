from flask import Blueprint, jsonify, request, current_app
from app.extensions import db, socketio
from app.models import Alert
import os
from datetime import datetime
from config import Config

edge_bp = Blueprint('edge', __name__)

@edge_bp.route('/api/edge/alerts', methods=['POST'])
def receive_alert():
    """
    接收来自边缘设备的告警数据（图片 + JSON数据）
    ---
    tags:
      - 边缘计算 (Edge Agent)
    summary: 接收边缘告警
    description: 专供内网边缘设备调用的接口，通过 HTTP POST (multipart/form-data) 提交告警和截图。
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: camera_id
        type: integer
        required: true
        description: 发生违规的摄像头 ID
      - in: formData
        name: alert_type
        type: string
        required: true
        description: 告警类型，比如 belt_broken
      - in: formData
        name: confidence
        type: number
        required: false
        description: YOLO 算法预测出的置信度 (0.0 - 1.0)
      - in: formData
        name: image
        type: file
        required: true
        description: 现场抓拍的实时视频帧 jpeg 截图
    responses:
      200:
        description: 告警接收成功并广播至 WebSocket
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
    """
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
