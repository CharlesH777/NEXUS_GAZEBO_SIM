#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu

class FixImuTime(Node):
    def __init__(self):
        super().__init__('fix_imu_time')
        self.sub = self.create_subscription(Imu, '/livox/imu', self.cb, 10)
        self.pub = self.create_publisher(Imu, '/imu_fixed', 10)
        self.get_logger().info('🧩 FixImuTime started: /livox/imu → /imu_fixed (using system clock)')

    def cb(self, msg):
        now = self.get_clock().now().to_msg()
        msg.header.stamp = now
        self.pub.publish(msg)

def main(args=None):
    rclpy.init(args=args)
    node = FixImuTime()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('🛑 FixImuTime stopped by user')
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
