#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import math
import time
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import Tuple, Dict, Any, List

import numpy as np
import torch
import torch.nn.functional as F

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from rclpy.callback_groups import ReentrantCallbackGroup, MutuallyExclusiveCallbackGroup
from rclpy.executors import MultiThreadedExecutor

from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2
from geometry_msgs.msg import PoseStamped, TransformStamped
from tf2_ros import TransformBroadcaster


MAP_SIM_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRIOR_PCD = MAP_SIM_ROOT / "slam_2026_charles" / "maps" / "accumulated_map_ds.pcd"

# ----------------------------- PCD Loader -----------------------------

def _parse_pcd_header(f) -> Tuple[Dict[str, Any], int]:
    header = {}
    while True:
        line = f.readline()
        if not line:
            raise RuntimeError("PCD header ended unexpectedly")
        s = line.decode("utf-8", errors="ignore").strip()
        if s.startswith("#") or len(s) == 0:
            continue
        key = s.split()[0].upper()
        header[key] = s
        if key == "DATA":
            data_pos = f.tell()
            return header, data_pos


def load_pcd_xyz(path: str) -> np.ndarray:
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    with open(path, "rb") as f:
        header, data_pos = _parse_pcd_header(f)

        def get_list(key: str) -> List[str]:
            if key not in header:
                raise RuntimeError(f"PCD missing {key}")
            return header[key].split()[1:]

        fields = get_list("FIELDS")
        sizes = list(map(int, get_list("SIZE")))
        types = get_list("TYPE")
        counts = list(map(int, get_list("COUNT"))) if "COUNT" in header else [1] * len(fields)

        data_fmt = header["DATA"].split()[1].lower()

        def np_dtype(t: str, size: int):
            if t == "F":
                return {4: np.float32, 8: np.float64}[size]
            if t == "I":
                return {1: np.int8, 2: np.int16, 4: np.int32, 8: np.int64}[size]
            if t == "U":
                return {1: np.uint8, 2: np.uint16, 4: np.uint32, 8: np.uint64}[size]
            raise RuntimeError(f"Unsupported PCD type={t} size={size}")

        for w in ["x", "y", "z"]:
            if w not in fields:
                raise RuntimeError(f"PCD fields missing '{w}', got: {fields}")

        f.seek(data_pos)

        if data_fmt == "ascii":
            txt = f.read().decode("utf-8", errors="ignore").strip().splitlines()
            idx_x, idx_y, idx_z = fields.index("x"), fields.index("y"), fields.index("z")
            pts = []
            for line in txt:
                if not line:
                    continue
                parts = line.split()
                if len(parts) <= max(idx_x, idx_y, idx_z):
                    continue
                pts.append([float(parts[idx_x]), float(parts[idx_y]), float(parts[idx_z])])
            return np.asarray(pts, dtype=np.float32)

        if data_fmt == "binary":
            dtype_fields = []
            for name, sz, ty, ct in zip(fields, sizes, types, counts):
                base = np_dtype(ty, sz)
                if ct == 1:
                    dtype_fields.append((name, base))
                else:
                    dtype_fields.append((name, base, (ct,)))
            dt = np.dtype(dtype_fields)
            raw = f.read()
            arr = np.frombuffer(raw, dtype=dt)
            x = np.asarray(arr["x"], dtype=np.float32).reshape(-1)
            y = np.asarray(arr["y"], dtype=np.float32).reshape(-1)
            z = np.asarray(arr["z"], dtype=np.float32).reshape(-1)
            return np.stack([x, y, z], axis=1).astype(np.float32, copy=False)

        raise RuntimeError(f"Unsupported PCD DATA format: {data_fmt}")


# ----------------------------- Utils -----------------------------

def yaw_to_quat(yaw: float):
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    return 0.0, 0.0, sy, cy


def wrap_pi(a: float) -> float:
    # wrap to [-pi, pi]
    while a > math.pi:
        a -= 2.0 * math.pi
    while a < -math.pi:
        a += 2.0 * math.pi
    return a


def hard_voxel_downsample_np(xyz: np.ndarray, leaf: float) -> np.ndarray:
    if leaf <= 0.0 or xyz.shape[0] == 0:
        return xyz
    q = np.floor(xyz / leaf).astype(np.int32)
    _, idx = np.unique(q, axis=0, return_index=True)
    return xyz[idx]


