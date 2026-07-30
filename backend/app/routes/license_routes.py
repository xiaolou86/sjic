"""
License management routes.
"""
from flask import Blueprint, jsonify
from app.middleware.auth import token_required
from app.services.license_service import license_service


license_bp = Blueprint('license', __name__)


@license_bp.route('/api/license/status', methods=['GET'])
@token_required
def get_license_status():
    status = license_service.get_status()
    return jsonify(status), 200
