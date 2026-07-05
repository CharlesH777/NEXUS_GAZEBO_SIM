#!/usr/bin/python3

import rclpy
from rclpy.node import Node
from nav_msgs.msg import OccupancyGrid
import time

class TestMapPublisher(Node):
    def __init__(self):
        super().__init__('test_map_publisher')
        self.pub_plane = self.create_publisher(OccupancyGrid, '/plane_OccMap', 10)
        self.pub_global = self.create_publisher(OccupancyGrid, '/globalMap', 10)
        self.timer = self.create_timer(1.0, self.publish_map)
        self.get_logger().info('测试地图发布器启动')

    def publish_map(self):
        # 创建一个简单的测试地图
        msg = OccupancyGrid()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'map'

        # 地图参数
        width = 100
        height = 100
        resolution = 0.3

        msg.info.resolution = resolution
        msg.info.width = width
        msg.info.height = height
        msg.info.origin.position.x = -15.0
        msg.info.origin.position.y = -15.0
        msg.info.origin.position.z = 0.0
        msg.info.origin.orientation.w = 1.0

        # 创建地图数据：中心区域可通行(0)，边缘未知(-1)
        data = []
        for y in range(height):
            for x in range(width):
                # 中心30x30区域可通行
                if 35 < x < 65 and 35 < y < 65:
                    data.append(0)  # 可通行
                # 外围10格未知（需要探索）
                elif 25 < x < 75 and 25 < y < 75:
                    data.append(-1)  # 未知
                else:
                    data.append(100)  # 障碍物

        msg.data = data

        # 发布到两个话题
        self.pub_plane.publish(msg)
        self.pub_global.publish(msg)

        self.get_logger().info(f'发布测试地图: {width}x{height}, 数据点: {len(data)}')

def main():
    rclpy.init()
    node = TestMapPublisher()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass

    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
