"""Allow unit tests to import app modules when OpenCV is not installed."""
import sys
import types

sys.modules.setdefault('cv2', types.ModuleType('cv2'))
sys.modules.setdefault('numpy', types.ModuleType('numpy'))
