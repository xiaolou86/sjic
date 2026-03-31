"""
模型管理路由蓝图
"""
from flask import Blueprint, jsonify, request, current_app
from app.extensions import db
from app.models import DetectionModel
from app.middleware.auth import token_required
from werkzeug.utils import secure_filename
from config import Config
import os
import tempfile
import shutil

model_bp = Blueprint('model', __name__)


def allowed_file(filename):
    """检查文件扩展名是否允许上传"""
    allowed_extensions = Config.ALLOWED_EXTENSIONS
    current_app.logger.info(f"Checking file extension for {filename}, allowed: {allowed_extensions}")
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


@model_bp.route('/api/models', methods=['GET'])
@token_required
def get_models():
    """获取所有模型"""
    models = DetectionModel.query.all()
    return jsonify([model.to_dict() for model in models])


@model_bp.route('/api/models/upload', methods=['POST'])
@token_required
def upload_model():
    """上传模型文件"""
    temp_file = None
    try:
        current_app.logger.info("Model upload request received")
        current_app.logger.info(f"Request content type: {request.content_type}")
        current_app.logger.info(f"Request headers: {dict(request.headers)}")
        current_app.logger.info(f"Request files: {list(request.files.keys()) if request.files else 'No files'}")
        current_app.logger.info(f"Request form: {dict(request.form) if request.form else 'No form data'}")

        # 检查请求中是否有文件
        if 'file' not in request.files:
            current_app.logger.error("No file part in the request")
            return jsonify({'error': '没有文件'}), 400

        file = request.files['file']

        # 检查文件名是否为空
        if file.filename == '':
            current_app.logger.error("No selected file")
            return jsonify({'error': '未选择文件'}), 400

        # 检查文件类型
        if not allowed_file(file.filename):
            current_app.logger.error(f"File type not allowed: {file.filename}")
            return jsonify({'error': '不支持的文件类型'}), 400

        # 获取模型名称
        name = request.form.get('name', '')
        if not name:
            name = os.path.splitext(file.filename)[0]

        current_app.logger.info(f"Processing model upload: {name}, file: {file.filename}")

        # 使用临时文件
        with tempfile.NamedTemporaryFile(delete=False) as temp:
            temp_file = temp.name
            file.save(temp_file)

            # 确保模型目录存在
            model_folder = current_app.config.get('MODEL_FOLDER', Config.MODEL_FOLDER)
            os.makedirs(model_folder, exist_ok=True)

            # 保存文件
            filename = secure_filename(file.filename)
            file_path = os.path.join(model_folder, filename)

            # 复制临时文件到目标位置
            shutil.copy2(temp_file, file_path)

        # 创建模型记录
        model = DetectionModel(
            name=name,
            path=filename,
            description=request.form.get('description', '')
        )

        db.session.add(model)
        db.session.commit()

        current_app.logger.info(f"Model uploaded successfully: {model.id}")
        return jsonify({'message': '模型上传成功', 'model': model.to_dict()}), 201

    except Exception as e:
        current_app.logger.error(f"Error uploading model: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500
    finally:
        # 清理临时文件
        if temp_file and os.path.exists(temp_file):
            os.unlink(temp_file)


@model_bp.route('/api/models/<int:model_id>', methods=['DELETE'])
@token_required
def delete_model(model_id):
    """删除模型"""
    model = DetectionModel.query.get_or_404(model_id)
    db.session.delete(model)
    db.session.commit()
    return '', 204
