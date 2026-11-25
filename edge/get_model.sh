#!/usr/bin/env bash
# Download the YOLOX-s detector (Apache-2.0, trained on COCO) into models/.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p models
URL=https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.onnx
[ -f models/yolox_s.onnx ] || curl -fL -o models/yolox_s.onnx "$URL"
echo "models/yolox_s.onnx ready"
