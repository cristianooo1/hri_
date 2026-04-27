import cv2
import sys
from pathlib import Path


def _add_project_venv_to_path():
    python_dir = f"python{sys.version_info.major}.{sys.version_info.minor}"
    for parent in Path(__file__).resolve().parents:
        site_packages = parent / ".venv" / "lib" / python_dir / "site-packages"
        if site_packages.exists():
            site_packages_text = str(site_packages)
            if site_packages_text not in sys.path:
                sys.path.insert(0, site_packages_text)
            return


_add_project_venv_to_path()

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

# =========================================================
# 1) CONFIGURATION
# =========================================================
TARGET_CLASSES = {"banana", "apple", "orange", "broccoli", "carrot"}

MIN_CONF = 0.60
PRINT_EVERY_N_FRAMES = 15

MIN_STABLE_FRAMES = 3
MAX_MISSING_FRAMES = 6
SMOOTHING_ALPHA = 0.7

DUPLICATE_IOU_THRESHOLD = 0.55
DUPLICATE_CENTER_DISTANCE = 45


# =========================================================
# 2) SMALL HELPER FUNCTIONS
# =========================================================
def smooth_value(old_val, new_val, alpha):
    return int(alpha * old_val + (1 - alpha) * new_val)


def smooth_bbox(old_bbox, new_bbox, alpha):
    return [
        smooth_value(old_bbox[0], new_bbox[0], alpha),
        smooth_value(old_bbox[1], new_bbox[1], alpha),
        smooth_value(old_bbox[2], new_bbox[2], alpha),
        smooth_value(old_bbox[3], new_bbox[3], alpha),
    ]


def center_distance(c1, c2):
    dx = c1[0] - c2[0]
    dy = c1[1] - c2[1]
    return (dx * dx + dy * dy) ** 0.5


def compute_iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    inter_w = max(0, xB - xA)
    inter_h = max(0, yB - yA)
    inter_area = inter_w * inter_h

    areaA = max(0, boxA[2] - boxA[0]) * max(0, boxA[3] - boxA[1])
    areaB = max(0, boxB[2] - boxB[0]) * max(0, boxB[3] - boxB[1])

    union = areaA + areaB - inter_area
    if union == 0:
        return 0.0

    return inter_area / union


def choose_better_track(a, b):
    # Prefer the one that is currently visible
    if a["missing_frames"] != b["missing_frames"]:
        return a if a["missing_frames"] < b["missing_frames"] else b

    # Then prefer the more established one
    if a["seen_frames"] != b["seen_frames"]:
        return a if a["seen_frames"] > b["seen_frames"] else b

    # Finally prefer the one with higher confidence
    return a if a["confidence"] >= b["confidence"] else b


def remove_spatial_duplicates(
    tracks,
    iou_thresh=DUPLICATE_IOU_THRESHOLD,
    dist_thresh=DUPLICATE_CENTER_DISTANCE
):
    """
    Remove false duplicates only when:
    - they have the same class
    - and they overlap too much or are too close

    If there are two real apples separated in the image,
    both should remain.
    """
    kept = []

    for track in tracks:
        duplicate_found = False

        for i, kept_track in enumerate(kept):
            if track["label"] != kept_track["label"]:
                continue

            iou = compute_iou(track["bbox"], kept_track["bbox"])
            dist = center_distance(track["center_px"], kept_track["center_px"])

            if iou > iou_thresh or dist < dist_thresh:
                kept[i] = choose_better_track(track, kept_track)
                duplicate_found = True
                break

        if not duplicate_found:
            kept.append(track)

    return kept


