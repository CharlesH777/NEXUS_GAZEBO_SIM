#!/usr/bin/python3
from __future__ import annotations

import argparse
import sys
import time
from typing import Iterable

import rclpy
from gazebo_msgs.srv import DeleteEntity, GetModelList, SpawnEntity
from rclpy.node import Node


FOLLOWER_PLUGIN_FILENAME = "libruntime_mount_follower_plugin.so"


def build_camera_sdf(
    *,
    camera_name: str,
    topic_prefix: str,
    frame_name: str,
    target_model_name: str,
    target_link_name: str,
    update_rate: float,
    width: int,
    height: int,
    hfov: float,
    near_clip: float,
    far_clip: float,
    min_depth: float,
    max_depth: float,
    visualize: bool,
) -> str:
    visualize_text = "false"
    return f"""<?xml version="1.0"?>
<sdf version="1.7">
  <model name="{camera_name}">
    <static>false</static>
    <allow_auto_disable>false</allow_auto_disable>
    <pose>0 0 0 0 0 0</pose>
    <link name="{camera_name}_link">
      <gravity>false</gravity>
      <self_collide>false</self_collide>
      <kinematic>true</kinematic>
      <inertial>
        <pose>0 0 0 0 0 0</pose>
        <mass>0.02</mass>
        <inertia>
          <ixx>1e-5</ixx>
          <ixy>0.0</ixy>
          <ixz>0.0</ixz>
          <iyy>1e-5</iyy>
          <iyz>0.0</iyz>
          <izz>1e-5</izz>
        </inertia>
      </inertial>
      <sensor name="{camera_name}_sensor" type="depth">
        <always_on>true</always_on>
        <update_rate>{update_rate:.6f}</update_rate>
        <visualize>{visualize_text}</visualize>
        <camera name="{camera_name}">
          <horizontal_fov>{hfov:.9f}</horizontal_fov>
          <image>
            <width>{width}</width>
            <height>{height}</height>
            <format>B8G8R8</format>
          </image>
          <depth_camera/>
          <clip>
            <near>{near_clip:.6f}</near>
            <far>{far_clip:.6f}</far>
          </clip>
        </camera>
        <plugin name="{camera_name}_controller" filename="libgazebo_ros_camera.so">
          <ros>
            <namespace>/</namespace>
            <remapping>{camera_name}/image_raw:=/{topic_prefix}/image_raw</remapping>
            <remapping>{camera_name}/camera_info:=/{topic_prefix}/camera_info</remapping>
            <remapping>{camera_name}/depth/image_raw:=/{topic_prefix}/depth/image_raw</remapping>
            <remapping>{camera_name}/depth/camera_info:=/{topic_prefix}/depth/camera_info</remapping>
            <remapping>{camera_name}/points:=/{topic_prefix}/points</remapping>
          </ros>
          <camera_name>{camera_name}</camera_name>
          <frame_name>{frame_name}</frame_name>
          <min_depth>{min_depth:.6f}</min_depth>
          <max_depth>{max_depth:.6f}</max_depth>
        </plugin>
      </sensor>
    </link>
    <plugin name="{camera_name}_mount_follower" filename="{FOLLOWER_PLUGIN_FILENAME}">
      <target_model_name>{target_model_name}</target_model_name>
      <target_link_name>{target_link_name}</target_link_name>
      <pose_offset>0 0 0 0 0 0</pose_offset>
    </plugin>
  </model>
</sdf>
"""


