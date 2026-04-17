import cv2
import numpy as np

def get_letterbox_params(h, w, target_size=640):
    try:
        if h is None or w is None or h == 0 or w == 0:
            return None, None, None, None, None, None
        # 计算缩放比例
        scale = min(target_size / h, target_size / w)
        new_h, new_w = int(h * scale), int(w * scale)

        print(h, w)
        print(new_h, new_w)

        dh = target_size - new_h
        dw = target_size - new_w
        top = dh // 2
        bottom = dh - top
        left = dw // 2
        right = dw - left
        print(dh, dw)
        print(top, bottom, left, right)
        return new_h, new_w, top, bottom, left, right
    except Exception as e:
        print(f"Error in get_letterbox_params: {e}")
        return None, None, None, None, None, None
    
def preprocess_return_numpy(frame, new_h, new_w, top, bottom, left, right):
    """预处理图像，进行 letterbox 变换"""
    # 确保返回的是 NumPy 数组，而不是 PyTorch 张量
    processed = cv2.resize(frame, (new_w, new_h))
    processed = cv2.copyMakeBorder(processed, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))
    return processed  # 返回 NumPy 数组

def preprocess(frame, new_h, new_w, top, bottom, left, right):
    """
    预处理图像，进行 letterbox 变换。
    注意：为了兼容不同后端（CPU/CUDA/MUSA/NPU），此处仅返回 NumPy 数组。
    各 Runtime 会自动根据模型位置处理设备迁移。
    """
    try:
        # 1. 检查输入有效性
        if frame is None or frame.size == 0:
            return None

        # 1. Resize 并添加灰边 (Letterbox)
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        padded = cv2.copyMakeBorder(
            resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114)
        )
        
        # 返回原生 NumPy 数组，不在此处强行 .cuda()
        # 这样即便没有 CUDA 的环境，任何 Runtime 都能正常使用
        return padded 
    except Exception as e:
        print(f"Error in preprocess: {e}")
        return None

def transform_points_from_frontend_to_backend(points, h_from_frontend, w_from_frontend, h_from_backend, w_from_backend, top, left):
    # 前端：也是原点在左上角；后端：原点也在左上角，但是有灰边
    try:
        scale_x = w_from_backend / w_from_frontend
        scale_y = h_from_backend / h_from_frontend

        # 将点从前端坐标系转换为后端坐标系
        transformed_points = []
        for point in points:
            x = int(point['x'] * scale_x + left)
            y = int(point['y'] * scale_y + top)
            transformed_points.append((x, y))
        return transformed_points
    except Exception as e:
        print(f"Error in transform_points_from_frontend_to_backend: {e}")
        return None