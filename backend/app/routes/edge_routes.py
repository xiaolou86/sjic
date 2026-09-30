from flask import Blueprint, jsonify, request, current_app
from app.extensions import db, socketio
from app.models import Alert, Camera, EdgeNode
from app.middleware.auth import token_required
import os
from datetime import datetime
from config import Config

edge_bp = Blueprint('edge', __name__)


def _camera_id_set(values):
    ids = set()
    if not isinstance(values, list):
        return ids
    for raw in values:
        try:
            ids.add(int(raw))
        except (TypeError, ValueError):
            continue
    return ids

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
        message = request.form.get('message') or None
        task_id = request.form.get('task_id') or None
        algorithm_id = request.form.get('algorithm_id') or None
        
        # 接收图像文件
        image_file = request.files.get('image')
        image_url = ""
        
        if image_file:
            # 保存到警报文件夹。带框图进页面；同名 _raw 原图只落盘，供回溯标注。
            save_dir = Config.ALERT_FOLDER
            os.makedirs(save_dir, exist_ok=True)
            filename = f"edge_alert_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
            filepath = os.path.join(save_dir, filename)
            image_file.save(filepath)
            image_url = filename
            raw_file = request.files.get('raw_image')
            if raw_file:
                stem, ext = os.path.splitext(filename)
                raw_file.save(os.path.join(save_dir, f"{stem}_raw{ext or '.jpg'}"))

        # 写入数据库。名称一并记下，视频源日后删除时告警仍能显示来源。
        camera = None
        if camera_id not in (None, ''):
            try:
                camera = Camera.query.get(int(camera_id))
            except (TypeError, ValueError):
                camera = None
        alert = Alert(
            camera_id=camera_id,
            camera_name=camera.name if camera else None,
            task_id=int(task_id) if task_id else None,
            algorithm_id=int(algorithm_id) if algorithm_id else None,
            alert_type=alert_type,
            confidence=float(confidence),
            image_url=image_url,
            message=message,
            review_status='pending',
        )
        db.session.add(alert)
        db.session.commit()

        # 推送给前端 WebSocket 进行实时展示
        from app.utils.algorithm_catalog import label_for_alert_type
        payload = alert.to_dict()
        payload['alert_type_label'] = label_for_alert_type(alert.alert_type)
        socketio.emit('new_alert', payload)

        return jsonify({"success": True, "message": "Alert received successfully"}), 200

    except Exception as e:
        current_app.logger.error(f"Error receiving edge alert: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@edge_bp.route('/api/nodes', methods=['GET'])
@token_required
def get_nodes():
    """获取所有边缘节点列表"""
    try:
        nodes = EdgeNode.query.all()
        # 与前端约定：直接返回数组（axios 响应拦截器会返回 response.data）
        payload = [node.to_dict() for node in nodes]
        # #region agent log
        try:
            import json as _json, time as _time, os as _os, urllib.request as _urlreq
            _dbg = {
                "sessionId": "902a99",
                "hypothesisId": "H4",
                "location": "edge_routes.py:get_nodes",
                "message": "api/nodes response snapshot",
                "data": {
                    "count": len(payload),
                    "nodes": [{"id": n.get("id"), "status": n.get("status"), "last_heartbeat": n.get("last_heartbeat"), "mac": n.get("mac_address")} for n in payload],
                    "server_now": datetime.now().isoformat(),
                },
                "timestamp": int(_time.time() * 1000),
                "pid": _os.getpid(),
            }
            _line = _json.dumps(_dbg, ensure_ascii=False) + "\n"
            for _p in ("/app/logs/debug-902a99.log", "logs/debug-902a99.log", "debug-902a99.log"):
                try:
                    _os.makedirs(_os.path.dirname(_p) or ".", exist_ok=True)
                    with open(_p, "a", encoding="utf-8") as _f:
                        _f.write(_line)
                    break
                except Exception:
                    continue
            for _host in ("host.docker.internal", "127.0.0.1"):
                try:
                    _req = _urlreq.Request(
                        f"http://{_host}:7453/ingest/081782cc-6465-4a44-ac05-89d5ee6ce675",
                        data=_json.dumps(_dbg).encode("utf-8"),
                        headers={"Content-Type": "application/json", "X-Debug-Session-Id": "902a99"},
                        method="POST",
                    )
                    _urlreq.urlopen(_req, timeout=0.5)
                    break
                except Exception:
                    continue
        except Exception:
            pass
        # #endregion
        return jsonify(payload), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@edge_bp.route('/api/nodes/<int:node_id>', methods=['PUT'])
@token_required
def update_node(node_id):
    """更新边缘节点信息(如改名)"""
    try:
        node = EdgeNode.query.get(node_id)
        if not node:
            return jsonify({"error": "Node not found"}), 404
            
        data = request.json or {}
        if 'name' in data:
            node.name = data['name']
        # 新版：节点可用视频源列表（多选）
        removed_camera_ids = set()
        if 'bound_camera_ids' in data:
            old_ids = _camera_id_set(node.bound_cameras)
            ids = data.get('bound_camera_ids')
            if ids in ("", None):
                node.bound_cameras = None
                new_ids = set()
            elif not isinstance(ids, list):
                return jsonify({"error": "bound_camera_ids 必须是数组"}), 400
            else:
                normalized = []
                for x in ids:
                    if x in ("", None):
                        continue
                    try:
                        normalized.append(int(x))
                    except Exception:
                        return jsonify({"error": f"bound_camera_ids 包含非法值: {x}"}), 400
                # 去重并排序，便于一致性展示
                node.bound_cameras = sorted(list(set(normalized)))
                new_ids = set(node.bound_cameras)
            removed_camera_ids = old_ids - new_ids

        if removed_camera_ids:
            from app.services.detector import DetectorService
            DetectorService().stop_tasks_for_unbound_cameras(node.id, removed_camera_ids)

        db.session.commit()
        return jsonify(node.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@edge_bp.route('/api/nodes/<int:node_id>', methods=['DELETE'])
@token_required
def delete_node(node_id):
    """删除或强制下线边缘节点"""
    try:
        node = EdgeNode.query.get(node_id)
        if not node:
            return jsonify({"error": "Node not found"}), 404
            
        db.session.delete(node)
        db.session.commit()
        return '', 204
    except Exception as e:
        return jsonify({"error": str(e)}), 500