def crop_points_aabb_np(xyz: np.ndarray,
                        min_x: float, max_x: float,
                        min_y: float, max_y: float,
                        min_z: float, max_z: float) -> np.ndarray:
    if xyz.shape[0] == 0:
        return xyz
    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    keep = (x >= min_x) & (x <= max_x) & (y >= min_y) & (y <= max_y) & (z >= min_z) & (z <= max_z)
    return xyz[keep]


def transform_xy_yaw(points_xyz: torch.Tensor, dx: torch.Tensor, dy: torch.Tensor, yaw: torch.Tensor) -> torch.Tensor:
    c = torch.cos(yaw)
    s = torch.sin(yaw)
    x = points_xyz[:, 0]
    y = points_xyz[:, 1]
    z = points_xyz[:, 2]
    x2 = c * x - s * y + dx
    y2 = s * x + c * y + dy
    return torch.stack([x2, y2, z], dim=1)


# ----------------------------- 2D Soft Voxel (XY) -----------------------------

@dataclass
class Grid2D:
    res: float
    origin_x: float
    origin_y: float
    X: int
    Y: int
    device: torch.device

    @staticmethod
    def from_params(res: float, size_x: float, size_y: float, origin_x: float, origin_y: float, device: torch.device):
        X = int(round(size_x / res))
        Y = int(round(size_y / res))
        if X <= 0 or Y <= 0:
            raise ValueError("Invalid grid size/res")
        return Grid2D(res=res, origin_x=origin_x, origin_y=origin_y, X=X, Y=Y, device=device)


def soft_voxelize_2d(points_xy: torch.Tensor, grid: Grid2D, occ_alpha: float = 2.0) -> torch.Tensor:
    """
    points_xy: (N,2) in world frame
    return: (1,1,Y,X) occupancy in [0,1]
    """
    device = grid.device
    X, Y = grid.X, grid.Y
    if points_xy.numel() == 0:
        return torch.zeros((1, 1, Y, X), device=device, dtype=torch.float32)

    gx = (points_xy[:, 0] - grid.origin_x) / grid.res
    gy = (points_xy[:, 1] - grid.origin_y) / grid.res

    ix0 = torch.floor(gx).to(torch.int64)
    iy0 = torch.floor(gy).to(torch.int64)

    fx = gx - ix0.to(torch.float32)
    fy = gy - iy0.to(torch.float32)

    flat = torch.zeros((Y * X,), device=device, dtype=torch.float32)

    def add(dx: int, dy: int, wx, wy):
        ix = ix0 + dx
        iy = iy0 + dy
        inside = (ix >= 0) & (ix < X) & (iy >= 0) & (iy < Y)
        if inside.any():
            w = (wx * wy)[inside]
            idx = (iy[inside] * X + ix[inside])
            flat.scatter_add_(0, idx, w)

    add(0, 0, (1 - fx), (1 - fy))
    add(1, 0, fx,       (1 - fy))
    add(0, 1, (1 - fx), fy)
    add(1, 1, fx,       fy)

    count = flat.view(Y, X)
    occ = 1.0 - torch.exp(-float(occ_alpha) * torch.clamp(count, min=0.0))
    return occ.unsqueeze(0).unsqueeze(0)


# ----------------------------- ROS2 Node -----------------------------

