#!/usr/bin/env python3

import math

import rclpy
from geometry_msgs.msg import Twist
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import Float64MultiArray


def wrap_angle(angle: float) -> float:
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


def shortest_angular_distance(from_angle: float, to_angle: float) -> float:
    return wrap_angle(to_angle - from_angle)


class CmdVelToSwerve(Node):
    def __init__(self) -> None:
        super().__init__("cmd_vel_to_swerve")

        self.wheel_radius = float(self.declare_parameter("wheel_radius", 0.10).value)
        self.wheelbase = float(self.declare_parameter("wheelbase", 0.35).value)
        self.track_width = float(self.declare_parameter("track_width", 0.40).value)
        self.max_wheel_speed = float(self.declare_parameter("max_wheel_speed", 18.0).value)
        self.max_steering_rate = float(self.declare_parameter("max_steering_rate", 5.5).value)
        self.module_speed_deadband = float(
            self.declare_parameter("module_speed_deadband", 0.10).value
        )
        self.min_alignment_scale = float(
            self.declare_parameter("min_alignment_scale", 0.35).value
        )
        self.command_timeout = float(self.declare_parameter("command_timeout", 0.5).value)
        self.publish_rate = float(self.declare_parameter("publish_rate", 30.0).value)

        half_wheelbase = 0.5 * self.wheelbase
        half_track = 0.5 * self.track_width
        self.module_positions = (
            ("left_front", half_wheelbase, half_track),
            ("right_front", half_wheelbase, -half_track),
            ("left_rear", -half_wheelbase, half_track),
            ("right_rear", -half_wheelbase, -half_track),
        )

        self.latest_cmd = Twist()
        self.last_cmd_stamp = self.get_clock().now()
        self.current_angles = [0.0, 0.0, 0.0, 0.0]

        self.cmd_sub = self.create_subscription(Twist, "/cmd_vel", self.on_cmd_vel, 20)
        self.steering_pub = self.create_publisher(
            Float64MultiArray,
            "/steering_position_controller/commands",
            QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE),
        )
        self.wheel_pub = self.create_publisher(
            Float64MultiArray,
            "/wheel_velocity_controller/commands",
            QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE),
        )
        self.timer = self.create_timer(1.0 / self.publish_rate, self.on_timer)

        self.get_logger().info(
            "swerve bridge ready: wheelbase=%.3f track_width=%.3f wheel_radius=%.3f "
            "max_wheel_speed=%.2f max_steering_rate=%.2f min_alignment_scale=%.2f"
            % (
                self.wheelbase,
                self.track_width,
                self.wheel_radius,
                self.max_wheel_speed,
                self.max_steering_rate,
                self.min_alignment_scale,
            )
        )

    def on_cmd_vel(self, msg: Twist) -> None:
        self.latest_cmd = msg
        self.last_cmd_stamp = self.get_clock().now()

    def build_targets(self, cmd: Twist) -> tuple[list[float], list[float]]:
        target_angles: list[float] = []
        wheel_speeds: list[float] = []

        for _, module_x, module_y in self.module_positions:
            vx = cmd.linear.x - cmd.angular.z * module_y
            vy = cmd.linear.y + cmd.angular.z * module_x
            speed = math.hypot(vx, vy) / self.wheel_radius

            if speed < self.module_speed_deadband:
                target_angles.append(float("nan"))
                wheel_speeds.append(0.0)
                continue

            target_angles.append(math.atan2(vy, vx))
            wheel_speeds.append(speed)

        peak_speed = max((abs(speed) for speed in wheel_speeds), default=0.0)
        if peak_speed > self.max_wheel_speed and peak_speed > 1e-6:
            scale = self.max_wheel_speed / peak_speed
            wheel_speeds = [speed * scale for speed in wheel_speeds]

        return target_angles, wheel_speeds

    def on_timer(self) -> None:
        now = self.get_clock().now()
        age = now - self.last_cmd_stamp

        cmd = Twist()
        if age <= Duration(seconds=self.command_timeout):
            cmd = self.latest_cmd

        target_angles, target_speeds = self.build_targets(cmd)

        max_steer_step = self.max_steering_rate / self.publish_rate
        steering_commands: list[float] = []
        wheel_commands: list[float] = []

        for index, target_angle in enumerate(target_angles):
            current_angle = self.current_angles[index]
            wheel_speed = target_speeds[index]

            if math.isnan(target_angle):
                steering_commands.append(current_angle)
                wheel_commands.append(0.0)
                continue

            desired_angle = target_angle
            delta = shortest_angular_distance(current_angle, desired_angle)

            if abs(delta) > (0.5 * math.pi):
                desired_angle = wrap_angle(desired_angle + math.pi)
                wheel_speed = -wheel_speed
                delta = shortest_angular_distance(current_angle, desired_angle)

            limited_delta = max(-max_steer_step, min(max_steer_step, delta))
            commanded_angle = wrap_angle(current_angle + limited_delta)
            residual_error = abs(shortest_angular_distance(commanded_angle, desired_angle))

            # Reduce drive effort while the pod is still slewing to avoid
            # dragging the wheel sideways during aggressive heading changes.
            alignment_scale = max(
                min(1.0, self.min_alignment_scale),
                max(0.0, math.cos(residual_error)),
            )

            self.current_angles[index] = commanded_angle
            steering_commands.append(commanded_angle)
            wheel_commands.append(wheel_speed * alignment_scale)

        steering_msg = Float64MultiArray()
        steering_msg.data = steering_commands
        self.steering_pub.publish(steering_msg)

        wheel_msg = Float64MultiArray()
        wheel_msg.data = wheel_commands
        self.wheel_pub.publish(wheel_msg)


def main() -> None:
    rclpy.init()
    node = CmdVelToSwerve()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
