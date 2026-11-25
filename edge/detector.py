"""Person + dishware detector: YOLOX-s (Apache-2.0) run with onnxruntime.

Input: one BGR frame (numpy array). Output: list of (kind, score, box) where kind is
"person" or "dish" and box is (x1, y1, x2, y2) in frame pixels. Nothing is stored.

COCO has no "plate" class, so "dish" means cups, glasses, bowls, bottles, cutlery and
common foods. Bare empty plates may be missed: check this on real footage.
"""
import cv2
import numpy as np
import onnxruntime as ort

PERSON = {0}
# bottle, wine glass, cup, fork, knife, spoon, bowl, banana..cake (foods)
DISH = {39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55}


class Detector:
    def __init__(self, model_path, conf=0.35, threads=2):
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        self.session = ort.InferenceSession(model_path, opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.size = self.session.get_inputs()[0].shape[2]  # 640
        self.conf = conf
        self.grids, self.strides = _grids(self.size)

    def detect(self, frame):
        img, ratio = _letterbox(frame, self.size)
        out = self.session.run(None, {self.input_name: img[None]})[0][0]
        return _decode(out, ratio, self.grids, self.strides, self.conf)


def _letterbox(frame, size):
    h, w = frame.shape[:2]
    r = min(size / h, size / w)
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    canvas[: int(h * r), : int(w * r)] = cv2.resize(frame, (int(w * r), int(h * r)))
    return canvas.transpose(2, 0, 1).astype(np.float32), r


def _grids(size):
    grids, strides = [], []
    for s in (8, 16, 32):
        n = size // s
        xv, yv = np.meshgrid(np.arange(n), np.arange(n))
        grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
        strides.append(np.full((n * n, 1), s))
    return np.concatenate(grids), np.concatenate(strides)


def _decode(out, ratio, grids, strides, conf):
    """out: (N, 85) raw YOLOX rows = cx, cy, w, h, objectness, 80 class scores."""
    xy = (out[:, :2] + grids) * strides
    wh = np.exp(out[:, 2:4]) * strides
    scores = out[:, 4:5] * out[:, 5:]
    cls = scores.argmax(1)
    score = scores[np.arange(len(cls)), cls]
    keep = (score >= conf) & np.isin(cls, list(PERSON | DISH))
    xy, wh, cls, score = xy[keep], wh[keep], cls[keep], score[keep]
    boxes = np.concatenate([xy - wh / 2, wh], 1) / ratio  # x, y, w, h in frame pixels
    results = []
    for kind, ids in (("person", PERSON), ("dish", DISH)):
        m = np.isin(cls, list(ids))
        if not m.any():
            continue
        idx = cv2.dnn.NMSBoxes(boxes[m].tolist(), score[m].tolist(), conf, 0.45)
        for i in np.array(idx).flatten():
            x, y, w, h = boxes[m][i]
            results.append((kind, float(score[m][i]), (float(x), float(y), float(x + w), float(y + h))))
    return results