def get_position_tag(center_px, frame_shape):
    """
    Assign a 3x3 position tag based on the object center.
    Possible outputs:
    - top-left, top-center, top-right
    - middle-left, center, middle-right
    - bottom-left, bottom-center, bottom-right
    """
    cx, cy = center_px
    height, width = frame_shape[:2]

    x_th1 = width / 3
    x_th2 = 2 * width / 3

    y_th1 = height / 3
    y_th2 = 2 * height / 3

    # Horizontal region
    if cx < x_th1:
        horizontal = "left"
    elif cx < x_th2:
        horizontal = "center"
    else:
        horizontal = "right"

    # Vertical region
    if cy < y_th1:
        vertical = "top"
    elif cy < y_th2:
        vertical = "middle"
    else:
        vertical = "bottom"

    if vertical == "middle" and horizontal == "center":
        return "center"

    return f"{vertical}-{horizontal}"


def add_position_tags(tracks, frame_shape):
    tagged_tracks = []

    for track in tracks:
        tagged_track = track.copy()
        tagged_track["position_tag"] = get_position_tag(track["center_px"], frame_shape)
        tagged_tracks.append(tagged_track)

    return tagged_tracks

def build_scene_summary(tracks):
    """
    Build a simplified scene summary for downstream modules.
    """
    summary = []

    for track in tracks:
        summary.append({
            "track_id": track["track_id"],
            "label": track["label"],
            "confidence": track["confidence"],
            "position_tag": track["position_tag"],
            "center_px": track["center_px"],
            "bbox": track["bbox"],
        })

    return summary

def build_scene_packet(frame_id, scene_summary):
    """
    Build the full scene packet to be sent to downstream modules.
    """
    return {
        "frame_id": frame_id,
        "num_objects": len(scene_summary),
        "objects": scene_summary
    }

# =========================================================
# 3) LOAD MODEL
# =========================================================
def load_model(model_path="yolo11n.pt"):
    if YOLO is None:
        raise RuntimeError("ultralytics is not installed on the GUI host.")
    return YOLO(model_path)


# =========================================================
# 4) RAW FRAME DETECTION
# =========================================================
def process_frame(model, frame):
    """
    Return raw detections:
    [
        {
            "track_id": 12,
            "label": "apple",
            "confidence": 0.84,
            "bbox": [x1, y1, x2, y2],
            "center_px": [cx, cy]
        }
    ]
    """
    results = model.track(frame, persist=True, verbose=False)
    detections = []

    for r in results:
        boxes = r.boxes
        names = r.names

        for box in boxes:
            cls_id = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            label = names[cls_id]

            if label not in TARGET_CLASSES:
                continue

            if conf < MIN_CONF:
                continue

            if box.id is None:
                continue

            track_id = int(box.id[0].item())

            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)

            detections.append({
                "track_id": track_id,
                "label": label,
                "confidence": round(conf, 3),
                "bbox": [x1, y1, x2, y2],
                "center_px": [cx, cy],
            })

    return detections


# =========================================================
# 5) TRACK STABILIZER
# =========================================================
class TrackStabilizer:
    def __init__(self, min_stable_frames=3, max_missing_frames=6, smoothing_alpha=0.7):
        self.min_stable_frames = min_stable_frames
        self.max_missing_frames = max_missing_frames
        self.smoothing_alpha = smoothing_alpha
        self.tracks = {}

    def update(self, detections):
        # First assume every stored track is missing in this frame
        for track in self.tracks.values():
            track["missing_frames"] += 1

        # Update existing tracks or create new ones
        for det in detections:
            track_id = det["track_id"]

            if track_id not in self.tracks:
                self.tracks[track_id] = {
                    "track_id": track_id,
                    "label": det["label"],
                    "confidence": det["confidence"],
                    "bbox": det["bbox"],
                    "center_px": det["center_px"],
                    "seen_frames": 1,
                    "missing_frames": 0,
                    "status": "candidate",
                }
            else:
                track = self.tracks[track_id]

                track["label"] = det["label"]
                track["confidence"] = det["confidence"]
                track["bbox"] = smooth_bbox(track["bbox"], det["bbox"], self.smoothing_alpha)
                track["center_px"] = [
                    smooth_value(track["center_px"][0], det["center_px"][0], self.smoothing_alpha),
                    smooth_value(track["center_px"][1], det["center_px"][1], self.smoothing_alpha),
                ]
                track["seen_frames"] += 1
                track["missing_frames"] = 0

            # Promote candidate to stable after enough observations
            current_track = self.tracks[track_id]
            if (
                current_track["status"] == "candidate"
                and current_track["seen_frames"] >= self.min_stable_frames
            ):
                current_track["status"] = "stable"

        # Remove tracks that have been missing for too long
        to_delete = []
        for track_id, track in self.tracks.items():
            if track["missing_frames"] > self.max_missing_frames:
                to_delete.append(track_id)

        for track_id in to_delete:
            del self.tracks[track_id]

        # Return only stable tracks
        stable_tracks = []
        for track in self.tracks.values():
            if track["status"] == "stable":
                stable_tracks.append(track.copy())

        return stable_tracks


