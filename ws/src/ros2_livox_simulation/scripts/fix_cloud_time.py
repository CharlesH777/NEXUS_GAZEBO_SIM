#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import PointCloud2, PointField
import numpy as np
import time
import math


class FixCloudTime(Node):
    def __init__(self):
        super().__init__('fix_cloud_time')

        # === 旋转参数：绕 Y 轴（度）===
        self.ROT_Y_DEG = 0
        theta = math.radians(self.ROT_Y_DEG)
        self.cos_t = math.cos(theta)
        self.sin_t = math.sin(theta)

        # === 订阅与发布 ===
        self.sub = self.create_subscription(
            PointCloud2, '/livox/lidar_PointCloud2', self.cb, 10)
        self.pub = self.create_publisher(PointCloud2, '/lidar_fixed', 10)

        # === 缓存与定时器 ===
        self.last_msg = None
        self.last_update_time = 0.0
        self.publish_timer = self.create_timer(0.1, self.publish_cached)  # 10Hz
        self.last_warn_time = 0.0

        self.get_logger().info(
            '🧩 FixCloudTime started: rotate Y -30°, timestamp fix + cache @10Hz'
        )

    def cb(self, msg: PointCloud2):
        """收到新点云：旋转 + 时间戳修复 + 缓存"""
        t_start = time.perf_counter()

        msg.header.stamp = self.get_clock().now().to_msg()

        field_names = [f.name for f in msg.fields]

        # === 读取点云 ===
        if field_names == ['x', 'y', 'z']:
            data = np.frombuffer(msg.data, dtype=np.float32).reshape(-1, 3)
            has_intensity = False
        elif 'intensity' in field_names:
            data = np.frombuffer(msg.data, dtype=np.float32).reshape(-1, 4)
            has_intensity = True
        else:
            self.get_logger().warn('⚠️ 未知点云字段结构，跳过')
            return

        # === ⭐ 绕 Y 轴旋转（高效写法）===
        xyz = data[:, :3]
        x = xyz[:, 0]
        y = xyz[:, 1]
        z = xyz[:, 2]

        x_new = self.cos_t * x + self.sin_t * z
        y_new = y
        z_new = -self.sin_t * x + self.cos_t * z

        xyz_rot = np.stack((x_new, y_new, z_new), axis=1)

        # === intensity 处理（功能不变）===
        if has_intensity:
            intensity = data[:, 3:4]
        else:
            intensity = np.ones((xyz_rot.shape[0], 1), dtype=np.float32)

        new_data = np.hstack((xyz_rot, intensity))

        # === 构造新 PointCloud2 ===
        new_msg = PointCloud2()
        new_msg.header = msg.header
        new_msg.height = 1
        new_msg.width = new_data.shape[0]
        new_msg.fields = [
            PointField(name='x', offset=0,  datatype=PointField.FLOAT32, count=1),
            PointField(name='y', offset=4,  datatype=PointField.FLOAT32, count=1),
            PointField(name='z', offset=8,  datatype=PointField.FLOAT32, count=1),
            PointField(name='intensity', offset=12, datatype=PointField.FLOAT32, count=1),
        ]
        new_msg.is_bigendian = False
        new_msg.point_step = 16
        new_msg.row_step = 16 * new_data.shape[0]
        new_msg.data = new_data.tobytes()
        new_msg.is_dense = True

        # === 缓存 ===
        self.last_msg = new_msg
        self.last_update_time = time.time()

        # === 单帧耗时日志 ===
        t_end = time.perf_counter()
        cost_ms = (t_end - t_start) * 1000.0
        self.get_logger().info(f'Frame processed in {cost_ms:.2f} ms')

    def publish_cached(self):
        """定时发布缓存：无新点云则重复上一帧"""
        if self.last_msg is not None:
            msg = self.last_msg
            msg.header.stamp = self.get_clock().now().to_msg()
            self.pub.publish(msg)
        else:
            now = time.time()
            if now - self.last_warn_time > 5.0:
                self.get_logger().warn('⚠️ 当前还没有任何点云缓存，等待输入...')
                self.last_warn_time = now


def main(args=None):
    rclpy.init(args=args)
    node = FixCloudTime()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('🛑 FixCloudTime stopped by user')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
