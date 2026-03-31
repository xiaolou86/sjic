"""
训练管理路由蓝图
"""
from flask import Blueprint, jsonify, request
from app.middleware.auth import token_required
from app.services.model_trainer import ModelTrainer

training_bp = Blueprint('training', __name__)

# 初始化服务
model_trainer = ModelTrainer()


@training_bp.route('/api/training/start', methods=['POST'])
@token_required
def start_training():
    """开始模型训练"""
    if 'dataset' not in request.files:
        return jsonify({'error': 'No dataset provided'}), 400

    dataset = request.files['dataset']
    config = request.form.get('config', '{}')

    try:
        result = model_trainer.train(dataset, config)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400
