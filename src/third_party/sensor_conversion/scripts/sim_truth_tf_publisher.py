#!/usr/bin/python3
"""
仿真真值 TF 发布器
订阅 /nav_odom，发布：
  world -> map
  map -> odom

/nav_odom 已经由 Gazebo 提供 odom -> base_footprint。
base_footprint -> base_link 由 robot_state_publisher 根据 URDF 提供。
这里只补齐 map -> odom，避免把 base_footprint 同时挂到 map 和 odom 下。
"""

import rclpy
import math
from rclpy.node import Node
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from tf2_ros import StaticTransformBroadcaster

class SimTruthTFPublisher(Node):
    def __init__(self):
        super().__init__(
            'sim_truth_tf_publisher',
            automatically_declare_parameters_from_overrides=True,
        )

        self.static_tf_broadcaster = StaticTransformBroadcaster(self)
        self.odom_pub = self.create_publisher(Odometry, '/cube_robot/world_odom', 10)

        self.nav_odom_sub = self.create_subscription(
            Odometry,
            '/nav_odom',
            self.odom_callback,
            10
        )

        self.publish_static_tfs()

        self.get_logger().info('Simulation truth TF publisher started')
        self.get_logger().info('Subscribing to /nav_odom')

    def odom_callback(self, msg):
        """将 Gazebo nav_odom 平面化后转发成供规划使用的 world_odom。"""
        q = msg.pose.pose.orientation
        siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        half_yaw = 0.5 * yaw
        qz = math.sin(half_yaw)
        qw = math.cos(half_yaw)

        odom = Odometry()
        odom.header.stamp = msg.header.stamp
        odom.header.frame_id = 'map'
        odom.child_frame_id = 'base_footprint'
        odom.pose.pose.position.x = msg.pose.pose.position.x
        odom.pose.pose.position.y = msg.pose.pose.position.y
        odom.pose.pose.position.z = 0.0
        odom.pose.pose.orientation.x = 0.0
        odom.pose.pose.orientation.y = 0.0
        odom.pose.pose.orientation.z = qz
        odom.pose.pose.orientation.w = qw
        odom.twist.twist = msg.twist.twist
        self.odom_pub.publish(odom)

    def publish_static_tfs(self):
        """发布静态 TF"""
        # world -> map (身份变换)
        t1 = TransformStamped()
        t1.header.stamp = self.get_clock().now().to_msg()
        t1.header.frame_id = 'world'
        t1.child_frame_id = 'map'
        t1.transform.translation.x = 0.0
        t1.transform.translation.y = 0.0
        t1.transform.translation.z = 0.0
        t1.transform.rotation.x = 0.0
        t1.transform.rotation.y = 0.0
        t1.transform.rotation.z = 0.0
        t1.transform.rotation.w = 1.0

        # map -> odom: in simulation we treat odom as globally aligned truth odom.
        t2 = TransformStamped()
        t2.header.stamp = t1.header.stamp
        t2.header.frame_id = 'map'
        t2.child_frame_id = 'odom'
        t2.transform.translation.x = 0.0
        t2.transform.translation.y = 0.0
        t2.transform.translation.z = 0.0
        t2.transform.rotation.x = 0.0
        t2.transform.rotation.y = 0.0
        t2.transform.rotation.z = 0.0
        t2.transform.rotation.w = 1.0

        self.static_tf_broadcaster.sendTransform([t1, t2])

def main(args=None):
    rclpy.init(args=args)
    node = SimTruthTFPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
