from flask import jsonify, request, Response, send_from_directory, stream_with_context
from app import app, db, socketio
from app.models import Alert, Camera, DetectionModel, Algorithm, Setting
from app.services.detector import DetectorService
from app.services.model_trainer import ModelTrainer
from app.models import Task, Log
import os
from pathlib import Path
from werkzeug.utils import secure_filename
from config import Config
from app.middleware.auth import token_required
import cv2
import time
from app.utils.calibration import get_calibration_image
import subprocess
import tempfile
import base64
from app import sock
import numpy as np
import shutil


# 初始化服务
detector_service = DetectorService()
model_trainer = ModelTrainer()

# 摄像头相关路由
@app.route('/api/cameras', methods=['GET'])
@token_required
def get_cameras():
    """获取所有摄像头"""
    try:
        cameras = Camera.query.all()
        app.logger.info([camera.to_dict() for camera in cameras])
        return jsonify([camera.to_dict() for camera in cameras])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cameras', methods=['POST'])
@token_required
def create_camera():
    """创建新摄像头"""
    try:
        data = request.json
        app.logger.info(f"Creating new camera: {data}")
        
        camera = Camera(
            name=data['name'],
            url=data['url']
        )
        db.session.add(camera)
        db.session.commit()
        
        app.logger.info(f"Camera created successfully: id={camera.id}")
        return jsonify(camera.to_dict()), 201
    except Exception as e:
        app.logger.error(f"Failed to create camera: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/cameras/<int:camera_id>', methods=['DELETE'])
@token_required
def delete_camera(camera_id):
    """删除摄像头"""
    camera = Camera.query.get_or_404(camera_id)
    db.session.delete(camera)
    db.session.commit()
    return '', 204

# 模型相关路由
@app.route('/api/models', methods=['GET'])
@token_required
def get_models():
    """获取所有模型"""
    models = DetectionModel.query.all()
    return jsonify([model.to_dict() for model in models])

def allowed_file(filename):
    """检查文件扩展名是否允许上传"""
    allowed_extensions = Config.ALLOWED_EXTENSIONS
    app.logger.info(f"Checking file extension for {filename}, allowed: {allowed_extensions}")
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

@app.route('/api/models/upload', methods=['POST'])
@token_required
def upload_model():
    """上传模型文件"""
    temp_file = None
    try:
        app.logger.info("Model upload request received")
        app.logger.info(f"Request content type: {request.content_type}")
        app.logger.info(f"Request headers: {dict(request.headers)}")
        app.logger.info(f"Request files: {list(request.files.keys()) if request.files else 'No files'}")
        app.logger.info(f"Request form: {dict(request.form) if request.form else 'No form data'}")
        
        # 检查请求中是否有文件
        if 'file' not in request.files:
            app.logger.error("No file part in the request")
            return jsonify({'error': '没有文件'}), 400
            
        file = request.files['file']
        
        # 检查文件名是否为空
        if file.filename == '':
            app.logger.error("No selected file")
            return jsonify({'error': '未选择文件'}), 400
            
        # 检查文件类型
        if not allowed_file(file.filename):
            app.logger.error(f"File type not allowed: {file.filename}")
            return jsonify({'error': '不支持的文件类型'}), 400
            
        # 获取模型名称
        name = request.form.get('name', '')
        if not name:
            name = os.path.splitext(file.filename)[0]
            
        app.logger.info(f"Processing model upload: {name}, file: {file.filename}")
        
        # 使用临时文件
        with tempfile.NamedTemporaryFile(delete=False) as temp:
            temp_file = temp.name
            file.save(temp_file)
            
            # 确保模型目录存在
            model_folder = app.config.get('MODEL_FOLDER', Config.MODEL_FOLDER)
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
        
        app.logger.info(f"Model uploaded successfully: {model.id}")
        return jsonify({'message': '模型上传成功', 'model': model.to_dict()}), 201
        
    except Exception as e:
        app.logger.error(f"Error uploading model: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500
    finally:
        # 清理临时文件
        if temp_file and os.path.exists(temp_file):
            os.unlink(temp_file)

@app.route('/api/models/<int:model_id>', methods=['DELETE'])
@token_required 
def delete_model(model_id):
    """删除模型"""
    model = DetectionModel.query.get_or_404(model_id)
    db.session.delete(model)
    db.session.commit()
    return '', 204

# 检测相关路由
@app.route('/api/detection/start', methods=['POST'])
@token_required
def start_detection():
    """启动检测任务"""
    try:
        data = request.json
        task_id = data.get('task_id')
        
        if not task_id:
            return jsonify({'error': 'Task ID is required'}), 400
        
        result = detector_service.start_detection(task_id)
        
        if result['success']:
            return jsonify({'message': result['message']}), 200
        else:
            return jsonify({'error': result['message']}), 400
            
    except Exception as e:
        app.logger.error(f"Error starting detection: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/detection/stop', methods=['POST'])
@token_required
def stop_detection():
    """停止检测任务"""
    try:
        data = request.json
        task_id = data.get('task_id')
        
        if not task_id:
            return jsonify({'error': 'Task ID is required'}), 400
        
        result = detector_service.stop_detection(task_id)
        
        if result['success']:
            return jsonify({'message': result['message']}), 200
        else:
            return jsonify({'error': result['message']}), 400
            
    except Exception as e:
        app.logger.error(f"Error stopping detection: {str(e)}")
        return jsonify({'error': str(e)}), 500

# 告警相关路由
@app.route('/api/alerts', methods=['GET'])
@token_required
def get_alerts():
    """获取告警记录，支持分页"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # 获取分页数据
        pagination = Alert.query.order_by(Alert.timestamp.desc()).paginate(
            page=page, 
            per_page=per_page,
            error_out=False
        )
        
        alerts = pagination.items
        
        return jsonify({
            'items': [alert.to_dict() for alert in alerts],
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': page
        })
        
    except Exception as e:
        app.logger.error(f"Error getting alerts: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts', methods=['POST'])
@token_required 
def create_alert():
    """创建新告警"""
    data = request.json
    
    camera = Camera.query.get(data['camera_id'])
    if not camera:
        return jsonify({'error': 'Camera not found'}), 404
        
    alert = Alert(
        camera_id=data['camera_id'],
        alert_type=data['alert_type'],
        confidence=data.get('confidence'),
        image_url=data.get('image_url')
    )
    
    db.session.add(alert)
    db.session.commit()
    
    # 通过WebSocket发送实时告警
    socketio.emit('new_alert', alert.to_dict())
    
    return jsonify(alert.to_dict()), 201

@app.route('/api/alerts/<int:alert_id>', methods=['DELETE'])
@token_required 
def delete_alert(alert_id):
    """删除告警记录"""
    alert = Alert.query.get_or_404(alert_id)
    db.session.delete(alert)
    db.session.commit()
    return '', 204

# 训练相关路由
@app.route('/api/training/start', methods=['POST'])
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

# 错误处理
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/algorithms', methods=['GET'])
@token_required 
def get_algorithms():
    """获取算法"""
    algorithms = Algorithm.query.all()
    return jsonify([algorithm.to_dict() for algorithm in algorithms])

@app.route('/api/algorithms', methods=['POST'])
@token_required 
def create_algorithm():
    """创建新算法"""
    data = request.json
    algorithm = Algorithm(**data)
    db.session.add(algorithm)
    db.session.commit()
    return jsonify(algorithm.to_dict()), 201

@app.route('/api/tasks', methods=['GET'])
@token_required 
def get_tasks():
    """获取算法设置"""
    tasks = Task.query.all()
    return jsonify([task.to_dict() for task in tasks])

@app.route('/api/tasks', methods=['POST'])
@token_required 
def create_tasks():
    """创建算法设置"""
    data = request.json
    app.logger.info(f"Creating new task: {data}")
    task = Task(**data)
    task.save_calibration_image()
    db.session.add(task)
    db.session.commit()
    return jsonify(task.to_dict()), 201

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
@token_required
def update_tasks(task_id):
    """更新算法设置"""
    try:
        data = request.json
        #app.logger.info(f"Updating task: {data}")
        task = Task.query.get_or_404(task_id)
        
        for key, value in data.items():
            if hasattr(task, key):
                setattr(task, key, value)
        
        task.save_calibration_image()
        db.session.add(task)  # 确保对象被跟踪
        db.session.commit()
        
        app.logger.info(f"Task updated successfully: {task.to_dict()}")
        return jsonify(task.to_dict())
        
    except Exception as e:
        app.logger.error(f"Error updating task: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@token_required 
def delete_tasks(task_id):
    """删除算法设置"""
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    return '', 204

@app.route('/api/tasks/<int:task_id>/detail', methods=['GET'])
@token_required 
def get_task_detail(task_id):
    task = Task.query.get_or_404(task_id)
    
    # 获取任务详情，包括标定图像
    task_data = task.to_dict()
    
    # 如果有标定图像，添加图像数据
    if task.algorithm_parameters and 'calibration' in task.algorithm_parameters:
        calibration = task.algorithm_parameters['calibration']
        if 'image_path' in calibration:
            # 获取图像数据
            image_data = get_calibration_image(task_id)
            if image_data:
                calibration['image_data'] = image_data
    
    return jsonify(task_data)

@app.route('/api/logs', methods=['GET'])
@token_required
def get_logs():
    """获取系统日志"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    logs = Log.query.order_by(Log.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify({
        'items': [log.to_dict() for log in logs.items],
        'total': logs.total,
        'pages': logs.pages,
        'current_page': logs.page
    })

@app.route('/api/logs', methods=['DELETE'])
@token_required
def clear_logs():
    """清除所有日志"""
    Log.query.delete()
    db.session.commit()
    return '', 204

@app.route('/api/logs/delete/<int:id>', methods=['DELETE'])
@token_required
def delete_log(id):
    log = Log.query.get(id)
    db.session.delete(log)
    db.session.commit()
    return jsonify({"status": "success"})

@app.route('/api/cameras/capture', methods=['POST'])
def capture_frame():
    """获取摄像头当前帧"""
    try:
        data = request.json
        camera_id = data.get('camera_id')
        
        # 获取摄像头
        camera = Camera.query.get_or_404(camera_id)
        cap = cv2.VideoCapture(camera.get_rtsp_url())
        
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open camera: {camera_id}")
            
        # 读取一帧
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            raise RuntimeError("Failed to capture frame")
            
        # 将图片编码为JPEG
        _, buffer = cv2.imencode('.jpg', frame)
        
        # 确保返回正确的 MIME 类型和二进制数据
        return Response(
            buffer.tobytes(),
            mimetype='image/jpeg',
            headers={
                'Content-Type': 'image/jpeg',
                'Content-Disposition': 'inline'
            }
        )
    except Exception as e:
        app.logger.error(f"Capture frame error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@socketio.on('connect')
def handle_connect():
    """处理连接"""
    app.logger.info('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    """处理断开连接"""
    app.logger.info('Client disconnected')

@socketio.on('start_stream')
def handle_start_stream(data):
    """处理开始流请求"""
    cap = None
    try:
        camera_id = data.get('camera_id')
        camera = Camera.query.get_or_404(camera_id)
        cap = cv2.VideoCapture(camera.get_rtsp_url())
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            # 将帧编码为JPEG
            _, buffer = cv2.imencode('.jpg', frame)
            frame_data = buffer.tobytes()
            
            # 发送帧到客户端
            socketio.emit('frame', frame_data, room=request.sid)
            
            # 控制帧率
            socketio.sleep(1/30)  # 30fps
            
    except Exception as e:
        app.logger.error(f"Stream error: {str(e)}")
    finally:
        if cap:
            cap.release()

@app.route('/api/settings', methods=['GET'])
@token_required
def get_settings():
    """获取系统设置"""
    try:
        settings = Setting.query.first()
        if not settings:
            settings = Setting()  # 使用默认值
            db.session.add(settings)
            db.session.commit()
        return jsonify(settings.to_dict())
    except Exception as e:
        app.logger.error(f"Error getting settings: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings', methods=['POST'])
@token_required
def update_settings():
    """更新系统设置"""
    try:
        data = request.get_json()
        app.logger.info(f"Received settings update: {data}")
        
        settings = Setting.query.first()
        if not settings:
            settings = Setting()
            db.session.add(settings)
        
        # 更新设置
        settings.update(data)
        
        # 提交更改
        try:
            db.session.commit()
            app.logger.info("Settings committed to database")
            
            # 验证更新
            updated_settings = Setting.query.get(settings.id)
            app.logger.info(f"Verified settings after commit: {updated_settings.config}")
            
            return jsonify({'message': 'Settings updated successfully'})
        except Exception as e:
            app.logger.error(f"Error committing settings: {str(e)}")
            db.session.rollback()
            raise
            
    except Exception as e:
        app.logger.error(f"Error updating settings: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts/images/<path:filename>')
def get_alert_image(filename):
    """获取告警图片"""
    try:
        return send_from_directory(app.config['ALERT_FOLDER'], filename)
    except Exception as e:
        app.logger.error(f"Error getting alert image: {str(e)}")
        return jsonify({'error': str(e)}), 404

@app.route('/api/stream/<int:camera_id>', methods=['GET'])
@token_required
def stream_camera(camera_id):
    """将 RTSP 流转换为 HTTP 流 (MPEG-TS)"""
    try:
        camera = Camera.query.get_or_404(camera_id)
        rtsp_url = camera.url
        
        # 添加 CORS 头
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
            'Content-Type': 'video/mp2t'
        }
        
        def generate():
            # 使用更简单、更兼容的 FFmpeg 参数
            cmd = [
                'ffmpeg',
                '-i', rtsp_url,
                '-f', 'mpegts',
                '-codec:v', 'mpeg1video',
                '-s', '640x360',    # 降低分辨率
                '-b:v', '800k',     # 降低比特率
                '-r', '30',         # 提高帧率
                '-bf', '0',
                '-an',              # 禁用音频
                '-f', 'mpegts',
                '-'
            ]
            
            app.logger.info(f"Starting FFmpeg process for camera {camera_id}")
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # 记录 FFmpeg 错误输出（用于调试）
            def log_stderr():
                while True:
                    line = process.stderr.readline()
                    if not line:
                        break
                    app.logger.debug(f"FFmpeg: {line.decode().strip()}")
            
            import threading
            stderr_thread = threading.Thread(target=log_stderr)
            stderr_thread.daemon = True
            stderr_thread.start()
            
            try:
                # 持续发送视频数据
                while True:
                    data = process.stdout.read(4096)
                    if not data:
                        app.logger.warning(f"No data received from FFmpeg for camera {camera_id}")
                        break
                    yield data
            except Exception as e:
                app.logger.error(f"Error streaming camera {camera_id}: {str(e)}")
            finally:
                process.kill()
                app.logger.info(f"Terminated FFmpeg process for camera {camera_id}")
        
        return Response(
            stream_with_context(generate()),
            headers=headers
        )
    except Exception as e:
        app.logger.error(f"Error setting up stream for camera {camera_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/hls/<int:camera_id>/playlist.m3u8', methods=['GET'])
@token_required
def hls_playlist(camera_id):
    """生成 HLS 播放列表"""
    camera = Camera.query.get_or_404(camera_id)
    
    # 创建 HLS 目录
    hls_dir = os.path.join(app.config['TEMP_FOLDER'], f'hls_{camera_id}')
    os.makedirs(hls_dir, exist_ok=True)
    
    # 生成播放列表文件
    playlist_path = os.path.join(hls_dir, 'playlist.m3u8')
    segment_path = os.path.join(hls_dir, 'segment_%03d.ts')
    
    # 使用 FFmpeg 生成 HLS 流
    cmd = [
        'ffmpeg',
        '-i', camera.url,
        '-c:v', 'h264',
        '-crf', '21',
        '-preset', 'veryfast',
        '-g', '48',
        '-sc_threshold', '0',
        '-hls_time', '2',
        '-hls_list_size', '6',
        '-hls_flags', 'delete_segments',
        '-hls_segment_filename', segment_path,
        playlist_path
    ]
    
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 等待播放列表文件生成
    start_time = time.time()
    while not os.path.exists(playlist_path) and time.time() - start_time < 10:
        time.sleep(0.5)
    
    if not os.path.exists(playlist_path):
        return jsonify({'error': 'Failed to generate HLS playlist'}), 500
    
    with open(playlist_path, 'r') as f:
        playlist_content = f.read()
    
    return Response(playlist_content, mimetype='application/vnd.apple.mpegurl')

@app.route('/api/hls/<int:camera_id>/segment_<segment_id>.ts', methods=['GET'])
@token_required
def hls_segment(camera_id, segment_id):
    """提供 HLS 分段"""
    hls_dir = os.path.join(app.config['TEMP_FOLDER'], f'hls_{camera_id}')
    segment_path = os.path.join(hls_dir, f'segment_{segment_id}.ts')
    
    if not os.path.exists(segment_path):
        return jsonify({'error': 'Segment not found'}), 404
    
    return send_from_directory(hls_dir, f'segment_{segment_id}.ts', mimetype='video/mp2t')

@sock.route('/ws/stream/<int:camera_id>')
def ws_stream_camera(ws, camera_id):
    """通过 WebSocket 提供 MPEG-TS 流"""
    try:
        # 验证 token (简化版本，实际应该使用 token_required 装饰器的逻辑)
        token = request.args.get('token')
        if not token:
            app.logger.error("No token provided for WebSocket connection")
            ws.close()
            return
        
        # 记录连接信息
        app.logger.info(f"WebSocket connection established for camera {camera_id}")
        
        # 获取摄像头
        camera = Camera.query.get_or_404(camera_id)
        rtsp_url = camera.url
        
        # 记录 RTSP URL
        app.logger.info(f"Streaming RTSP URL: {rtsp_url}")
        
        cmd = [
            'ffmpeg',
            '-i', rtsp_url,
            '-f', 'mpegts',
            '-codec:v', 'mpeg1video',
            '-s', '640x360',
            '-b:v', '800k',
            '-r', '30',
            '-bf', '0',
            '-an',
            '-f', 'mpegts',
            '-'
        ]
        
        # 启动 FFmpeg 进程
        app.logger.info(f"Starting FFmpeg process for WebSocket stream of camera {camera_id}")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # 记录 FFmpeg 错误输出（用于调试）
        def log_stderr():
            while True:
                line = process.stderr.readline()
                if not line:
                    break
                app.logger.debug(f"FFmpeg: {line.decode().strip()}")
        
        import threading
        stderr_thread = threading.Thread(target=log_stderr)
        stderr_thread.daemon = True
        stderr_thread.start()
        
        try:
            # 发送初始数据
            ws.send(b'\x00' * 8192, binary=True)
            
            # 持续发送视频数据
            while True:
                data = process.stdout.read(4096)
                if not data:
                    app.logger.warning(f"No data received from FFmpeg for camera {camera_id}")
                    break
                ws.send(data, binary=True)
        except Exception as e:
            app.logger.error(f"Error in WebSocket stream: {str(e)}")
        finally:
            process.kill()
            app.logger.info(f"Terminated FFmpeg process for WebSocket stream")
    except Exception as e:
        app.logger.error(f"Error setting up WebSocket stream: {str(e)}")

# 创建错误图像
def create_error_image():
    error_img_path = 'app/static/error.jpg'
    if not os.path.exists('app/static'):
        os.makedirs('app/static')
    if not os.path.exists(error_img_path):
        # 创建一个黑色图像，写入错误文本
        img = np.zeros((360, 640, 3), dtype=np.uint8)
        cv2.putText(img, "Error: Cannot connect to camera", (50, 180), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.imwrite(error_img_path, img)

# 在应用启动时调用
create_error_image()

@app.route('/api/mjpeg/<int:camera_id>', methods=['GET'])
def mjpeg_stream(camera_id):
    """使用 OpenCV 提供 MJPEG 流"""
    try:
        # 获取摄像头
        camera = Camera.query.get_or_404(camera_id)
        rtsp_url = camera.url
        app.logger.info(f"Starting MJPEG stream for camera {camera_id}: {rtsp_url}")
        
        # 设置响应头
        headers = {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
            'Content-Type': 'multipart/x-mixed-replace; boundary=frame'
        }
        
        def generate_frames():
            # 打开视频流
            cap = cv2.VideoCapture(rtsp_url)
            if not cap.isOpened():
                app.logger.error(f"Failed to open video stream: {rtsp_url}")
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + 
                       open('app/static/error.jpg', 'rb').read() + b'\r\n')
                return
            
            app.logger.info(f"Video stream opened successfully: {rtsp_url}")
            
            # 设置帧率限制
            fps_limit = 15  # 限制最大帧率
            frame_time = 1.0 / fps_limit
            last_frame_time = time.time()
            
            try:
                while True:
                    # 控制帧率
                    current_time = time.time()
                    if current_time - last_frame_time < frame_time:
                        time.sleep(0.001)  # 短暂休眠以减少 CPU 使用率
                        continue
                    
                    # 读取一帧
                    ret, frame = cap.read()
                    if not ret:
                        app.logger.warning(f"Failed to read frame from {rtsp_url}")
                        # 尝试重新连接
                        cap.release()
                        time.sleep(1)
                        cap = cv2.VideoCapture(rtsp_url)
                        if not cap.isOpened():
                            app.logger.error(f"Failed to reconnect to video stream: {rtsp_url}")
                            break
                        continue
                    
                    # 调整图像大小以减少带宽
                    frame = cv2.resize(frame, (640, 360))
                    
                    # 编码为 JPEG
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    
                    # 更新上一帧时间
                    last_frame_time = current_time
                    
                    # 生成 multipart 响应
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + 
                           buffer.tobytes() + b'\r\n')
            except Exception as e:
                app.logger.error(f"Error in MJPEG stream: {str(e)}")
            finally:
                cap.release()
                app.logger.info(f"Released video capture for {rtsp_url}")
        
        return Response(stream_with_context(generate_frames()), headers=headers)
    except Exception as e:
        app.logger.error(f"Error setting up MJPEG stream: {str(e)}")
        return jsonify({'error': str(e)}), 500





