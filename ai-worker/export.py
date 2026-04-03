import argparse
from ultralytics import YOLO

def main():
    parser = argparse.ArgumentParser(description="YOLO Model Export Tool")
    parser.add_argument("--model", "--weights", type=str, required=True, help="Path to input .pt model file")
    parser.add_argument("--format", type=str, default="onnx", help="Export format (onnx, engine, openvino, etc.)")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size for export")
    
    args = parser.parse_args()

    # Load the specified model
    print(f"Loading model from: {args.model}")
    model = YOLO(args.model)

    # Export the model
    print(f"Exporting model to {args.format} format with imgsz={args.imgsz}...")
    path = model.export(format=args.format, imgsz=args.imgsz)
    print(f"Export complete. File saved at: {path}")

if __name__ == "__main__":
    main()