from .base import BaseAlgorithm
import cv2
import time
from datetime import datetime
from utils.calc import transform_points_from_frontend_to_backend, get_letterbox_params, preprocess

class ObjectDetectionAlgorithm(BaseAlgorithm):
    """边缘端目标检测算法"""

    def process(self, camera_stream, config_dict, logger, stop_event, on_alert, runtime):
        """处理目标检测视频"""
        try:
            # 解析最新的边侧下发配置
            parameters = config_dict.get('parameters', {})
            model_path = config_dict.get('model_local_path')
            task_name = config_dict.get('task_id', 'unknown_task')
            camera = camera_stream

            logger.debug(f"parameters={parameters}")
            logger.debug(f"model_path={model_path}")
            logger.debug(f"task_name={task_name}")
            logger.debug(f"camera={camera}")
            
            # 通过 Runtime 抽象加载模型（自动适配 Jetson/摩尔/RK3588）
            logger.info(f"Loading model for object_detection via runtime: {model_path}")
            runtime.load(model_path)
            
            confidence = float(parameters.get('confidence', 0.5))
            algorithm_parameters = parameters.get('algorithm_parameters', {})
            alertThreshold = int(parameters.get('alertThreshold', 10))
            last_alert_time = None
            
            # 获取检测区域
            detection_region = algorithm_parameters.get('detection_region')
            points = None
            frame_size = None
            roi_points = None

            if camera is None:
                logger.error(f"error: camera is None")
                return
            
            if detection_region:
                points = detection_region.get('points', [])
                frame_size = detection_region.get('frame_size', {})

            h, w = camera.get(cv2.CAP_PROP_FRAME_HEIGHT), camera.get(cv2.CAP_PROP_FRAME_WIDTH)
            new_h, new_w, top, bottom, left, right = get_letterbox_params(h, w, target_size=640)
            
            if new_h is None:
                logger.error(f"error: get_letterbox_params return None")
                return

            if points:
                logger.debug(f"ROI Points from frontend: {points}, Frame size: {frame_size}")
                roi_points = transform_points_from_frontend_to_backend(points, frame_size['height'], frame_size['width'], new_h, new_w, top, left)
                if roi_points is None:
                    logger.error(f"error: roi_points is None")
                    return
                logger.info(f"Transformed ROI Points for inference: {roi_points}")

            # 设置 FFmpeg 读取容忍度（应对多流 RTMP）
            import os
            os.environ.setdefault('OPENCV_FFMPEG_READ_ATTEMPTS', '65536')
            grab_fail_count = 0
            max_grab_fails = 10  # 连续失败 10 次后触发重连

            while not stop_event.is_set():
                # 策略升级：跳过旧帧，直接抓取缓冲区中【最新】的一帧 (Real-time Frame Grabbing)
                if not camera.grab(): 
                    grab_fail_count += 1
                    if grab_fail_count >= max_grab_fails:
                        rtsp_url = config_dict['camera'].get('rtsp_url')
                        logger.warning(f"Stream grab failed {grab_fail_count} times, reconnecting to {rtsp_url}...")
                        camera.release()
                        time.sleep(3)  # 等待流恢复
                        camera = cv2.VideoCapture(rtsp_url)
                        if not camera.isOpened():
                            logger.error(f"Reconnect failed, will retry in 5s...")
                            time.sleep(5)
                            continue
                        logger.info(f"Stream reconnected successfully.")
                        grab_fail_count = 0
                    else:
                        time.sleep(0.5)
                    continue
                
                grab_fail_count = 0  # 成功 grab，重置计数器

                # 成功 grab 后，只检索当前这帧
                ret, frame = camera.retrieve()
                if not ret:
                    logger.warning("Failed to retrieve frame from camera")
                    continue
                
                logger.debug("Frame retrieved, starting inference...")
                # 预处理（Letterbox）
                processed = preprocess(frame, new_h, new_w, top, bottom, left, right)
                if processed is None:
                    continue

                # 通过 Runtime 推理 - 指定输入类别为人 (classes=[0])
                result = runtime.infer(processed, conf=confidence, classes=[0], imgsz=640)
                
                total_detected = result.count
                if total_detected > 0:
                    logger.debug(f"Detected {total_detected} human(s)")
                else:
                    logger.debug("No human detected in this frame")

                # 检查是否有人员在检测区域内
                is_exception = False
                result_confidence = 0
                
                for box in result.boxes:
                    foot_center = box.foot_center
                    logger.debug(f"Detected Human at foot_center: {foot_center}, Box: [{box.x1}, {box.y1}, {box.x2}, {box.y2}]")

                    if roi_points:
                        # 检查点是否在检测区域内
                        if self.is_point_in_roi(foot_center, roi_points, logger):
                            is_exception = True
                            result_confidence = box.confidence
                            logger.info(f"MATCH! Human detected in ROI! foot_center={foot_center}, Confidence: {result_confidence:.2f}")
                            break
                
                if total_detected > 0 and not is_exception:
                    logger.debug(f"Human(s) detected (counts={total_detected}), but none matched current ROI: {roi_points}")

                # 发起告警
                if is_exception and self.need_alert_again(last_alert_time, alertThreshold, logger):
                    last_alert_time = datetime.now()
                    
                    # 生成检测画面截图
                    # 注意：当前算法的 ROI 与检测框都在 preprocess 后的 letterbox 坐标系中，
                    # 需在 processed 上绘制，避免将 letterbox 坐标误画到原始 frame 造成位置偏移。
                    alert_frame = self.draw_and_get_frame(processed, result)
        
                    # 如果有检测结果，将结果投送给 TaskManager 上传到云端
                    if on_alert:
                        logger.info(f"Triggering alert for {task_name}...")
                        on_alert(
                            alert_type="object_detection", 
                            confidence=result_confidence, 
                            image_frame=alert_frame
                        )
                
                time.sleep(0.01) # 降频节能
                               
        except Exception as e:
            logger.error(f"Error in object detection: {str(e)}", exc_info=True)
            raise
