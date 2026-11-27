"""Re-time real frames of the Mixkit 4385 time-lapse into a ~9-minute 'service'."""
import cv2, sys
src, out = sys.argv[1], sys.argv[2]
cap = cv2.VideoCapture(src)
def frame(t):
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000); ok, f = cap.read(); return f
# (time-lapse second, seconds to hold, what really happens in that frame)
PLAN = [
    (0.0, 60,  "T2, T3 eating; T1 set with glasses; T4 bare"),
    (3.0, 110, "T3's guests gone, a cup left behind"),
    (6.5, 110, "T2's guests gone, dishes left; new guests at T3"),
    (7.5, 50,  "T2 cleared"),
    (9.0, 100, "guests sit at T4 (placemats, menus)"),
    (12.0, 90, "food arrives at T4"),
]
w = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), 5, (1280, 720))
t0 = 0
for t, secs, what in PLAN:
    print(f"{t0:>4}s-{t0 + secs:>4}s  {what}"); f = frame(t)
    for _ in range(secs * 5): w.write(f)
    t0 += secs
w.release()
