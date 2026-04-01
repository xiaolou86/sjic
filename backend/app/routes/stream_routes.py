"""
视频流路由蓝图（HTTP 流、HLS、WebSocket、MJPEG）
"""
from flask import Blueprint, jsonify, request, Response, stream_with_context, current_app
from app.extensions import db, sock, socketio
from app.models import Camera
from app.middleware.auth import token_required
import subprocess
import threading
import time
import os
import cv2
import numpy as np

stream_bp = Blueprint('stream', __name__)


@socketio.on('connect')
def handle_connect():
    """处理连接"""
    from flask import current_app
    current_app.logger.info('Client connected')


@socketio.on('disconnect')
def handle_disconnect():
    """处理断开连接"""
    from flask import current_app
    current_app.logger.info('Client disconnected')


@socketio.on('start_stream')
def handle_start_stream(data):
    """处理开始流请求"""
    from flask import current_app
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
        current_app.logger.error(f"Stream error: {str(e)}")
    finally:
        if cap:
            cap.release()


@stream_bp.route('/api/stream/<int:camera_id>', methods=['GET'])
@token_required
def stream_camera(camera_id):
    """
    将 RTSP 转 HTTP 流 (MPEG-TS)
    ---
    tags:
      - 流媒体 (Streams)
    summary: 获取摄像头的实时网页兼容视频流
    security:
      - APIKeyHeader: []
    parameters:
      - name: camera_id
        in: path
        type: integer
        required: true
        description: 摄像头 ID
    responses:
      200:
        description: 返回 MPEG-TS 视频长连接流
    """
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

            current_app.logger.info(f"Starting FFmpeg process for camera {camera_id}")
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # 记录 FFmpeg 错误输出（用于调试）
            def log_stderr():
                while True:
                    line = process.stderr.readline()
                    if not line:
                        break
                    current_app.logger.debug(f"FFmpeg: {line.decode().strip()}")

            stderr_thread = threading.Thread(target=log_stderr)
            stderr_thread.daemon = True
            stderr_thread.start()

            try:
                # 持续发送视频数据
                while True:
                    data = process.stdout.read(4096)
                    if not data:
                        current_app.logger.warning(f"No data received from FFmpeg for camera {camera_id}")
                        break
                    yield data
            except Exception as e:
                current_app.logger.error(f"Error streaming camera {camera_id}: {str(e)}")
            finally:
                process.kill()
                current_app.logger.info(f"Terminated FFmpeg process for camera {camera_id}")

        return Response(
            stream_with_context(generate()),
            headers=headers
        )
    except Exception as e:
        current_app.logger.error(f"Error setting up stream for camera {camera_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500


@stream_bp.route('/api/hls/<int:camera_id>/playlist.m3u8', methods=['GET'])
@token_required
def hls_playlist(camera_id):
    """
    生成 HLS 播放列表
    ---
    tags:
      - 流媒体 (Streams)
    summary: 返回 HLS M3U8 播放列表
    security:
      - APIKeyHeader: []
    parameters:
      - name: camera_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: 返回 m3u8 文本
    """
    camera = Camera.query.get_or_404(camera_id)

    # 创建 HLS 目录
    hls_dir = os.path.join(current_app.config['TEMP_FOLDER'], f'hls_{camera_id}')
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


@stream_bp.route('/api/hls/<int:camera_id>/segment_<segment_id>.ts', methods=['GET'])
@token_required
def hls_segment(camera_id, segment_id):
    """
    提供 HLS 视频分段
    ---
    tags:
      - 流媒体 (Streams)
    summary: 返回 HLS 具体 ts 分段视频块
    security:
      - APIKeyHeader: []
    parameters:
      - name: camera_id
        in: path
        type: integer
        required: true
      - name: segment_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: TS 二进制流
    """
    from flask import send_from_directory
    hls_dir = os.path.join(current_app.config['TEMP_FOLDER'], f'hls_{camera_id}')
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
            current_app.logger.error("No token provided for WebSocket connection")
            ws.close()
            return

        # 记录连接信息
        current_app.logger.info(f"WebSocket connection established for camera {camera_id}")

        # 获取摄像头
        camera = Camera.query.get_or_404(camera_id)
        rtsp_url = camera.url

        # 记录 RTSP URL
        current_app.logger.info(f"Streaming RTSP URL: {rtsp_url}")

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
        current_app.logger.info(f"Starting FFmpeg process for WebSocket stream of camera {camera_id}")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # 记录 FFmpeg 错误输出（用于调试）
        def log_stderr():
            while True:
                line = process.stderr.readline()
                if not line:
                    break
                current_app.logger.debug(f"FFmpeg: {line.decode().strip()}")

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
                    current_app.logger.warning(f"No data received from FFmpeg for camera {camera_id}")
                    break
                ws.send(data, binary=True)
        except Exception as e:
            current_app.logger.error(f"Error in WebSocket stream: {str(e)}")
        finally:
            process.kill()
            current_app.logger.info(f"Terminated FFmpeg process for WebSocket stream")
    except Exception as e:
        current_app.logger.error(f"Error setting up WebSocket stream: {str(e)}")


@stream_bp.route('/api/mjpeg/<int:camera_id>', methods=['GET'])
def mjpeg_stream(camera_id):
    """
    生成 MJPEG 流
    ---
    tags:
      - 流媒体 (Streams)
    summary: 返回 OpenCV 处理后的 MJPEG 图集流
    parameters:
      - name: camera_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: MJPEG 组合图流
    """
    try:
        # 获取摄像头
        camera = Camera.query.get_or_404(camera_id)
        rtsp_url = camera.url
        current_app.logger.info(f"Starting MJPEG stream for camera {camera_id}: {rtsp_url}")

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
                current_app.logger.error(f"Failed to open video stream: {rtsp_url}")
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' +
                       open('app/static/error.jpg', 'rb').read() + b'\r\n')
                return

            current_app.logger.info(f"Video stream opened successfully: {rtsp_url}")

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
                        current_app.logger.warning(f"Failed to read frame from {rtsp_url}")
                        # 尝试重新连接
                        cap.release()
                        time.sleep(1)
                        cap = cv2.VideoCapture(rtsp_url)
                        if not cap.isOpened():
                            current_app.logger.error(f"Failed to reconnect to video stream: {rtsp_url}")
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
                current_app.logger.error(f"Error in MJPEG stream: {str(e)}")
            finally:
                cap.release()
                current_app.logger.info(f"Released video capture for {rtsp_url}")

        return Response(stream_with_context(generate_frames()), headers=headers)
    except Exception as e:
        current_app.logger.error(f"Error setting up MJPEG stream: {str(e)}")
        return jsonify({'error': str(e)}), 500


def create_error_image():
    """创建错误图像"""
    error_img_path = 'app/static/error.jpg'
    if not os.path.exists('app/static'):
        os.makedirs('app/static')
    if not os.path.exists(error_img_path):
        # 创建一个黑色图像，写入错误文本
        img = np.zeros((360, 640, 3), dtype=np.uint8)
        cv2.putText(img, "Error: Cannot connect to camera", (50, 180),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.imwrite(error_img_path, img)
