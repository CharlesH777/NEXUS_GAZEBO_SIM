#!/usr/bin/env python3
import rclpy
from rclpy.node import Node

from sensor_msgs.msg import PointCloud2
import sensor_msgs_py.point_cloud2 as pc2

import numpy as np
import threading
import sys
import os


class CloudAccumulatorRaw(Node):
    def __init__(self):
        super().__init__('cloud_accumulator_raw')

        # ===== parameters =====
        self.declare_parameter('input_topic', '/cloud_registered')
        self.declare_parameter('output_topic', '/cloud_registered_accum')
        self.declare_parameter('save_path', 'accumulated_map_ds.pcd')
        self.declare_parameter('voxel_size', 0.05)     # 保存时体素
        self.declare_parameter('z_min', 0.05)         # ⭐ 保留 z > z_min (米)

        self.input_topic = self.get_parameter('input_topic').value
        self.output_topic = self.get_parameter('output_topic').value
        self.save_path = self.get_parameter('save_path').value
        self.voxel_size = float(self.get_parameter('voxel_size').value)
        self.z_min = float(self.get_parameter('z_min').value)

        # ===== data =====
        self.points = []          # list of (x,y,z)
        self.frame_count = 0
        self.lock = threading.Lock()

        # ===== ROS I/O =====
        self.sub = self.create_subscription(
            PointCloud2,
            self.input_topic,
            self.cb_cloud,
            10
        )

        self.pub = self.create_publisher(
            PointCloud2,
            self.output_topic,
            10
        )

        # ===== keyboard thread =====
        self.key_thread = threading.Thread(
            target=self.keyboard_loop,
            daemon=True
        )
        self.key_thread.start()

        self.get_logger().info(
            f'Accumulating cloud from {self.input_topic}\n'
            f'Filtering: keep z > {self.z_min} m (drop z <= {self.z_min})\n'
            f'Press "s + Enter" in terminal to downsample & save map.'
        )

    # =========================
    # Cloud callback
    # =========================
    def cb_cloud(self, msg: PointCloud2):
        # ⭐ 剔除高度 <= z_min 的所有点
        pts = [
            (p['x'], p['y'], p['z'])
            for p in pc2.read_points(
                msg,
                field_names=('x', 'y', 'z'),
                skip_nans=True
            )
            if p['z'] > self.z_min
        ]
        if not pts:
            return

        with self.lock:
            self.points.extend(pts)
            self.frame_count += 1
            total = len(self.points)

        if self.frame_count % 10 == 0:
            self.get_logger().info(
                f'Frames={self.frame_count}, total_points≈{total}'
            )

        # republish accumulated cloud
        with self.lock:
            cloud_msg = pc2.create_cloud_xyz32(
                msg.header,
                self.points
            )
        self.pub.publish(cloud_msg)

    # =========================
    # Keyboard listener
    # =========================
    def keyboard_loop(self):
        while rclpy.ok():
            try:
                cmd = sys.stdin.readline().strip()
            except Exception:
                break

            if cmd.lower() == 's':
                self.get_logger().info('Save command received, processing map...')
                self.save_downsampled_map()

    # =========================
    # Save logic
    # =========================
    def save_downsampled_map(self):
        with self.lock:
            if len(self.points) == 0:
                self.get_logger().warn('No points to save')
                return
            pts_np = np.asarray(self.points, dtype=np.float32)

        pts_ds = self.voxel_downsample(pts_np, self.voxel_size)

        self.get_logger().info(
            f'Downsampled: {pts_np.shape[0]} -> {pts_ds.shape[0]}'
        )

        self.write_pcd_binary(self.save_path, pts_ds)
        self.get_logger().info(f'Saved map to {self.save_path}')

    # =========================
    # Utils
    # =========================
    @staticmethod
    def voxel_downsample(xyz: np.ndarray, voxel: float) -> np.ndarray:
        if xyz.size == 0:
            return xyz.reshape(0, 3)

        xyz_min = xyz.min(axis=0)
        coords = np.floor((xyz - xyz_min) / voxel).astype(np.int32)
        _, idx = np.unique(coords, axis=0, return_index=True)
        return xyz[idx]

    @staticmethod
    def write_pcd_binary(path: str, xyz: np.ndarray):
        os.makedirs(os.path.dirname(path), exist_ok=True) if '/' in path else None
        xyz = np.asarray(xyz, dtype=np.float32)
        n = xyz.shape[0]

        header = (
            "# .PCD v0.7 - Point Cloud Data file format\n"
            "VERSION 0.7\n"
            "FIELDS x y z\n"
            "SIZE 4 4 4\n"
            "TYPE F F F\n"
            "COUNT 1 1 1\n"
            f"WIDTH {n}\n"
            "HEIGHT 1\n"
            "VIEWPOINT 0 0 0 1 0 0 0\n"
            f"POINTS {n}\n"
            "DATA binary\n"
        )

        with open(path, 'wb') as f:
            f.write(header.encode('ascii'))
            f.write(xyz.tobytes(order='C'))


def main():
    rclpy.init()
    node = CloudAccumulatorRaw()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