# =========================================================
# 6) DRAW RESULTS
# =========================================================
def draw_grid(frame):
    """
    Draw a 3x3 guide grid on the image.
    """
    height, width = frame.shape[:2]

    x1 = width // 3
    x2 = 2 * width // 3
    y1 = height // 3
    y2 = 2 * height // 3

    cv2.line(frame, (x1, 0), (x1, height), (255, 0, 0), 1)
    cv2.line(frame, (x2, 0), (x2, height), (255, 0, 0), 1)
    cv2.line(frame, (0, y1), (width, y1), (255, 0, 0), 1)
    cv2.line(frame, (0, y2), (width, y2), (255, 0, 0), 1)

    return frame


def draw_tracks(frame, tracks):
    for track in tracks:
        x1, y1, x2, y2 = track["bbox"]
        cx, cy = track["center_px"]
        position_tag = track.get("position_tag", "unknown")

        text1 = f"T{track['track_id']} {track['label']} {track['confidence']:.2f}"
        text2 = position_tag

        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        cv2.putText(
            frame,
            text1,
            (x1, max(y1 - 28, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 0),
            2
        )

        cv2.putText(
            frame,
            text2,
            (x1, max(y1 - 8, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255),
            2
        )

        cv2.circle(frame, (cx, cy), 4, (0, 0, 255), -1)

    return frame


# =========================================================
# 7) MAIN PROGRAM
# =========================================================
def main():
    model = load_model()
    stabilizer = TrackStabilizer(
        min_stable_frames=MIN_STABLE_FRAMES,
        max_missing_frames=MAX_MISSING_FRAMES,
        smoothing_alpha=SMOOTHING_ALPHA,
    )

    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        raise RuntimeError("Could not open the webcam")

    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Could not read a frame from the camera")
            break

        # A) Raw detections
        raw_detections = process_frame(model, frame)

        # B) Stabilize tracks using track_id
        stable_tracks = stabilizer.update(raw_detections)

        # C) Remove false duplicates of the same class
        stable_tracks = remove_spatial_duplicates(stable_tracks)

        # D) Add position tags
        stable_tracks = add_position_tags(stable_tracks, frame.shape)

        # E) Build simplified scene summary
        scene_summary = build_scene_summary(stable_tracks)

        # F) Draw grid and tracks
        frame = draw_grid(frame)
        frame = draw_tracks(frame, stable_tracks)

        # G) Show counters on the image
        info_text = f"RAW: {len(raw_detections)} | STABLE: {len(stable_tracks)}"
        cv2.putText(
            frame,
            info_text,
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 0),
            2
        )

        # H) Update frame counter
        frame_count += 1

        # I) Build full scene packet
        scene_packet = build_scene_packet(frame_count, scene_summary)

        # J) Print scene packet every N frames
        if frame_count % PRINT_EVERY_N_FRAMES == 0:
            print(scene_packet)

        cv2.imshow("CV Module - Stable Tracks", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