class Align2DPoseOnline(Node):
    """
    ✅ 正确逻辑：不在线训练网络，只优化 pose (dx,dy,yaw)
    """
    def __init__(self):
        super().__init__("nn_map_align_online")  # 保持你原来的 node 名字

        # ----- params -----
        self.prior_pcd = self.declare_parameter("prior_pcd", str(DEFAULT_PRIOR_PCD)).value
        self.input_topic = self.declare_parameter(
            "input_topic", "/cloud_registered"
        ).value
        self.out_pose_topic = self.declare_parameter("out_pose_topic", "/nn_pose").value

        self.map_frame = self.declare_parameter("map_frame", "world").value
        self.child_frame = self.declare_parameter("child_frame", "base_link").value
        self.publish_tf = self.declare_parameter("publish_tf", True).value

        self.tick_hz = float(self.declare_parameter("tick_hz", 5.0).value)

        # grid (XY)
        self.grid_res = float(self.declare_parameter("grid_res", 0.10).value)
        self.grid_size_x = float(self.declare_parameter("grid_size_x", 30.0).value)
        self.grid_size_y = float(self.declare_parameter("grid_size_y", 30.0).value)
        self.grid_origin_x = float(self.declare_parameter("grid_origin_x", -15.0).value)
        self.grid_origin_y = float(self.declare_parameter("grid_origin_y", -15.0).value)

        # Z crop (只用来过滤点云，不做 3D voxel)
        self.z_min = float(self.declare_parameter("z_min", -1.0).value)
        self.z_max = float(self.declare_parameter("z_max",  1.0).value)

        # scan crop + buffer downsample
        self.enable_scan_crop = bool(self.declare_parameter("enable_scan_crop", True).value)
        self.buffer_voxel = float(self.declare_parameter("buffer_voxel", 0.05).value)
        self.min_points = int(self.declare_parameter("min_points", 2000).value)

        # pose bounds (绝对范围，不累加飞走)
        self.max_pose_xy = float(self.declare_parameter("max_pose_xy", 5.0).value)
        self.max_pose_yaw = float(self.declare_parameter("max_pose_yaw_deg", 45.0).value) * math.pi / 180.0

        # optimizer
        self.pose_lr = float(self.declare_parameter("pose_lr", 0.2).value)
        self.opt_iters = int(self.declare_parameter("opt_iters", 15).value)

        # voxel saturation
        self.occ_alpha = float(self.declare_parameter("occ_alpha", 2.0).value)

        # loss weights
        self.w_l1 = float(self.declare_parameter("w_l1", 1.0).value)
        self.w_iou = float(self.declare_parameter("w_iou", 2.0).value)
        self.w_reg = float(self.declare_parameter("w_reg", 0.05).value)

        # coarse yaw search
        self.enable_yaw_search = bool(self.declare_parameter("enable_yaw_search", True).value)
        self.yaw_search_deg = float(self.declare_parameter("yaw_search_deg", 30.0).value)
        self.yaw_search_bins = int(self.declare_parameter("yaw_search_bins", 9).value)

        dev = self.declare_parameter("device", "cuda").value
        self.device = torch.device("cuda") if (dev == "cuda" and torch.cuda.is_available()) else torch.device("cpu")

        # ----- AABB for cropping in world -----
        self.aabb_min = np.array([self.grid_origin_x,
                                  self.grid_origin_y,
                                  self.z_min], dtype=np.float32)
        self.aabb_max = np.array([self.grid_origin_x + self.grid_size_x,
                                  self.grid_origin_y + self.grid_size_y,
                                  self.z_max], dtype=np.float32)

        # ----- build 2D grid -----
        self.grid2d = Grid2D.from_params(
            res=self.grid_res,
            size_x=self.grid_size_x, size_y=self.grid_size_y,
            origin_x=self.grid_origin_x, origin_y=self.grid_origin_y,
            device=self.device
        )

        # ----- load prior -----
        self.get_logger().info(f"[PRIOR] Loading PCD: {self.prior_pcd}")
        xyz_prior = load_pcd_xyz(self.prior_pcd)
        xyz_prior = xyz_prior[np.isfinite(xyz_prior).all(axis=1)]
        self.get_logger().info(f"[PRIOR] Loaded points: {xyz_prior.shape[0]}")

        if self.enable_scan_crop:
            xyz_prior = crop_points_aabb_np(
                xyz_prior,
                float(self.aabb_min[0]), float(self.aabb_max[0]),
                float(self.aabb_min[1]), float(self.aabb_max[1]),
                float(self.aabb_min[2]), float(self.aabb_max[2]),
            )

        xyz_prior = hard_voxel_downsample_np(xyz_prior, leaf=max(self.grid_res * 0.5, 0.05))

        with torch.no_grad():
            prior_t = torch.from_numpy(xyz_prior).to(self.device, dtype=torch.float32)
            self.prior2d = soft_voxelize_2d(prior_t[:, :2], self.grid2d, occ_alpha=self.occ_alpha)

        nz = int((self.prior2d[0, 0] > 0.01).sum().item())
        self.get_logger().info(f"[PRIOR] prior2d ready. nonzero={nz}")

        # ----- pose state -----
        self.last_x = 0.0
        self.last_y = 0.0
        self.last_yaw = 0.0

        # ----- ROS pub/sub -----
        self.cb_sub = ReentrantCallbackGroup()
        self.cb_timer = MutuallyExclusiveCallbackGroup()  # ✅ timer 不允许重入（关键！）

        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=50
        )
        self.sub = self.create_subscription(PointCloud2, self.input_topic, self.on_cloud, qos,
                                            callback_group=self.cb_sub)
        self.pub_pose = self.create_publisher(PoseStamped, self.out_pose_topic, 10)
        self.tf_br = TransformBroadcaster(self) if self.publish_tf else None

        self._lock = threading.Lock()
        self._buffer_xyz: List[np.ndarray] = []
        self._last_rx_log = 0.0
        self._last_tick_log = 0.0

        # 额外保险：防止任何意外重入
        self._tick_lock = threading.Lock()

        period = 1.0 / max(self.tick_hz, 0.1)
        self.timer = self.create_timer(period, self.on_tick, callback_group=self.cb_timer)

        self.get_logger().info(
            "[INIT] Ready.\n"
            f"  input_topic={self.input_topic}\n"
            f"  tick_hz={self.tick_hz} opt_iters={self.opt_iters} pose_lr={self.pose_lr}\n"
            f"  buffer_voxel={self.buffer_voxel} min_points={self.min_points}\n"
            f"  max_pose_xy={self.max_pose_xy} max_pose_yaw_deg={self.max_pose_yaw*180/math.pi:.1f}\n"
            f"  device={self.device}"
        )

    def on_cloud(self, msg: PointCloud2):
        pts = np.array(
            [[p[0], p[1], p[2]] for p in point_cloud2.read_points(msg, field_names=("x", "y", "z"), skip_nans=True)],
            dtype=np.float32
        )
        raw_n = int(pts.shape[0])
        if raw_n == 0:
            return

        if self.enable_scan_crop:
            pts = crop_points_aabb_np(
                pts,
                float(self.aabb_min[0]), float(self.aabb_max[0]),
                float(self.aabb_min[1]), float(self.aabb_max[1]),
                float(self.aabb_min[2]), float(self.aabb_max[2]),
            )
        after_crop = int(pts.shape[0])
        if after_crop < 50:
            return

        if self.buffer_voxel > 0.0:
            pts = hard_voxel_downsample_np(pts, self.buffer_voxel)
        after_vox = int(pts.shape[0])
        if after_vox < 50:
            return

        with self._lock:
            self._buffer_xyz.append(pts)

        now = time.time()
        if now - self._last_rx_log > 1.0:
            self._last_rx_log = now
            self.get_logger().info(
                f"[RX] raw={raw_n} crop={after_crop} vox={after_vox} buffer_chunks={len(self._buffer_xyz)}"
            )

    @torch.no_grad()
    def coarse_yaw_search(self, live_pts: torch.Tensor, base_x: float, base_y: float, base_yaw: float) -> float:
        if (not self.enable_yaw_search) or self.yaw_search_bins < 2:
            return base_yaw

        ys = torch.linspace(-self.yaw_search_deg, self.yaw_search_deg, self.yaw_search_bins,
                            device=self.device) * math.pi / 180.0

        best_yaw = base_yaw
        best = None

        dx = torch.tensor(base_x, device=self.device)
        dy = torch.tensor(base_y, device=self.device)
        yaw0 = torch.tensor(base_yaw, device=self.device)

        for d in ys:
            yaw = yaw0 + d
            pts_T = transform_xy_yaw(live_pts, dx, dy, yaw)
            live2d = soft_voxelize_2d(pts_T[:, :2], self.grid2d, occ_alpha=self.occ_alpha)

            # weighted L1 diff (focus on occupied area)
            w = torch.clamp(self.prior2d + live2d, 0.0, 1.0)
            l1 = (w * torch.abs(live2d - self.prior2d)).sum() / w.sum().clamp(min=1.0)

            # iou
            inter = (live2d * self.prior2d).sum()
            union = (live2d + self.prior2d - live2d * self.prior2d).sum().clamp(min=1e-6)
            liou = 1.0 - inter / union

            loss = (l1 + 2.0 * liou).item()
            if best is None or loss < best:
                best = loss
                best_yaw = float(yaw.item())

        return best_yaw

    def on_tick(self):
        # ✅ 防重入保险
        if not self._tick_lock.acquire(blocking=False):
            return
        try:
            with self._lock:
                if len(self._buffer_xyz) == 0:
                    return
                xyz = np.concatenate(self._buffer_xyz, axis=0)
                self._buffer_xyz.clear()

            if xyz.shape[0] < self.min_points:
                self.get_logger().warn(f"[ACC] too few points: {xyz.shape[0]} < min_points={self.min_points}")
                return

            live_pts = torch.from_numpy(xyz).to(self.device, dtype=torch.float32)

            prev = torch.tensor([self.last_x, self.last_y, self.last_yaw], device=self.device, dtype=torch.float32)

            # yaw coarse warm start
            with torch.no_grad():
                warm_yaw = self.coarse_yaw_search(
                    live_pts,
                    base_x=self.last_x, base_y=self.last_y, base_yaw=self.last_yaw
                )

            pose = torch.tensor([self.last_x, self.last_y, warm_yaw],
                                device=self.device, dtype=torch.float32, requires_grad=True)

            opt = torch.optim.Adam([pose], lr=self.pose_lr)

            loss_val = 0.0
            for _ in range(self.opt_iters):
                opt.zero_grad(set_to_none=True)

                dx, dy, yaw = pose[0], pose[1], pose[2]
                pts_T = transform_xy_yaw(live_pts, dx, dy, yaw)
                live2d = soft_voxelize_2d(pts_T[:, :2], self.grid2d, occ_alpha=self.occ_alpha)

                # weighted L1 diff（只在“有东西”的区域算）
                w = torch.clamp(self.prior2d + live2d, 0.0, 1.0)
                loss_l1 = (w * torch.abs(live2d - self.prior2d)).sum() / w.sum().clamp(min=1.0)

                # IoU（防止投影跑空）
                inter = (live2d * self.prior2d).sum()
                union = (live2d + self.prior2d - live2d * self.prior2d).sum().clamp(min=1e-6)
                loss_iou = 1.0 - inter / union

                # small step regularizer（锚住，不乱飞）
                loss_reg = ((pose - prev) ** 2).sum()

                loss = self.w_l1 * loss_l1 + self.w_iou * loss_iou + self.w_reg * loss_reg
                loss.backward()
                opt.step()

                # clamp pose to bounds (no_grad)
                with torch.no_grad():
                    pose[0].clamp_(-self.max_pose_xy, self.max_pose_xy)
                    pose[1].clamp_(-self.max_pose_xy, self.max_pose_xy)
                    pose[2].clamp_(-self.max_pose_yaw, self.max_pose_yaw)

                loss_val = float(loss.detach().item())

            # update state
            self.last_x = float(pose[0].detach().item())
            self.last_y = float(pose[1].detach().item())
            self.last_yaw = wrap_pi(float(pose[2].detach().item()))

            self.publish_pose(self.last_x, self.last_y, self.last_yaw)

            now = time.time()
            if now - self._last_tick_log > 0.2:
                self._last_tick_log = now
                self.get_logger().info(
                    f"[TICK] acc_pts={xyz.shape[0]} loss={loss_val:.5f} "
                    f"pred(x,y,yaw)=({self.last_x:.2f},{self.last_y:.2f},{self.last_yaw*180/math.pi:.1f}deg)"
                )
        finally:
            self._tick_lock.release()

    def publish_pose(self, x: float, y: float, yaw: float):
        qx, qy, qz, qw = yaw_to_quat(yaw)

        msg = PoseStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.map_frame
        msg.pose.position.x = float(x)
        msg.pose.position.y = float(y)
        msg.pose.position.z = 0.0
        msg.pose.orientation.x = qx
        msg.pose.orientation.y = qy
        msg.pose.orientation.z = qz
        msg.pose.orientation.w = qw
        self.pub_pose.publish(msg)

        if self.tf_br is not None:
            tfm = TransformStamped()
            tfm.header = msg.header
            tfm.child_frame_id = self.child_frame
            tfm.transform.translation.x = float(x)
            tfm.transform.translation.y = float(y)
            tfm.transform.translation.z = 0.0
            tfm.transform.rotation.x = qx
            tfm.transform.rotation.y = qy
            tfm.transform.rotation.z = qz
            tfm.transform.rotation.w = qw
            self.tf_br.sendTransform(tfm)


def main():
    rclpy.init()
    node = Align2DPoseOnline()

    # ✅ 多线程让订阅不卡，但 timer 本身互斥，不会重入
    ex = MultiThreadedExecutor(num_threads=2)
    ex.add_node(node)
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
