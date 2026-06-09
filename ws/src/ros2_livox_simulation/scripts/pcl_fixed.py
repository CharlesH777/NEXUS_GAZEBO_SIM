#!/usr/bin/env python3
import struct
import numpy as np
import os

INPUT_PCD  = "accumulated_map_ds.pcd"
OUTPUT_PCD = "accumulated_map_ds.pcd"   # 覆盖写（你现在就是这么用的）

CROP_SIZE  = 25.0
BIN_SIZE   = 0.5
INTENSITY_VALUE = 1.0   # ★ 新增：补全的 intensity 值

def read_pcd_binary_xyz(path):
    header = []
    num_points = None
    sizes = None
    counts = None

    with open(path, "rb") as f:
        while True:
            line = f.readline().decode("ascii").strip()
            header.append(line)

            if line.startswith("POINTS"):
                num_points = int(line.split()[1])
            elif line.startswith("SIZE"):
                sizes = list(map(int, line.split()[1:]))
            elif line.startswith("COUNT"):
                counts = list(map(int, line.split()[1:]))
            elif line.startswith("DATA"):
                if "binary" not in line:
                    raise RuntimeError("Only binary PCD supported")
                break

        if num_points is None or sizes is None or counts is None:
            raise RuntimeError("PCD header missing POINTS/SIZE/COUNT")

        point_step = sum(s * c for s, c in zip(sizes, counts))
        pts = np.zeros((num_points, 3), dtype=np.float32)

        for i in range(num_points):
            raw = f.read(point_step)
            if len(raw) < point_step:
                raise RuntimeError("Unexpected EOF while reading binary PCD data")
            x, y, z = struct.unpack_from("<fff", raw, 0)
            pts[i, 0] = x
            pts[i, 1] = y
            pts[i, 2] = z

    return header, pts

def write_pcd_binary_xyzi(path, header, points, intensity_value):
    new_header = []
    for line in header:
        if line.startswith("FIELDS"):
            new_header.append("FIELDS x y z intensity")
        elif line.startswith("SIZE"):
            new_header.append("SIZE 4 4 4 4")
        elif line.startswith("TYPE"):
            new_header.append("TYPE F F F F")
        elif line.startswith("COUNT"):
            new_header.append("COUNT 1 1 1 1")
        elif line.startswith("WIDTH"):
            new_header.append(f"WIDTH {points.shape[0]}")
        elif line.startswith("POINTS"):
            new_header.append(f"POINTS {points.shape[0]}")
        elif line.startswith("DATA"):
            new_header.append("DATA binary")
        else:
            new_header.append(line)

    with open(path, "wb") as f:
        for line in new_header:
            f.write((line + "\n").encode("ascii"))

        for p in points:
            f.write(struct.pack(
                "<ffff",
                float(p[0]),
                float(p[1]),
                float(p[2]),
                float(intensity_value)
            ))

def find_densest_center_xy(pts, bin_size):
    x = pts[:, 0].astype(np.float64)
    y = pts[:, 1].astype(np.float64)

    xmin, xmax = float(x.min()), float(x.max())
    ymin, ymax = float(y.min()), float(y.max())

    nx = max(1, int(np.ceil((xmax - xmin) / bin_size)))
    ny = max(1, int(np.ceil((ymax - ymin) / bin_size)))

    ix = np.floor((x - xmin) / bin_size).astype(np.int64)
    iy = np.floor((y - ymin) / bin_size).astype(np.int64)

    ix = np.clip(ix, 0, nx - 1)
    iy = np.clip(iy, 0, ny - 1)

    idx = ix + iy * nx
    counts = np.bincount(idx, minlength=nx * ny)

    best = int(np.argmax(counts))
    best_ix = best % nx
    best_iy = best // nx

    cx = xmin + (best_ix + 0.5) * bin_size
    cy = ymin + (best_iy + 0.5) * bin_size

    return float(cx), float(cy), int(counts[best])

def main():
    if not os.path.exists(INPUT_PCD):
        raise FileNotFoundError(INPUT_PCD)

    header, pts = read_pcd_binary_xyz(INPUT_PCD)

    cx, cy, peak = find_densest_center_xy(pts, BIN_SIZE)
    print(f"[INFO] Densest center: cx={cx:.3f}, cy={cy:.3f}, peak={peak}")

    half = CROP_SIZE * 0.5
    mask = (
        (pts[:, 0] >= cx - half) & (pts[:, 0] <= cx + half) &
        (pts[:, 1] >= cy - half) & (pts[:, 1] <= cy + half)
    )
    cropped = pts[mask].copy()

    print(f"[INFO] Original points: {pts.shape[0]}")
    print(f"[INFO] Cropped  points: {cropped.shape[0]}")

    if cropped.shape[0] == 0:
        raise RuntimeError("Crop produced empty cloud")

    cropped[:, 0] -= cx
    cropped[:, 1] -= cy

    write_pcd_binary_xyzi(
        OUTPUT_PCD,
        header,
        cropped,
        INTENSITY_VALUE
    )

    print(f"[INFO] Saved to {OUTPUT_PCD}")
    print("[INFO] intensity field filled with constant value")

if __name__ == "__main__":
    main()
