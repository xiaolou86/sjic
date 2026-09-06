"""
模型管理路由蓝图
"""
from flask import Blueprint, jsonify, request, current_app
from app.extensions import db
from app.models import DetectionModel
from app.middleware.auth import token_required, role_required
from app.utils.storage import get_storage
from werkzeug.utils import secure_filename
from config import Config
import os
import tempfile
import json

model_bp = Blueprint('model', __name__)


def allowed_file(filename):
    """检查文件扩展名是否允许上传"""
    allowed_extensions = Config.ALLOWED_EXTENSIONS
    current_app.logger.info(f"Checking file extension for {filename}, allowed: {allowed_extensions}")
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


@model_bp.route('/api/models', methods=['GET'])
@token_required
@role_required('vendor')
def get_models():
    """
    获取所有模型
    ---
    tags:
      - 模型管理 (Models)
    summary: 获取可用检测模型列表
    security:
      - APIKeyHeader: []
    responses:
      200:
        description: 模型配置列表
    """
    models = DetectionModel.query.all()
    return jsonify([model.to_dict() for model in models])


@model_bp.route('/api/models/upload', methods=['POST'])
@token_required
@role_required('vendor')
def upload_model():
    """
    上传模型文件
    ---
    tags:
      - 模型管理 (Models)
    summary: 上传新的网络结构模型文件 (.pt, .onnx, .engine)
    security:
      - APIKeyHeader: []
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: file
        type: file
        required: true
        description: 模型文件
      - in: formData
        name: name
        type: string
        required: false
        description: 模型名称
      - in: formData
        name: description
        type: string
        required: false
        description: 模型描述
    responses:
      201:
        description: 模型上传成功
      400:
        description: 上传失败，文件格式不对等
    """
    temp_file = None
    try:
        current_app.logger.info("Model upload request received")

        if 'file' not in request.files:
            current_app.logger.error("No file part in the request")
            return jsonify({'error': '没有文件'}), 400

        file = request.files['file']

        if file.filename == '':
            current_app.logger.error("No selected file")
            return jsonify({'error': '未选择文件'}), 400

        if not allowed_file(file.filename):
            current_app.logger.error(f"File type not allowed: {file.filename}")
            return jsonify({'error': '不支持的文件类型'}), 400

        name = request.form.get('name', '')
        if not name:
            name = os.path.splitext(file.filename)[0]

        filename = secure_filename(file.filename)
        current_app.logger.info(f"Processing model upload: {name}, file: {filename}")

        with tempfile.NamedTemporaryFile(delete=False) as temp:
            temp_file = temp.name
            file.save(temp_file)

        # 写入当前 STORAGE_TYPE 对应的后端（NGINX 本地目录 / MinIO / OBS）
        get_storage().upload(filename, temp_file)

        labelmap_raw = request.form.get('labelmap')
        labelmap = None
        if labelmap_raw:
            try:
                labelmap = json.loads(labelmap_raw)
            except Exception:
                return jsonify({'error': 'labelmap 必须是合法 JSON'}), 400

        model = DetectionModel(
            name=name,
            path=filename,
            description=request.form.get('description', ''),
            labelmap=labelmap
        )

        db.session.add(model)
        db.session.commit()

        current_app.logger.info(f"Model uploaded successfully: {model.id}")
        return jsonify({'message': '模型上传成功', 'model': model.to_dict()}), 201

    except Exception as e:
        current_app.logger.error(f"Error uploading model: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500
    finally:
        if temp_file and os.path.exists(temp_file):
            os.unlink(temp_file)


@model_bp.route('/api/models/<int:model_id>', methods=['DELETE'])
@token_required
@role_required('vendor')
def delete_model(model_id):
    """
    删除模型
    ---
    tags:
      - 模型管理 (Models)
    summary: 删除指定的检测模型
    security:
      - APIKeyHeader: []
    parameters:
      - name: model_id
        in: path
        type: integer
        required: true
        description: 模型 ID
    responses:
      204:
        description: 模型删除成功
    """
    model = DetectionModel.query.get_or_404(model_id)
    storage_path = model.path
    try:
        if storage_path:
            get_storage().delete(storage_path)
    except Exception as e:
        current_app.logger.warning(f"Failed to delete model object {storage_path}: {e}")

    db.session.delete(model)
    db.session.commit()
    return '', 204


@model_bp.route('/api/models/<int:model_id>', methods=['PUT'])
@token_required
@role_required('vendor')
def update_model(model_id):
    """更新模型元数据（名称/描述/labelmap）"""
    try:
        model = DetectionModel.query.get_or_404(model_id)
        data = request.json or {}

        if 'name' in data:
            model.name = data['name']
        if 'description' in data:
            model.description = data['description']
        if 'labelmap' in data:
            model.labelmap = data['labelmap']

        db.session.commit()
        return jsonify(model.to_dict()), 200
    except Exception as e:
        current_app.logger.error(f"Error updating model: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
