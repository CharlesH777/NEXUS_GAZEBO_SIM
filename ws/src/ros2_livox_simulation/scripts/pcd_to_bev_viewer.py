#!/usr/bin/env python3
import argparse
import numpy as np
import cv2

# ================= 基础配置 =================

Z_RANGE = (-3.0, 3.0)

WINDOW_NAME = "BEV (click to set origin)"
TRACKBAR_RES = "Resolution idx"
TRACKBAR_VIEW = "View radius (m)"
TRACKBAR_SCALE = "Display scale"

# 体素 / BEV 分辨率（物理意义）
RESOLUTION_LIST = [0.05, 0.1, 0.2, 0.5, 1.0]

# ================= 全局状态 =================

points_global = None
current_origin = np.zeros(3, dtype=np.float32)

VIEW_RADIUS = 60.0
RES_IDX = 2                 # 默认 0.2m
DISPLAY_SCALE = 3           # 只影响 UI 显示

bev_raw = None              # 原始 BEV（算法）
bev_vis = None              # 放大后的显示图


# ================= ASCII PCD 读取 =================

def load_pcd_xyz_ascii(pcd_path):
    with open(pcd_path, "r", encoding="latin-1") as f:
        lines = f.readlines()

    fields = None
    data_start = 0

    for i, l in enumerate(lines):
        if l.startswith("FIELDS"):
            fields = l.split()[1:]
        if l.strip().startswith("DATA"):
            if "ascii" not in l.lower():
                raise RuntimeError("Only ASCII PCD supported")
            data_start = i + 1
            break

    if fields is None:
        raise RuntimeError("PCD missing FIELDS")

    ix, iy, iz = fields.index("x"), fields.index("y"), fields.index("z")

    pts = []
    for l in lines[data_start:]:
        s = l.strip()
        if not s:
            continue
        p = s.split()
        try:
            pts.append([float(p[ix]), float(p[iy]), float(p[iz])])
        except Exception:
            pass

    return np.asarray(pts, dtype=np.float32)


# ================= BEV 构建 =================

def make_bev(points, view_radius, resolution):
    size = int((2 * view_radius) / resolution)
    bev = np.zeros((size, size), dtype=np.uint8)

    x, y, z = points[:, 0], points[:, 1], points[:, 2]

    mask = (
        (x >= -view_radius) & (x <= view_radius) &
        (y >= -view_radius) & (y <= view_radius) &
        (z >= Z_RANGE[0]) & (z <= Z_RANGE[1])
    )
    x, y = x[mask], y[mask]

    px = ((x + view_radius) / resolution).astype(np.int32)
    py = ((y + view_radius) / resolution).astype(np.int32)

    px = size - px - 1  # 图像坐标系

    valid = (
        (px >= 0) & (px < size) &
        (py >= 0) & (py < size)
    )

    bev[px[valid], py[valid]] = 255
    return bev


def draw_origin(bev):
    img = cv2.cvtColor(bev, cv2.COLOR_GRAY2BGR)
    h, w = bev.shape
    cv2.circle(img, (w // 2, h // 2), 5, (0, 0, 255), -1)
    return img


# ================= UI 显示（只放大，不改数据） =================

def show_bev(img):
    global bev_vis
    if DISPLAY_SCALE == 1:
        bev_vis = img
    else:
        h, w = img.shape[:2]
        bev_vis = cv2.resize(
            img,
            (w * DISPLAY_SCALE, h * DISPLAY_SCALE),
            interpolation=cv2.INTER_NEAREST
        )
    cv2.imshow(WINDOW_NAME, bev_vis)


# ================= 重绘 =================

def redraw():
    global bev_raw
    resolution = RESOLUTION_LIST[RES_IDX]

    shifted = points_global - current_origin
    bev = make_bev(shifted, VIEW_RADIUS, resolution)
    bev_raw = draw_origin(bev)

    show_bev(bev_raw)

    print(
        f"[STATE] res={resolution:.3f}m | "
        f"radius={VIEW_RADIUS:.1f}m | "
        f"grid={bev.shape[0]}x{bev.shape[1]} | "
        f"display x{DISPLAY_SCALE}"
    )


# ================= Trackbars =================

def on_res_trackbar(val):
    global RES_IDX
    RES_IDX = max(0, min(val, len(RESOLUTION_LIST) - 1))
    redraw()


def on_view_trackbar(val):
    global VIEW_RADIUS
    VIEW_RADIUS = max(10, val)
    redraw()


def on_scale_trackbar(val):
    global DISPLAY_SCALE
    DISPLAY_SCALE = max(1, val)
    redraw()


# ================= 鼠标回调 =================

def mouse_callback(event, x, y, flags, param):
    global current_origin

    if event != cv2.EVENT_LBUTTONDOWN:
        return

    resolution = RESOLUTION_LIST[RES_IDX]

    # 注意：点击坐标要除以显示倍率
    px = y // DISPLAY_SCALE
    py = x // DISPLAY_SCALE

    size = bev_raw.shape[0]

    world_x = (size - 1 - px) * resolution - VIEW_RADIUS
    world_y = py * resolution - VIEW_RADIUS

    current_origin = np.array([world_x, world_y, 0.0], dtype=np.float32)

    print("\n[CLICK]")
    print(f"  origin = ({world_x:.3f}, {world_y:.3f}, 0.0)")

    redraw()


# ================= 主程序 =================

def main():
    global points_global

    parser = argparse.ArgumentParser()
    parser.add_argument("pcd", help="ASCII PCD file")
    args = parser.parse_args()

    print("[INFO] Loading PCD...")
    points_global = load_pcd_xyz_ascii(args.pcd)
    print(f"[INFO] Loaded {points_global.shape[0]} points")

    cv2.namedWindow(WINDOW_NAME)

    cv2.createTrackbar(
        TRACKBAR_RES, WINDOW_NAME,
        RES_IDX, len(RESOLUTION_LIST) - 1, on_res_trackbar
    )

    cv2.createTrackbar(
        TRACKBAR_VIEW, WINDOW_NAME,
        int(VIEW_RADIUS), 200, on_view_trackbar
    )

    cv2.createTrackbar(
        TRACKBAR_SCALE, WINDOW_NAME,
        DISPLAY_SCALE, 8, on_scale_trackbar
    )

    cv2.setMouseCallback(WINDOW_NAME, mouse_callback)

    redraw()

    print("\n[USAGE]")
    print("  - Resolution idx : BEV / voxel size (physical)")
    print("  - View radius    : map coverage")
    print("  - Display scale  : UI zoom only")
    print("  - Click          : set world origin")
    print("  - ESC            : exit\n")

    while True:
        if cv2.waitKey(10) == 27:
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
