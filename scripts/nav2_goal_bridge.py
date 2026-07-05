#!/usr/bin/env python3
"""
Bridge: /goal_pose (PoseStamped) -> NavigateToPose action.

Lets RViz's built-in "2D Goal Pose" tool and the novelty_explorer
drive Nav2 without needing the nav2_rviz_plugins Nav2 Goal button.

Anti-stutter logic:
  - If a new goal arrives while one is executing, only cancel + re-send
    when the new goal is > GOAL_MIN_SHIFT meters from the current goal.
  - Goals within the threshold are silently dropped so the robot keeps
    driving smoothly toward the current target.
  - If no goal is executing, always send immediately.
"""
import math
import threading

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose

# Minimum lateral distance (m) between current and new goal to trigger
# a cancel + re-send. Smaller = more responsive but more stutter.
GOAL_MIN_SHIFT = 3.0


class GoalBridge(Node):
    def __init__(self) -> None:
        super().__init__("nav2_goal_bridge")
        self.action_client = ActionClient(self, NavigateToPose, "navigate_to_pose")
        self.goal_sub = self.create_subscription(
            PoseStamped, "/goal_pose", self.on_goal, 10
        )
        self.current_handle = None
        self.current_goal_xy = None  # (x, y) of the active goal
        self.lock = threading.Lock()
        self.get_logger().info(
            "nav2_goal_bridge: /goal_pose -> navigate_to_pose "
            "(goal_min_shift=%.1fm)" % GOAL_MIN_SHIFT
        )

    def on_goal(self, msg: PoseStamped) -> None:
        if not self.action_client.wait_for_server(timeout_sec=2.0):
            self.get_logger().warn("NavigateToPose action not available yet.")
            return

        new_x = float(msg.pose.position.x)
        new_y = float(msg.pose.position.y)

        with self.lock:
            if self.current_handle is not None and self.current_goal_xy is not None:
                dx = new_x - self.current_goal_xy[0]
                dy = new_y - self.current_goal_xy[1]
                dist = math.hypot(dx, dy)
                if dist < GOAL_MIN_SHIFT:
                    # New goal is too close to current — keep driving,
                    # don't interrupt Nav2.
                    return
                # Goal shifted significantly — cancel current and re-send.
                self.get_logger().info(
                    "Goal shifted %.1fm — cancelling current goal." % dist
                )
                cancel_future = self.current_handle.cancel_goal_async()
                cancel_future.add_done_callback(lambda _: None)
                self.current_handle = None

            self.current_goal_xy = (new_x, new_y)

        goal = NavigateToPose.Goal()
        goal.pose = msg
        goal.behavior_tree = ""

        self.get_logger().info(
            "Sending goal: frame=%s x=%.2f y=%.2f"
            % (msg.header.frame_id, new_x, new_y)
        )
        future = self.action_client.send_goal_async(
            goal, feedback_callback=lambda _fb: None
        )
        future.add_done_callback(self.on_goal_response)

    def on_goal_response(self, future) -> None:
        goal_handle = future.result()
        if goal_handle is None or not goal_handle.accepted:
            self.get_logger().warn("Goal rejected by Nav2.")
            with self.lock:
                self.current_handle = None
                self.current_goal_xy = None
            return
        self.get_logger().info("Goal accepted by Nav2.")
        with self.lock:
            self.current_handle = goal_handle
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.on_result)

    def on_result(self, future) -> None:
        result = future.result()
        status = result.status if result is not None else "unknown"
        self.get_logger().info("Goal finished with status: %s" % status)
        with self.lock:
            self.current_handle = None
            self.current_goal_xy = None


def main() -> None:
    rclpy.init()
    node = GoalBridge()
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
