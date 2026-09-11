python3 -c "
import torch
import tensorrt as trt
from ultralytics import YOLO
print(f'PyTorch: {torch.__version__}')
print(f'CUDA: {torch.cuda.is_available()}')
print(f'TensorRT: {trt.__version__}')
print('所有组件安装成功！')
"
