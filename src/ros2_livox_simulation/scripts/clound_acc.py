#!/usr/bin/env python3
import rclpy
from rclpy.node import Node

from sensor_msgs.msg import PointCloud2
import sensor_msgs_py.point_cloud2 as pc2

import numpy as np
import threading
import sys
import os
import math

from geometry_msgs.msg import PoseStamped


class CloudAccumulatorRaw(Node):
    def __init__(self):
        super().__init__('cloud_accumulator_raw')

        # ===== parameters =====
        self.declare_parameter('input_topic', '/cloud_registered')
        self.declare_parameter('output_topic', '/cloud_registered_accum')
        self.declare_parameter('save_path', 'accumulated_map_ds.pcd')
        self.declare_parameter('voxel_size', 0.05)
        self.declare_parameter('z_min', 0.05)         # ⭐ 保留 z > z_min (米)
        self.declare_parameter('enable_keyboard_save', bool(sys.stdin.isatty()))
        self.declare_parameter('enable_ray_clear', True)
        self.declare_parameter('base_pose_topic', '/cube_robot/world_pose')
        self.declare_parameter('sensor_pose_topic', '/livox/world_pose')
        self.declare_parameter('pose_timeout_sec', 0.15)
        self.declare_parameter('sensor_offset_x', 0.0)
        self.declare_parameter('sensor_offset_y', 0.0)
        self.declare_parameter('sensor_offset_z', 0.4)
        self.declare_parameter('sensor_pitch_deg', 30.0)
        self.declare_parameter('ray_clear_step_fraction', 0.5)
        self.declare_parameter('ray_clear_endpoint_margin', 0.75)

        self.input_topic = self.get_parameter('input_topic').value
        self.output_topic = self.get_parameter('output_topic').value
        self.save_path = self.get_parameter('save_path').value
        self.voxel_size = float(self.get_parameter('voxel_size').value)
        self.z_min = float(self.get_parameter('z_min').value)
        self.enable_keyboard_save = bool(self.get_parameter('enable_keyboard_save').value)
        self.enable_ray_clear = bool(self.get_parameter('enable_ray_clear').value)
        self.base_pose_topic = str(self.get_parameter('base_pose_topic').value)
        self.sensor_pose_topic = str(self.get_parameter('sensor_pose_topic').value)
        self.pose_timeout_sec = float(self.get_parameter('pose_timeout_sec').value)
        self.sensor_offset_x = float(self.get_parameter('sensor_offset_x').value)
        self.sensor_offset_y = float(self.get_parameter('sensor_offset_y').value)
        self.sensor_offset_z = float(self.get_parameter('sensor_offset_z').value)
        self.sensor_pitch_deg = float(self.get_parameter('sensor_pitch_deg').value)
        self.ray_clear_step_fraction = max(0.1, float(self.get_parameter('ray_clear_step_fraction').value))
        self.ray_clear_endpoint_margin = max(0.0, float(self.get_parameter('ray_clear_endpoint_margin').value))

        # ===== data =====
        self.points = []          # legacy raw accumulation when voxel_size <= 0
        self.voxel_map = {}       # (ix, iy, iz) -> [sum_x, sum_y, sum_z, count]
        self.latest_base_pose = None   # (stamp_sec, position(np.ndarray), quat(np.ndarray))
        self.latest_sensor_pose = None # (stamp_sec, position(np.ndarray), quat(np.ndarray))
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

        self.base_pose_sub = self.create_subscription(
            PoseStamped,
            self.base_pose_topic,
            self.base_pose_callback,
            10,
        )
        self.sensor_pose_sub = None
        if self.sensor_pose_topic:
            self.sensor_pose_sub = self.create_subscription(
                PoseStamped,
                self.sensor_pose_topic,
                self.sensor_pose_callback,
                10,
            )

        # ===== keyboard thread =====
        if self.enable_keyboard_save:
            self.key_thread = threading.Thread(
                target=self.keyboard_loop,
                daemon=True
            )
            self.key_thread.start()

        info_lines = [
            f'Accumulating cloud from {self.input_topic}',
            f'Filtering: keep z > {self.z_min} m (drop z <= {self.z_min})',
        ]
        if self.voxel_size > 0.0:
            info_lines.append(
                f'Online voxel accumulation is enabled: voxel_size={self.voxel_size} m'
            )
        else:
            info_lines.append('Online voxel accumulation is disabled: publishing raw accumulated cloud')
        if self.enable_ray_clear and self.voxel_size > 0.0:
            info_lines.append(
                f'Ray clearing is enabled: base_pose={self.base_pose_topic}, '
                f'sensor_pose={self.sensor_pose_topic or "<none>"}'
            )
        if self.enable_keyboard_save:
            info_lines.append('Press "s + Enter" in terminal to downsample & save map.')
        self.get_logger().info('\n'.join(info_lines))

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

        pts_np = np.asarray(pts, dtype=np.float32)

        cloud_stamp_sec = self.stamp_to_sec(msg.header.stamp)
        sensor_origin = self.resolve_sensor_origin(cloud_stamp_sec)

        with self.lock:
            if self.voxel_size > 0.0:
                if self.enable_ray_clear and sensor_origin is not None:
                    pts_np = self.select_voxel_representatives(pts_np, sensor_origin)
                    pts_np = self.process_with_ray_clear_locked(pts_np, sensor_origin)
                self.update_voxel_map(pts_np, self.voxel_size)
                total = len(self.voxel_map)
            else:
                self.points.extend(pts)
                total = len(self.points)
            self.frame_count += 1

        if self.frame_count % 10 == 0:
            self.get_logger().info(
                f'Frames={self.frame_count}, total_points≈{total}'
            )

        # republish accumulated cloud
        with self.lock:
            points_to_publish = self.get_accumulated_points_locked()
            cloud_msg = pc2.create_cloud_xyz32(msg.header, points_to_publish.tolist())
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

    @staticmethod
    def stamp_to_sec(stamp) -> float:
        return float(stamp.sec) + 1e-9 * float(stamp.nanosec)

    def base_pose_callback(self, msg: PoseStamped):
        self.latest_base_pose = self.pose_to_tuple(msg)

    def sensor_pose_callback(self, msg: PoseStamped):
        self.latest_sensor_pose = self.pose_to_tuple(msg)

    def pose_to_tuple(self, msg: PoseStamped):
        position = np.array(
            [msg.pose.position.x, msg.pose.position.y, msg.pose.position.z],
            dtype=np.float32,
        )
        quat = np.array(
            [
                msg.pose.orientation.x,
                msg.pose.orientation.y,
                msg.pose.orientation.z,
                msg.pose.orientation.w,
            ],
            dtype=np.float32,
        )
        return (self.stamp_to_sec(msg.header.stamp), position, quat)

    @staticmethod
    def quat_to_rot_matrix(quat: np.ndarray) -> np.ndarray:
        qx, qy, qz, qw = [float(v) for v in quat]
        norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
        if norm <= 1e-9:
            return np.eye(3, dtype=np.float32)
        qx /= norm
        qy /= norm
        qz /= norm
        qw /= norm
        return np.array(
            [
                [1.0 - 2.0 * (qy * qy + qz * qz), 2.0 * (qx * qy - qz * qw), 2.0 * (qx * qz + qy * qw)],
                [2.0 * (qx * qy + qz * qw), 1.0 - 2.0 * (qx * qx + qz * qz), 2.0 * (qy * qz - qx * qw)],
                [2.0 * (qx * qz - qy * qw), 2.0 * (qy * qz + qx * qw), 1.0 - 2.0 * (qx * qx + qy * qy)],
            ],
            dtype=np.float32,
        )

    def resolve_sensor_origin(self, cloud_stamp_sec: float):
        if self.voxel_size <= 0.0 or not self.enable_ray_clear:
            return None

        if self.latest_sensor_pose is not None:
            stamp_sec, position, _ = self.latest_sensor_pose
            if self.pose_timeout_sec <= 0.0 or abs(cloud_stamp_sec - stamp_sec) <= self.pose_timeout_sec:
                return position.copy()

        if self.latest_base_pose is None:
            return None

        stamp_sec, base_position, base_quat = self.latest_base_pose
        if self.pose_timeout_sec > 0.0 and abs(cloud_stamp_sec - stamp_sec) > self.pose_timeout_sec:
            return None

        base_rot = self.quat_to_rot_matrix(base_quat)
        offset = np.array(
            [self.sensor_offset_x, self.sensor_offset_y, self.sensor_offset_z],
            dtype=np.float32,
        )
        return base_position + base_rot @ offset

    def select_voxel_representatives(self, xyz: np.ndarray, sensor_origin: np.ndarray) -> np.ndarray:
        if xyz.size == 0 or self.voxel_size <= 0.0:
            return xyz

        coords = np.floor(xyz / self.voxel_size).astype(np.int64)
        dist_sq = np.sum(np.square(xyz - sensor_origin.reshape(1, 3)), axis=1)
        best_by_key = {}

        for idx, coord in enumerate(coords):
            key = (int(coord[0]), int(coord[1]), int(coord[2]))
            best = best_by_key.get(key)
            if best is None or dist_sq[idx] < best[0]:
                best_by_key[key] = (float(dist_sq[idx]), idx)

        selected_idx = [entry[1] for entry in best_by_key.values()]
        if not selected_idx:
            return np.empty((0, 3), dtype=np.float32)
        return xyz[np.asarray(selected_idx, dtype=np.int32)]

    def process_with_ray_clear_locked(self, xyz: np.ndarray, sensor_origin: np.ndarray) -> np.ndarray:
        if xyz.size == 0 or self.voxel_size <= 0.0:
            return xyz

        distances = np.linalg.norm(xyz - sensor_origin.reshape(1, 3), axis=1)
        order = np.argsort(-distances)
        ordered_points = xyz[order]
        current_scan_points = {}

        for point in ordered_points:
            self.clear_ray_locked(sensor_origin, point, current_scan_points)
            current_scan_points[self.make_voxel_key(point)] = np.asarray(point, dtype=np.float32)

        if not current_scan_points:
            return np.empty((0, 3), dtype=np.float32)
        return np.asarray(list(current_scan_points.values()), dtype=np.float32)

    def clear_ray_locked(self, origin: np.ndarray, endpoint: np.ndarray, current_scan_points=None):
        delta = endpoint - origin
        distance = float(np.linalg.norm(delta))
        if distance <= 1e-6:
            return

        step = max(self.voxel_size * self.ray_clear_step_fraction, 1e-3)
        end_distance = max(0.0, distance - self.voxel_size * self.ray_clear_endpoint_margin)
        if end_distance <= step:
            return

        direction = delta / distance
        sample_count = max(1, int(math.floor(end_distance / step)))
        endpoint_key = self.make_voxel_key(endpoint)
        cleared_keys = set()

        for sample_idx in range(1, sample_count + 1):
            sample_dist = min(end_distance, sample_idx * step)
            sample_point = origin + direction * sample_dist
            voxel_key = self.make_voxel_key(sample_point)
            if voxel_key == endpoint_key or voxel_key in cleared_keys:
                continue
            self.voxel_map.pop(voxel_key, None)
            if current_scan_points is not None:
                current_scan_points.pop(voxel_key, None)
            cleared_keys.add(voxel_key)

    def make_voxel_key(self, xyz: np.ndarray):
        coord = np.floor(np.asarray(xyz, dtype=np.float32) / self.voxel_size).astype(np.int64)
        return (int(coord[0]), int(coord[1]), int(coord[2]))

    # =========================
    # Save logic
    # =========================
    def save_downsampled_map(self):
        with self.lock:
            pts_np = self.get_accumulated_points_locked()
            if pts_np.size == 0:
                self.get_logger().warn('No points to save')
                return

        if self.voxel_size > 0.0:
            pts_ds = pts_np
        else:
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
        if voxel <= 0.0:
            return xyz
        if xyz.size == 0:
            return xyz.reshape(0, 3)

        xyz_min = xyz.min(axis=0)
        coords = np.floor((xyz - xyz_min) / voxel).astype(np.int32)
        _, idx = np.unique(coords, axis=0, return_index=True)
        return xyz[idx]

    def update_voxel_map(self, xyz: np.ndarray, voxel: float):
        if xyz.size == 0:
            return

        coords = np.floor(xyz / voxel).astype(np.int64)
        unique_coords, inverse = np.unique(coords, axis=0, return_inverse=True)

        sums = np.zeros((unique_coords.shape[0], 3), dtype=np.float64)
        counts = np.zeros(unique_coords.shape[0], dtype=np.int64)
        np.add.at(sums, inverse, xyz)
        np.add.at(counts, inverse, 1)

        for coord, sum_xyz, count in zip(unique_coords, sums, counts):
            key = (int(coord[0]), int(coord[1]), int(coord[2]))
            if key in self.voxel_map:
                entry = self.voxel_map[key]
                entry[0] += float(sum_xyz[0])
                entry[1] += float(sum_xyz[1])
                entry[2] += float(sum_xyz[2])
                entry[3] += int(count)
            else:
                self.voxel_map[key] = [
                    float(sum_xyz[0]),
                    float(sum_xyz[1]),
                    float(sum_xyz[2]),
                    int(count),
                ]

    def get_accumulated_points_locked(self) -> np.ndarray:
        if self.voxel_size > 0.0:
            if not self.voxel_map:
                return np.empty((0, 3), dtype=np.float32)
            points = np.empty((len(self.voxel_map), 3), dtype=np.float32)
            for idx, entry in enumerate(self.voxel_map.values()):
                inv_count = 1.0 / float(entry[3])
                points[idx, 0] = float(entry[0]) * inv_count
                points[idx, 1] = float(entry[1]) * inv_count
                points[idx, 2] = float(entry[2]) * inv_count
            return points

        if not self.points:
            return np.empty((0, 3), dtype=np.float32)
        return np.asarray(self.points, dtype=np.float32)

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
