import os
import cv2
import numpy as np
from datetime import datetime
import base64
from flask import current_app
from config import Config

def save_calibration_frame(frame_data, task_id):
    """保存标定图像
    
    Args:
        frame_data: base64 编码的图像数据或二进制图像数据
        task_id: 任务ID
    """
    try:
        # 创建保存目录
        save_dir = os.path.join(Config.IMAGE_FOLDER, 'calibration_images')
        os.makedirs(save_dir, exist_ok=True)
        
        # 生成文件名
        filename = f'calibration_{task_id}.jpg'
        filepath = os.path.join(save_dir, filename)

        current_app.logger.info(f"Saving calibration image to: {filepath}")

        # 将图像数据转换为 numpy 数组
        if isinstance(frame_data, str) and frame_data.startswith('data:image'):
            # 处理 base64 编码的图像
            frame_data = frame_data.split(',')[1]
            img_data = base64.b64decode(frame_data)
            nparr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        elif isinstance(frame_data, bytes):
            # 处理二进制图像数据
            nparr = np.frombuffer(frame_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        else:
            # 直接使用 numpy 数组
            frame = frame_data
            
        # 保存图像
        cv2.imwrite(filepath, frame)
        
        return filename
        
    except Exception as e:
        current_app.logger.error(f"Error saving calibration image: {str(e)}")
        raise

def get_calibration_image(task_id):
    """获取标定图像
    """
    try:
        save_dir = os.path.join(Config.IMAGE_FOLDER, 'calibration_images')
        filename = f'calibration_{task_id}.jpg'
        filepath = os.path.join(save_dir, filename)
        current_app.logger.info(f"Getting calibration image from: {filepath}")
        if not os.path.exists(filepath):
            return None
            
        # 读取图像文件
        with open(filepath, 'rb') as f:
            image_data = f.read()
            
        # 转换为 base64
        image_b64 = base64.b64encode(image_data).decode('utf-8')
        return f'data:image/jpeg;base64,{image_b64}'
        
    except Exception as e:
        current_app.logger.error(f"Error reading calibration image: {str(e)}")
        return None 