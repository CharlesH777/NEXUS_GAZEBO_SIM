#!/usr/bin/env python3
import os
from pathlib import Path
import sys

from ament_index_python.packages import get_package_prefix, get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    LogInfo,
    OpaqueFunction,
    RegisterEventHandler,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.event_handlers import OnProcessExit, OnProcessStart
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node

THIS_LAUNCH_DIR = Path(__file__).resolve().parent
if str(THIS_LAUNCH_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_LAUNCH_DIR))

from _world_lighting import maybe_prepare_world_with_lighting


def _is_true(value: str) -> bool:
    return (value or "").strip().lower() not in ("0", "false", "")


def _resolve_livox_root(pkg_share: str) -> str:
    world_rel = os.path.join("world", "marsyard2020_map_only.world")
    candidates = [
        os.getenv("LIVOX_SIM_ROOT", ""),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        os.path.abspath(os.path.join(os.getcwd(), "livox_laser_simulation_RO2")),
        os.path.abspath(os.path.join(os.getcwd(), "..", "livox_laser_simulation_RO2")),
        os.path.abspath(os.path.join(pkg_share, "..", "..", "..", "..")),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(os.path.join(candidate, world_rel)):
            return candidate
    raise RuntimeError("Cannot resolve livox_laser_simulation_RO2 root. Set LIVOX_SIM_ROOT env.")


def _resolve_world_path(world_name: str, pkg_share: str, livox_root: str) -> str:
    candidates = []
    if os.path.isabs(world_name):
        candidates.append(world_name)
    candidates.extend(
        [
            os.path.join(pkg_share, "world", world_name),
            os.path.join(livox_root, "world", world_name),
        ]
    )
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    raise RuntimeError(f"Cannot resolve world file: {world_name}")


def _resolve_rviz_config_path(rviz_config: str, pkg_share: str) -> str:
    if not (rviz_config or "").strip():
        candidate = os.path.join(pkg_share, "config", "nexus_gazebo_sim.rviz")
    elif os.path.isabs(rviz_config):
        candidate = rviz_config
    else:
        candidate = os.path.join(pkg_share, "config", rviz_config)

    if os.path.exists(candidate):
        return candidate

    raise RuntimeError(f"Cannot resolve RViz config file: {rviz_config or candidate}")


def _join_existing(paths: list[str]) -> str:
    seen: list[str] = []
    for entry in paths:
        for candidate in str(entry).split(":"):
            if candidate and os.path.exists(candidate) and candidate not in seen:
                seen.append(candidate)
    return ":".join(seen)


def _spawn_entity_cmd() -> list[str]:
    gazebo_ros_prefix = get_package_prefix("gazebo_ros")
    spawn_entity_script = os.path.join(
        gazebo_ros_prefix, "lib", "gazebo_ros", "spawn_entity.py"
    )
    system_python = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else sys.executable
    return [system_python, spawn_entity_script]


def _launch_setup(context):
    pkg_share = get_package_share_directory("ros2_livox_simulation")
    pkg_prefix = get_package_prefix("ros2_livox_simulation")
    livox_root = _resolve_livox_root(pkg_share)

    world_name = LaunchConfiguration("world_name").perform(context)
    world_path = _resolve_world_path(world_name, pkg_share, livox_root)
    lighting_preset = LaunchConfiguration("lighting_preset").perform(context)
    lighting_brightness = float(LaunchConfiguration("lighting_brightness").perform(context))
    solar_time = LaunchConfiguration("solar_time").perform(context)
    solar_lighting_enabled = bool((solar_time or "").strip())
    enable_solar_time_panel = _is_true(
        LaunchConfiguration("enable_solar_time_panel").perform(context)
    )
    launch_gzclient = _is_true(LaunchConfiguration("use_gui").perform(context))
    headless_rendering = _is_true(
        LaunchConfiguration("enable_headless_rendering").perform(context)
    )
    spawn_robot_enabled = _is_true(LaunchConfiguration("spawn_robot").perform(context))
    enable_livox = _is_true(LaunchConfiguration("enable_livox").perform(context))
    enable_depth_camera = _is_true(LaunchConfiguration("enable_depth_camera").perform(context))
    enable_imu = _is_true(LaunchConfiguration("enable_imu").perform(context))
    enable_tf_pub = _is_true(LaunchConfiguration("enable_tf_pub").perform(context))
    enable_ros2_control = _is_true(
        LaunchConfiguration("enable_ros2_control").perform(context)
    )
    enable_rviz = _is_true(LaunchConfiguration("enable_rviz").perform(context))
    rviz_config_path = _resolve_rviz_config_path(
        LaunchConfiguration("rviz_config").perform(context),
        pkg_share,
    )

    world_path = maybe_prepare_world_with_lighting(
        world_path,
        lighting_preset,
        lighting_brightness,
        solar_time if solar_lighting_enabled else None,
    )

    robot_xacro = os.path.abspath(os.path.join(pkg_share, "urdf", "robot_sim.xacro"))
    robot_description = Command(
        [
            "xacro ",
            robot_xacro,
            " enable_livox:=",
            LaunchConfiguration("enable_livox"),
            " enable_depth_camera:=",
            LaunchConfiguration("enable_depth_camera"),
            " enable_imu:=",
            LaunchConfiguration("enable_imu"),
            " enable_ros2_control:=",
            LaunchConfiguration("enable_ros2_control"),
            " enable_tf_pub:=",
            "true" if enable_tf_pub else "false",
            " livox_samples:=",
            LaunchConfiguration("livox_samples"),
            " livox_downsample:=",
            LaunchConfiguration("livox_downsample"),
            " livox_max_range:=",
            LaunchConfiguration("livox_max_range"),
            " depth_camera_name:=",
            os.getenv("MAP_SIM_DEPTH_CAMERA_NAME", "livox_tilt_depth"),
            " depth_camera_topic_prefix:=",
            os.getenv("MAP_SIM_DEPTH_CAMERA_TOPIC_PREFIX", "livox/depth"),
            " depth_camera_frame_name:=",
            os.getenv("MAP_SIM_DEPTH_CAMERA_FRAME_NAME", "depth_camera_mount_link"),
            " depth_camera_update_rate:=",
            os.getenv("MAP_SIM_DEPTH_CAMERA_UPDATE_RATE", "60.0"),
            " depth_camera_width:=",
            os.getenv("MAP_SIM_DEPTH_CAMERA_WIDTH", "848"),
            " depth_camera_height:=",
            os.getenv("MAP_SIM_DEPTH_CAMERA_HEIGHT", "480"),
            " depth_camera_hfov:=",
            os.getenv("MAP_SIM_DEPTH_CAMERA_HFOV", "1.5184364"),
            " depth_camera_near_clip:=",
            os.getenv("MAP_SIM_DEPTH_CAMERA_NEAR_CLIP", "0.10"),
            " depth_camera_far_clip:=",
            os.getenv("MAP_SIM_DEPTH_CAMERA_FAR_CLIP", "10.0"),
            " depth_camera_min_depth:=",
            os.getenv("MAP_SIM_DEPTH_CAMERA_MIN_DEPTH", "0.10"),
            " depth_camera_max_depth:=",
            os.getenv("MAP_SIM_DEPTH_CAMERA_MAX_DEPTH", "10.0"),
            " depth_camera_visualize:=",
            "true"
            if _is_true(os.getenv("MAP_SIM_DEPTH_CAMERA_VISUALIZE", "0"))
            else "false",
        ]
    )
    robot_description_param = {"robot_description": robot_description}

    model_path = _join_existing(
        [
            "/usr/share/gazebo-11/models",
            os.path.join(pkg_share, "models"),
            os.path.join(livox_root, "models"),
            os.getenv("MAP_SIM_EXTRA_MODEL_PATHS", ""),
            os.getenv("GAZEBO_MODEL_PATH", ""),
        ]
    )
    plugin_path = _join_existing(
        [
            os.path.join(pkg_prefix, "lib"),
            os.path.join(livox_root, "install", "ros2_livox_simulation", "lib"),
            os.getenv("GAZEBO_PLUGIN_PATH", ""),
        ]
    )

    gzserver_cmd = ["gzserver"]
    if headless_rendering:
        gzserver_cmd.append("--headless-rendering")
    gzserver_cmd.extend(
        [
            world_path,
            "--verbose",
            "-slibgazebo_ros_init.so",
            "-slibgazebo_ros_factory.so",
        ]
    )

    actions = [
        SetEnvironmentVariable(name="GAZEBO_MODEL_PATH", value=model_path),
        SetEnvironmentVariable(name="GAZEBO_PLUGIN_PATH", value=plugin_path),
        LogInfo(msg=f"[INFO] livox_root={livox_root}"),
        LogInfo(msg=f"[INFO] world={world_path}"),
        LogInfo(msg=f"[INFO] lighting preset={lighting_preset} brightness={lighting_brightness:g}"),
        LogInfo(
            msg=(
                f"[INFO] solar lighting={'enabled' if solar_lighting_enabled else 'disabled'} "
                f"time={solar_time if solar_lighting_enabled else '<none>'}"
            )
        ),
        LogInfo(msg=f"[INFO] headless_rendering={'yes' if headless_rendering else 'no'}"),
        ExecuteProcess(cmd=gzserver_cmd, output="screen"),
    ]

    if launch_gzclient:
        actions.append(ExecuteProcess(cmd=["gzclient"], output="screen"))

    if enable_rviz:
        actions.extend(
            [
                LogInfo(msg=f"[INFO] rviz_config={rviz_config_path}"),
                Node(
                    package="rviz2",
                    executable="rviz2",
                    name="map_sim_rviz",
                    output="screen",
                    arguments=["-d", rviz_config_path],
                    parameters=[{"use_sim_time": True}],
                ),
            ]
        )

    if solar_lighting_enabled and enable_solar_time_panel and launch_gzclient:
        actions.append(
            TimerAction(
                period=6.0,
                actions=[
                    Node(
                        package="ros2_livox_simulation",
                        executable="solar_time_panel",
                        output="screen",
                        arguments=[
                            "--initial-time",
                            solar_time,
                            "--topic",
                            "/map_sim/solar_time_hours",
                        ],
                    )
                ],
            )
        )

    if not spawn_robot_enabled:
        return actions

    spawn_x = LaunchConfiguration("spawn_x").perform(context)
    spawn_y = LaunchConfiguration("spawn_y").perform(context)
    spawn_z = LaunchConfiguration("spawn_z").perform(context)
    controller_manager_timeout = LaunchConfiguration("controller_manager_timeout").perform(
        context
    )
    service_call_timeout = LaunchConfiguration("service_call_timeout").perform(context)

    robot_state_pub = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="screen",
        parameters=[{"use_sim_time": True}, robot_description_param],
    )

    spawn_robot = ExecuteProcess(
        cmd=_spawn_entity_cmd()
        + [
            "-entity",
            "cube_robot",
            "-topic",
            "robot_description",
            "-x",
            spawn_x,
            "-y",
            spawn_y,
            "-z",
            spawn_z,
            "-timeout",
            service_call_timeout,
            "--ros-args",
        ],
        output="screen",
    )

    runtime_nodes: list[Node] = []
    if enable_ros2_control:
        runtime_nodes.extend(
            [
                Node(
                    package="controller_manager",
                    executable="spawner",
                    arguments=[
                        "joint_state_broadcaster",
                        "--controller-manager",
                        "/controller_manager",
                        "--controller-manager-timeout",
                        controller_manager_timeout,
                    ],
                    output="screen",
                ),
                Node(
                    package="controller_manager",
                    executable="spawner",
                    arguments=[
                        "rear_wheel_velocity_controller",
                        "--controller-manager",
                        "/controller_manager",
                        "--controller-manager-timeout",
                        controller_manager_timeout,
                    ],
                    output="screen",
                ),
            ]
        )

    if enable_imu:
        runtime_nodes.append(
            Node(
                package="ros2_livox_simulation",
                executable="fix_imu_time",
                name="fix_imu_time",
                output="screen",
                parameters=[
                    {"use_sim_time": True},
                    {"input_topic": "/livox/imu"},
                    {"output_topic": "/imu_fixed"},
                    {"timestamp_offset_sec": 0.0},
                    {"apply_rotation": False},
                    {"rotation_pitch_deg": 0.0},
                ],
            )
        )

    actions.extend(
        [
            robot_state_pub,
            RegisterEventHandler(
                OnProcessStart(target_action=robot_state_pub, on_start=[spawn_robot])
            ),
        ]
    )

    if runtime_nodes:
        actions.append(
            RegisterEventHandler(OnProcessExit(target_action=spawn_robot, on_exit=runtime_nodes))
        )

    return actions


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "world_name",
                default_value=os.getenv("MAP_SIM_WORLD", "marsyard2020_map_only.world"),
                description="World file name under ros2_livox_simulation/world or an absolute path.",
            ),
            DeclareLaunchArgument(
                "use_gui",
                default_value=os.getenv("MAP_SIM_GZCLIENT", "1"),
                description="Whether to launch gzclient (1/0, true/false).",
            ),
            DeclareLaunchArgument(
                "enable_headless_rendering",
                default_value=os.getenv("MAP_SIM_ENABLE_HEADLESS_RENDERING", "0"),
                description="Whether headless gzserver should request --headless-rendering.",
            ),
            DeclareLaunchArgument(
                "spawn_robot",
                default_value=os.getenv("MAP_SIM_SPAWN_ROBOT", "1"),
                description="Whether to spawn the robot.",
            ),
            DeclareLaunchArgument(
                "lighting_preset",
                default_value=os.getenv("MAP_SIM_LIGHTING_PRESET", "world"),
                description="Lighting preset for Gazebo worlds: world, dim, dark.",
            ),
            DeclareLaunchArgument(
                "lighting_brightness",
                default_value=os.getenv("MAP_SIM_LIGHTING_BRIGHTNESS", "1.0"),
                description="Global multiplier applied on top of the lighting preset.",
            ),
            DeclareLaunchArgument(
                "solar_time",
                default_value=os.getenv("MAP_SIM_SOLAR_TIME", ""),
                description="24-hour solar time at the equator (HH:MM). Empty disables solar lighting override.",
            ),
            DeclareLaunchArgument(
                "enable_solar_time_panel",
                default_value=os.getenv("MAP_SIM_ENABLE_SOLAR_TIME_PANEL", "1"),
                description="Whether to open a realtime solar time control panel when GUI mode is enabled.",
            ),
            DeclareLaunchArgument(
                "enable_livox",
                default_value=os.getenv("MAP_SIM_ENABLE_LIVOX", "1"),
                description="Whether to enable the Livox Gazebo ray sensor plugin in the robot model.",
            ),
            DeclareLaunchArgument(
                "enable_depth_camera",
                default_value=os.getenv("MAP_SIM_ENABLE_DEPTH_CAMERA", "0"),
                description="Whether to enable the Gazebo depth camera mounted on the robot.",
            ),
            DeclareLaunchArgument(
                "enable_imu",
                default_value=os.getenv("MAP_SIM_ENABLE_IMU", "1"),
                description="Whether to enable the IMU sensor interface in the robot model.",
            ),
            DeclareLaunchArgument(
                "enable_ros2_control",
                default_value=os.getenv("MAP_SIM_ENABLE_ROS2_CONTROL", "1"),
                description="Whether to enable and spawn ros2_control controllers.",
            ),
            DeclareLaunchArgument(
                "enable_tf_pub",
                default_value=os.getenv("MAP_SIM_ENABLE_TF_PUB", "0"),
                description="Whether to publish the Gazebo world-pose / odom TF plugin.",
            ),
            DeclareLaunchArgument(
                "enable_rviz",
                default_value=os.getenv("MAP_SIM_ENABLE_RVIZ", "0"),
                description="Whether to launch rviz2 with the bare-sim visualization config.",
            ),
            DeclareLaunchArgument(
                "rviz_config",
                default_value=os.getenv("MAP_SIM_RVIZ_CONFIG", ""),
                description="Absolute path or share/config-relative RViz config file.",
            ),
            DeclareLaunchArgument(
                "livox_samples",
                default_value=os.getenv("MAP_SIM_LIVOX_SAMPLES", "20000"),
            ),
            DeclareLaunchArgument(
                "livox_downsample",
                default_value=os.getenv("MAP_SIM_LIVOX_DOWNSAMPLE", "1"),
            ),
            DeclareLaunchArgument(
                "livox_max_range",
                default_value=os.getenv("MAP_SIM_LIVOX_MAX_RANGE", "70.0"),
            ),
            DeclareLaunchArgument(
                "controller_manager_timeout",
                default_value=os.getenv("MAP_SIM_CONTROLLER_MANAGER_TIMEOUT", "180.0"),
            ),
            DeclareLaunchArgument(
                "service_call_timeout",
                default_value=os.getenv("MAP_SIM_SERVICE_CALL_TIMEOUT", "180.0"),
            ),
            DeclareLaunchArgument("spawn_x", default_value=os.getenv("MAP_SIM_SPAWN_X", "0.0")),
            DeclareLaunchArgument("spawn_y", default_value=os.getenv("MAP_SIM_SPAWN_Y", "0.0")),
            DeclareLaunchArgument("spawn_z", default_value=os.getenv("MAP_SIM_SPAWN_Z", "0.19")),
            OpaqueFunction(function=_launch_setup),
        ]
    )
