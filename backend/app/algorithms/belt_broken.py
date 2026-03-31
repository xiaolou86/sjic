from .base import BaseAlgorithm
from app.models import Algorithm
from flask import current_app
from app.extensions import db
import cv2
import numpy as np

class BeltBroken(BaseAlgorithm):
    """皮带表面故障检测算法"""
    __tablename__ = 'algorithms'
    __mapper_args__ = {
        'polymorphic_identity': 'belt_broken'
    }

    @classmethod
    def register(cls):
        type_name = cls.__mapper_args__['polymorphic_identity']
        print(type_name)
        algorithm = Algorithm.query.filter_by(type=type_name).first()
        print(algorithm)
        if not algorithm:
            algorithm = cls(
                name='皮带表面故障检测',
                type=type_name,
                description='皮带表面故障检测'
            )
            db.session.add(algorithm)
        else:
            # 如果算法已存在，则更新它
            current_app.logger.info(f"Algorithm {type_name} already exists, updating")
            algorithm.name = '皮带表面故障检测'
            algorithm.description = '皮带表面故障检测'
        db.session.commit()

    def process(self, camera, parameters):
        """处理图像"""
        try:
            model = parameters.get('model')
            confidence = parameters.get('confidence', 0.5)
            algorithm_parameters = parameters.get('algorithm_parameters', {})
            on_alert = parameters.get('on_alert')  # 获取告警处理回调
            stop_event = parameters.get('stop_event')
            
            # 从标定数据计算像素到厘米的转换比例
            calibration = algorithm_parameters.get('calibration', {})
            if calibration:
                belt_width = calibration.get('belt_width', 0)      # 真实宽度(cm)
                pixel_width = calibration.get('pixel_width', 0)    # 像素宽度
                frame_size = calibration.get('frame_size', {})     # 前端显示的帧尺寸
                points = calibration.get('points', [])             # 标定点
                
                # 获取实际图像尺寸
                ret, frame = camera.read()
                if ret:
                    actual_width = frame.shape[1]  # 实际图像宽度
                    scale_factor = actual_width / frame_size['width']  # 计算缩放比例
                    
                    # 计算实际的像素距离
                    actual_pixel_width = pixel_width * scale_factor
                    
                    # 计算真实的像素到厘米转换比例
                    pixel_to_cm = belt_width / actual_pixel_width
                else:
                    pixel_to_cm = 0.1  # 默认值
            else:
                pixel_to_cm = 0.1  # 默认值
            
            # 使用计算出的转换比例
            min_area_cm2 = algorithm_parameters.get('min_area_cm2', 100)
            
            while not stop_event.is_set():
                ret, frame = camera.read()
                if not ret:
                    continue

                # 使用YOLO Segment检测异常
                results = model(frame, conf=confidence)[0]
                
                if len(results) > 0:
                    defect_regions = []
                    total_defect_area_px = 0
                    
                    # 处理每个检测到的异常区域
                    for i in range(len(results.boxes)):
                        # 获取检测框
                        box = results.boxes[i]
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        conf = float(box.conf[0])
                        
                        # 获取分割掩码
                        mask = results.masks[i].data[0].cpu().numpy()
                        
                        # 计算异常区域面积（像素）
                        area_px = np.sum(mask)
                        total_defect_area_px += area_px
                        
                        # 记录异常区域信息
                        defect_regions.append({
                            'x': x1,
                            'y': y1,
                            'width': x2 - x1,
                            'height': y2 - y1,
                            'area_px': area_px,
                            'confidence': conf
                        })
                        
                        # 在原图上绘制异常区域
                        colored_mask = np.zeros_like(frame)
                        colored_mask[mask == 1] = [0, 0, 255]  # 红色标记异常区域
                        frame = cv2.addWeighted(frame, 1, colored_mask, 0.5, 0)
                        
                        # 绘制边界框
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    
                    # 计算总异常面积(cm²)
                    total_defect_area_cm2 = total_defect_area_px * (pixel_to_cm ** 2)
                    
                    # 如果异常面积超过阈值，返回结果
                    if total_defect_area_cm2 >= min_area_cm2:
                        # 添加文本说明
                        text = f'Defect Area: {total_defect_area_cm2:.1f} cm²'
                        cv2.putText(
                            frame,
                            text,
                            (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1,
                            (0, 0, 255),
                            2
                        )
                        
                        return {
                            'frame': frame,
                            'defect_area': total_defect_area_cm2,
                            'defect_regions': defect_regions,
                            'alert': True,
                            'alert_type': 'belt_broken',
                            'confidence': max(r['confidence'] for r in defect_regions)
                        }
                
                # 如果没有检测到异常，返回原始帧
                return {
                    'frame': frame,
                    'alert': False
                }

        except Exception as e:
            current_app.logger.error(f"Error in belt broken algorithm: {str(e)}")
            raise