class RuntimeDepthCamera(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("runtime_depth_camera")
        self.args = args
        self.camera_name = args.camera_name
        self.topic_prefix = args.topic_prefix.strip("/")
        self.target_model_name = args.target_model_name
        self.target_link_name = args.target_link_name
        self.target_scoped_link = f"{self.target_model_name}::{self.target_link_name}"
        self.service_timeout = args.service_timeout

        self.spawn_client = self.create_client(SpawnEntity, "/spawn_entity")
        self.delete_client = self.create_client(DeleteEntity, "/delete_entity")
        self.model_list_client = self.create_client(GetModelList, "/get_model_list")

    def wait_for_services(self, timeout_sec: float) -> None:
        services = (
            (self.spawn_client, "/spawn_entity"),
            (self.delete_client, "/delete_entity"),
            (self.model_list_client, "/get_model_list"),
        )
        missing = []
        deadline = self.get_clock().now().nanoseconds + int(timeout_sec * 1e9)
        while self.get_clock().now().nanoseconds < deadline:
            missing = []
            for client, name in services:
                if not client.wait_for_service(timeout_sec=0.25):
                    missing.append(name)
            if not missing:
                return

        missing_text = ", ".join(missing) if missing else "unknown"
        raise RuntimeError(
            f"Gazebo services not ready within {timeout_sec:.1f}s: {missing_text}. "
            "Please start ./run_sim_local.sh first."
        )

    def call_service(self, client, request, description: str):
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=self.service_timeout)
        if not future.done():
            raise RuntimeError(
                f"Timed out after {self.service_timeout:.1f}s while waiting for {description}."
            )
        if future.exception() is not None:
            raise RuntimeError(f"{description} failed: {future.exception()}")
        result = future.result()
        if result is None:
            raise RuntimeError(f"{description} returned no result.")
        return result

    def expected_topics(self) -> list[str]:
        return [
            f"/{self.topic_prefix}/image_raw",
            f"/{self.topic_prefix}/camera_info",
            f"/{self.topic_prefix}/depth/image_raw",
            f"/{self.topic_prefix}/depth/camera_info",
            f"/{self.topic_prefix}/points",
        ]

    def topic_collisions(self) -> list[str]:
        busy_topics: list[str] = []
        for topic in self.expected_topics():
            if self.get_publishers_info_by_topic(topic):
                busy_topics.append(topic)
        return busy_topics

    def wait_for_topics_to_clear(self, timeout_sec: float) -> list[str]:
        deadline = time.monotonic() + timeout_sec
        collisions = self.topic_collisions()
        while collisions and time.monotonic() < deadline:
            time.sleep(0.2)
            rclpy.spin_once(self, timeout_sec=0.05)
            collisions = self.topic_collisions()
        return collisions

    def get_model_list(self) -> list[str]:
        response = self.call_service(
            self.model_list_client,
            GetModelList.Request(),
            "get Gazebo model list",
        )
        if not response.success:
            raise RuntimeError("GetModelList failed.")
        return list(response.model_names)

    def ensure_target_model_present(self) -> None:
        model_names = self.get_model_list()
        if self.target_model_name not in model_names:
            raise RuntimeError(
                f"Target model [{self.target_model_name}] is not in Gazebo: {model_names}"
            )

    def delete_camera(self, *, quiet_missing: bool = False) -> bool:
        request = DeleteEntity.Request()
        request.name = self.camera_name
        response = self.call_service(
            self.delete_client,
            request,
            f"delete entity {self.camera_name}",
        )
        if response.success:
            self.get_logger().info(f"Deleted runtime depth camera [{self.camera_name}].")
            return True

        if not quiet_missing:
            self.get_logger().warning(
                f"DeleteEntity reported failure for [{self.camera_name}]: {response.status_message}"
            )
        return False

    def spawn_camera(self) -> None:
        request = SpawnEntity.Request()
        request.name = self.camera_name
        request.xml = build_camera_sdf(
            camera_name=self.camera_name,
            topic_prefix=self.topic_prefix,
            frame_name=self.args.frame_name,
            target_model_name=self.target_model_name,
            target_link_name=self.target_link_name,
            update_rate=self.args.update_rate,
            width=self.args.width,
            height=self.args.height,
            hfov=self.args.hfov,
            near_clip=self.args.near_clip,
            far_clip=self.args.far_clip,
            min_depth=self.args.min_depth,
            max_depth=self.args.max_depth,
            visualize=self.args.visualize,
        )
        request.robot_namespace = "/"
        request.initial_pose.position.x = 0.0
        request.initial_pose.position.y = 0.0
        request.initial_pose.position.z = 0.0
        request.initial_pose.orientation.w = 1.0
        request.reference_frame = "world"
        response = self.call_service(
            self.spawn_client,
            request,
            f"spawn runtime depth camera {self.camera_name}",
        )
        if not response.success:
            raise RuntimeError(
                f"SpawnEntity failed for [{self.camera_name}]: {response.status_message}"
            )
        self.get_logger().info(
            f"Spawned runtime depth camera [{self.camera_name}] on [{self.target_scoped_link}]."
        )

    def status_text(self) -> str:
        models = self.get_model_list()
        state = "running" if self.camera_name in models else "stopped"
        return (
            f"runtime_depth_camera={state} "
            f"camera={self.camera_name} "
            f"target={self.target_scoped_link}"
        )

    def start(self) -> None:
        self.ensure_target_model_present()
        self.delete_camera(quiet_missing=True)
        if not self.args.allow_topic_collision:
            collisions = self.wait_for_topics_to_clear(self.args.topic_clear_timeout)
            if collisions:
                collision_text = ", ".join(collisions)
                raise RuntimeError(
                    "Depth camera topics already have publishers: "
                    f"{collision_text}. "
                    "This usually means the startup camera is already enabled."
                )
        self.spawn_camera()


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Spawn or delete a standalone Gazebo depth camera mounted level on the robot."
        )
    )
    parser.add_argument(
        "--camera-name",
        default="livox_tilt_depth",
        help="Gazebo model name for the runtime camera.",
    )
    parser.add_argument(
        "--target-model-name",
        default="cube_robot",
        help="Gazebo model name that owns the camera mount.",
    )
    parser.add_argument(
        "--target-link-name",
        default="depth_camera_mount_link",
        help="Gazebo link name to follow inside the target model.",
    )
    parser.add_argument(
        "--topic-prefix",
        default="livox/depth",
        help="ROS topic prefix for the depth camera output.",
    )
    parser.add_argument(
        "--frame-name",
        default="depth_camera_mount_link",
        help="frame_id used in the published camera messages.",
    )
    parser.add_argument(
        "--update-rate",
        type=float,
        default=60.0,
        help="Sensor publishing rate in Hz.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=848,
        help="Depth camera image width.",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=480,
        help="Depth camera image height.",
    )
    parser.add_argument(
        "--hfov",
        type=float,
        default=1.5184364,
        help="Horizontal field of view in radians.",
    )
    parser.add_argument(
        "--near-clip",
        type=float,
        default=0.10,
        help="Near clipping distance in meters.",
    )
    parser.add_argument(
        "--far-clip",
        type=float,
        default=10.0,
        help="Far clipping distance in meters.",
    )
    parser.add_argument(
        "--min-depth",
        type=float,
        default=0.10,
        help="Minimum depth value in meters.",
    )
    parser.add_argument(
        "--max-depth",
        type=float,
        default=10.0,
        help="Maximum depth value in meters.",
    )
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="Enable Gazebo sensor visualization for the runtime camera.",
    )
    parser.add_argument(
        "--service-wait-timeout",
        type=float,
        default=20.0,
        help="Maximum wait time for Gazebo ROS services.",
    )
    parser.add_argument(
        "--service-timeout",
        type=float,
        default=5.0,
        help="Per-request timeout for Gazebo ROS service calls.",
    )
    parser.add_argument(
        "--topic-clear-timeout",
        type=float,
        default=6.0,
        help="How long to wait for old depth camera publishers to disappear before respawning.",
    )
    parser.add_argument(
        "--allow-topic-collision",
        action="store_true",
        help="Allow spawning even if the target depth topics already have publishers.",
    )
    parser.add_argument(
        "--delete-only",
        action="store_true",
        help="Delete the runtime camera entity and exit.",
    )
    parser.add_argument(
        "--status-only",
        action="store_true",
        help="Print whether the runtime camera model exists in Gazebo and exit.",
    )
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    rclpy.init(args=None)
    node = RuntimeDepthCamera(args)
    exit_code = 0

    try:
        node.wait_for_services(args.service_wait_timeout)
        if args.delete_only:
            node.delete_camera(quiet_missing=True)
        elif args.status_only:
            print(node.status_text())
        else:
            node.start()
            print("topics=" + " ".join(node.expected_topics()))
    except Exception as exc:
        node.get_logger().error(str(exc))
        exit_code = 1
    finally:
        node.destroy_node()
        rclpy.shutdown()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
