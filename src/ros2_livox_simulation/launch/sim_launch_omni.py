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

# Repo root = three levels up from launch/ dir (launch -> ros2_livox_simulation -> src -> repo)
_REPO_ROOT = str(THIS_LAUNCH_DIR.parent.parent.parent)


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


def _workspace_root_from_livox_root(livox_root: str) -> str:
    return os.path.abspath(os.path.join(livox_root, "..", ".."))


def _resolve_world_path(world_name: str, pkg_share: str, livox_root: str) -> str:
    workspace_root = _workspace_root_from_livox_root(livox_root)
    external_worlds_root = os.path.join(workspace_root, ".external_worlds")
    candidates = []
    if os.path.isabs(world_name):
        candidates.append(world_name)
    candidates.extend(
        [
            os.path.join(pkg_share, "world", world_name),
            os.path.join(livox_root, "world", world_name),
            os.path.join(external_worlds_root, "ltu_darpa_cave_01", world_name),
            os.path.join(external_worlds_root, "darpa_subt_worlds", world_name),
            os.path.join(external_worlds_root, "darpa_subt_worlds", "worlds", world_name),
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
    workspace_root = _workspace_root_from_livox_root(livox_root)

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
    publish_nav_tf = _is_true(LaunchConfiguration("tf_pub_publish_nav_tf").perform(context))
    enable_pointcloud_pipeline = _is_true(
        LaunchConfiguration("enable_pointcloud_pipeline").perform(context)
    )
    pointcloud_publish_world = enable_pointcloud_pipeline and _is_true(
        LaunchConfiguration("pointcloud_publish_world").perform(context)
    )
    pointcloud_publish_body = enable_pointcloud_pipeline and _is_true(
        LaunchConfiguration("pointcloud_publish_body").perform(context)
    )
    pointcloud_accumulate_world = pointcloud_publish_world and _is_true(
        LaunchConfiguration("pointcloud_accumulate_world").perform(context)
    )
    pointcloud_input_topic = LaunchConfiguration("pointcloud_input_topic").perform(context)
    pointcloud_world_topic = LaunchConfiguration("pointcloud_world_topic").perform(context)
    pointcloud_body_topic = LaunchConfiguration("pointcloud_body_topic").perform(context)
    pointcloud_base_pose_topic = LaunchConfiguration("pointcloud_base_pose_topic").perform(context)
    pointcloud_world_downsample_stride = max(
        1, int(LaunchConfiguration("pointcloud_world_downsample_stride").perform(context))
    )
    pointcloud_save_path = LaunchConfiguration("pointcloud_save_path").perform(context)
    pointcloud_accum_topic = LaunchConfiguration("pointcloud_accum_topic").perform(context)
    pointcloud_accum_voxel = float(
        LaunchConfiguration("pointcloud_accum_voxel").perform(context)
    )
    pointcloud_accum_z_min = float(
        LaunchConfiguration("pointcloud_accum_z_min").perform(context)
    )
    pointcloud_enable_keyboard_save = _is_true(
        LaunchConfiguration("pointcloud_enable_keyboard_save").perform(context)
    )
    pointcloud_sensor_offset_x = float(
        LaunchConfiguration("pointcloud_sensor_offset_x").perform(context)
    )
    pointcloud_sensor_offset_y = float(
        LaunchConfiguration("pointcloud_sensor_offset_y").perform(context)
    )
    pointcloud_sensor_offset_z = float(
        LaunchConfiguration("pointcloud_sensor_offset_z").perform(context)
    )
    pointcloud_sensor_pitch_deg = float(
        LaunchConfiguration("pointcloud_sensor_pitch_deg").perform(context)
    )
    effective_enable_tf_pub = enable_tf_pub or pointcloud_publish_world
    enable_fastlio2 = _is_true(LaunchConfiguration("enable_fastlio2").perform(context))
    fastlio2_bin = LaunchConfiguration("fastlio2_bin").perform(context)
    fastlio2_config = LaunchConfiguration("fastlio2_config").perform(context)
    fastlio2_namespace = LaunchConfiguration("fastlio2_namespace").perform(context)
    fastlio2_tf_topic = LaunchConfiguration("fastlio2_tf_topic").perform(context)
    fastlio2_enable_rviz = enable_fastlio2 and _is_true(
        LaunchConfiguration("fastlio2_enable_rviz").perform(context)
    )
    fastlio2_rviz_config = LaunchConfiguration("fastlio2_rviz_config").perform(context)
    fastlio2_lidar_input_topic = LaunchConfiguration("fastlio2_lidar_input_topic").perform(context)
    fastlio2_lidar_output_topic = LaunchConfiguration("fastlio2_lidar_output_topic").perform(context)
    fastlio2_lidar_rotation_pitch_deg = float(
        LaunchConfiguration("fastlio2_lidar_rotation_pitch_deg").perform(context)
    )
    fastlio2_imu_input_topic = LaunchConfiguration("fastlio2_imu_input_topic").perform(context)
    fastlio2_imu_output_topic = LaunchConfiguration("fastlio2_imu_output_topic").perform(context)
    fastlio2_imu_linear_accel_scale = float(
        LaunchConfiguration("fastlio2_imu_linear_accel_scale").perform(context)
    )
    fastlio2_imu_rotation_pitch_deg = float(
        LaunchConfiguration("fastlio2_imu_rotation_pitch_deg").perform(context)
    )
    enable_rviz = _is_true(LaunchConfiguration("enable_rviz").perform(context))
    rviz_config_path = _resolve_rviz_config_path(
        LaunchConfiguration("rviz_config").perform(context),
        pkg_share,
    )

    software_gl_detected = _is_true(os.getenv("MAP_SIM_SOFTWARE_GL_DETECTED", "0"))
    world_path = maybe_prepare_world_with_lighting(
        world_path,
        lighting_preset,
        lighting_brightness,
        solar_time if solar_lighting_enabled else None,
        disable_shadows=software_gl_detected,
    )

    robot_xacro = os.path.abspath(os.path.join(pkg_share, "urdf", "robot_sim_omni.xacro"))
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
            " enable_tf_pub:=",
            "true" if effective_enable_tf_pub else "false",
            " tf_pub_publish_nav_tf:=",
            LaunchConfiguration("tf_pub_publish_nav_tf"),
            " tf_pub_publish_livox_world_pose:=",
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
            os.path.join(workspace_root, ".fuel_models"),
            os.path.join(
                workspace_root, ".external_worlds", "darpa_subt_worlds", "worlds", "models"
            ),
            os.path.expanduser("~/.gazebo/models"),
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
        LogInfo(
            msg=(
                f"[INFO] pointcloud pipeline={'enabled' if enable_pointcloud_pipeline else 'disabled'} "
                f"world={'on' if pointcloud_publish_world else 'off'} "
                f"body={'on' if pointcloud_publish_body else 'off'} "
                f"accum={'on' if pointcloud_accumulate_world else 'off'}"
            )
        ),
        LogInfo(
            msg=(
                f"[INFO] fastlio2={'enabled' if enable_fastlio2 else 'disabled'} "
                f"bin={fastlio2_bin if enable_fastlio2 else '<none>'}"
            )
        ),
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
    switch_timeout = LaunchConfiguration("switch_timeout").perform(context)

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

    runtime_nodes = [
        Node(
            package="ros2_livox_simulation",
            executable="spawn_omni_controllers",
            output="screen",
            parameters=[
                {"use_sim_time": True},
                {"controller_manager": "/controller_manager"},
                {"controller_manager_timeout": float(controller_manager_timeout)},
                {"service_call_timeout": float(service_call_timeout)},
                {"switch_timeout": float(switch_timeout)},
                {
                    "controllers": [
                        "joint_state_broadcaster",
                        "steering_position_controller",
                        "wheel_velocity_controller",
                    ]
                },
            ],
        ),
        Node(
            package="ros2_livox_simulation",
            executable="cmd_vel_to_swerve",
            name="cmd_vel_to_swerve",
            output="screen",
            respawn=True,
            respawn_delay=2.0,
            parameters=[
                {"use_sim_time": True},
                {
                    "use_swerve_kinematics": os.getenv(
                        "MAP_SIM_OMNI_USE_SWERVE_KINEMATICS", "true"
                    ).strip().lower()
                    not in ("0", "false", "no", "off")
                },
                {"max_wheel_speed": float(os.getenv("MAP_SIM_OMNI_MAX_WHEEL_SPEED", "18.0"))},
                {
                    "max_steering_rate": float(
                        os.getenv("MAP_SIM_OMNI_MAX_STEERING_RATE", "5.5")
                    )
                },
                {
                    "module_speed_deadband": float(
                        os.getenv("MAP_SIM_OMNI_MODULE_SPEED_DEADBAND", "0.10")
                    )
                },
                {
                    "min_alignment_scale": float(
                        os.getenv("MAP_SIM_OMNI_MIN_ALIGNMENT_SCALE", "0.0")
                    )
                },
                {
                    "publish_rate": float(
                        os.getenv("MAP_SIM_OMNI_CMD_PUBLISH_RATE", "50.0")
                    )
                },
            ],
        ),
    ]

    if effective_enable_tf_pub and not publish_nav_tf:
        runtime_nodes.append(
            Node(
                package="nexus_teleop",
                        executable="pose_to_tf_bridge",
                name="pose_to_tf_bridge",
                output="screen",
                parameters=[
                    {"use_sim_time": True},
                    {"pose_topic": "/cube_robot/world_pose"},
                    {"parent_frame": "world"},
                    {"child_frame": "base_footprint"},
                    {"offset_x": 0.0},
                    {"offset_y": 0.0},
                    {"offset_z": -0.13},
                ],
            )
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

    if enable_pointcloud_pipeline:
        runtime_nodes.append(
            Node(
                package="ros2_livox_simulation",
                executable="lidar_to_world",
                name="lidar_to_world",
                output="screen",
                parameters=[
                    {"use_sim_time": True},
                    {"input_topic": pointcloud_input_topic},
                    {"base_pose_topic": pointcloud_base_pose_topic},
                    {"world_topic": pointcloud_world_topic if pointcloud_publish_world else ""},
                    {"body_topic": pointcloud_body_topic if pointcloud_publish_body else ""},
                    {"body_frame_id": "base_link"},
                    {"world_frame_id": "world"},
                    {"use_dynamic_sensor_pose": False},
                    {"sensor_offset_x": pointcloud_sensor_offset_x},
                    {"sensor_offset_y": pointcloud_sensor_offset_y},
                    {"sensor_offset_z": pointcloud_sensor_offset_z},
                    {"sensor_pitch_deg": pointcloud_sensor_pitch_deg},
                    {"world_downsample_stride": pointcloud_world_downsample_stride},
                ],
            )
        )

        if pointcloud_accumulate_world:
            runtime_nodes.append(
                Node(
                    package="ros2_livox_simulation",
                    executable="cloud_accumulator",
                    name="cloud_accumulator",
                    output="screen",
                    parameters=[
                        {"use_sim_time": True},
                        {"input_topic": pointcloud_world_topic},
                        {"output_topic": pointcloud_accum_topic},
                        {"save_path": pointcloud_save_path},
                        {"voxel_size": pointcloud_accum_voxel},
                        {"z_min": pointcloud_accum_z_min},
                        {"enable_keyboard_save": pointcloud_enable_keyboard_save},
                        {"enable_ray_clear": True},
                        {"base_pose_topic": pointcloud_base_pose_topic},
                        {"sensor_offset_x": pointcloud_sensor_offset_x},
                        {"sensor_offset_y": pointcloud_sensor_offset_y},
                        {"sensor_offset_z": pointcloud_sensor_offset_z},
                        {"sensor_pitch_deg": pointcloud_sensor_pitch_deg},
                    ],
                )
            )

    if enable_fastlio2:
        if os.path.exists(fastlio2_bin) and os.path.exists(fastlio2_config):
            runtime_nodes.append(
                Node(
                    package="nexus_fastlio",
                    executable="fastlio_lidar_adapter",
                    name="fastlio_lidar_adapter",
                    output="screen",
                    parameters=[
                        {"use_sim_time": True},
                        {"input_topic": fastlio2_lidar_input_topic},
                        {"output_topic": fastlio2_lidar_output_topic},
                        {"rotation_pitch_deg": fastlio2_lidar_rotation_pitch_deg},
                        {"target_frame_id": "base_link"},
                    ],
                )
            )
            runtime_nodes.append(
                Node(
                    package="nexus_fastlio",
                    executable="fastlio_imu_adapter",
                    name="fastlio_imu_adapter",
                    output="screen",
                    parameters=[
                        {"use_sim_time": True},
                        {"input_topic": fastlio2_imu_input_topic},
                        {"output_topic": fastlio2_imu_output_topic},
                        {"linear_accel_scale": fastlio2_imu_linear_accel_scale},
                        {"rotation_pitch_deg": fastlio2_imu_rotation_pitch_deg},
                        {"target_frame_id": "base_link"},
                    ],
                )
            )
            runtime_nodes.append(
                ExecuteProcess(
                    cmd=[
                        fastlio2_bin,
                        "--ros-args",
                        "-r",
                        f"__ns:={fastlio2_namespace}",
                        *(["-r", f"/tf:={fastlio2_tf_topic}"] if fastlio2_tf_topic else []),
                        "-p",
                        f"config_path:={fastlio2_config}",
                    ],
                    output="screen",
                )
            )
            if fastlio2_enable_rviz and os.path.exists(fastlio2_rviz_config):
                runtime_nodes.append(
                    Node(
                        package="rviz2",
                        executable="rviz2",
                        name="fastlio2_rviz",
                        namespace=fastlio2_namespace.strip("/"),
                        output="screen",
                        arguments=["-d", fastlio2_rviz_config],
                        parameters=[{"use_sim_time": True}],
                    )
                )
        else:
            runtime_nodes.append(
                LogInfo(
                    msg=(
                        f"[WARN] fastlio2 not started because bin/config missing: "
                        f"bin={fastlio2_bin} config={fastlio2_config}"
                    )
                )
            )

    actions.extend(
        [
            robot_state_pub,
            RegisterEventHandler(
                OnProcessStart(target_action=robot_state_pub, on_start=[spawn_robot])
            ),
            RegisterEventHandler(
                OnProcessExit(target_action=spawn_robot, on_exit=runtime_nodes)
            ),
        ]
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
                description="Whether to spawn the omni robot and its controllers.",
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
                "enable_tf_pub",
                default_value=os.getenv("MAP_SIM_ENABLE_TF_PUB", "0"),
                description="Whether to publish the Gazebo world-pose / odom TF plugin.",
            ),
            DeclareLaunchArgument(
                "tf_pub_publish_nav_tf",
                default_value=os.getenv("MAP_SIM_TF_PUB_PUBLISH_NAV_TF", "1"),
                description="Whether the Gazebo TF plugin should broadcast nav TF on /tf.",
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
            DeclareLaunchArgument(
                "switch_timeout",
                default_value=os.getenv("MAP_SIM_SWITCH_TIMEOUT", "180.0"),
            ),
            DeclareLaunchArgument(
                "enable_pointcloud_pipeline",
                default_value=os.getenv("MAP_SIM_ENABLE_POINTCLOUD_PIPELINE", "0"),
                description="Whether to start the built-in pointcloud processing bridge.",
            ),
            DeclareLaunchArgument(
                "pointcloud_publish_world",
                default_value=os.getenv("MAP_SIM_POINTCLOUD_PUBLISH_WORLD", "1"),
                description="Whether lidar_to_world should publish a world-frame cloud.",
            ),
            DeclareLaunchArgument(
                "pointcloud_publish_body",
                default_value=os.getenv("MAP_SIM_POINTCLOUD_PUBLISH_BODY", "1"),
                description="Whether lidar_to_world should publish a base_link-frame cloud.",
            ),
            DeclareLaunchArgument(
                "pointcloud_accumulate_world",
                default_value=os.getenv("MAP_SIM_POINTCLOUD_ACCUMULATE_WORLD", "0"),
                description="Whether to accumulate / save the world-frame cloud online.",
            ),
            DeclareLaunchArgument(
                "pointcloud_input_topic",
                default_value=os.getenv(
                    "MAP_SIM_POINTCLOUD_INPUT_TOPIC", "/livox/lidar_PointCloud2"
                ),
            ),
            DeclareLaunchArgument(
                "pointcloud_world_topic",
                default_value=os.getenv("MAP_SIM_POINTCLOUD_WORLD_TOPIC", "/cloud_registered"),
            ),
            DeclareLaunchArgument(
                "pointcloud_body_topic",
                default_value=os.getenv("MAP_SIM_POINTCLOUD_BODY_TOPIC", "/cloud_body"),
            ),
            DeclareLaunchArgument(
                "pointcloud_base_pose_topic",
                default_value=os.getenv(
                    "MAP_SIM_POINTCLOUD_BASE_POSE_TOPIC", "/cube_robot/world_pose"
                ),
            ),
            DeclareLaunchArgument(
                "pointcloud_world_downsample_stride",
                default_value=os.getenv("MAP_SIM_POINTCLOUD_WORLD_DOWNSAMPLE_STRIDE", "1"),
            ),
            DeclareLaunchArgument(
                "pointcloud_accum_topic",
                default_value=os.getenv(
                    "MAP_SIM_POINTCLOUD_ACCUM_TOPIC", "/cloud_registered_accum"
                ),
            ),
            DeclareLaunchArgument(
                "pointcloud_save_path",
                default_value=os.getenv(
                    "MAP_SIM_POINTCLOUD_SAVE_PATH", "accumulated_map_ds.pcd"
                ),
            ),
            DeclareLaunchArgument(
                "pointcloud_accum_voxel",
                default_value=os.getenv("MAP_SIM_POINTCLOUD_ACCUM_VOXEL", "0.05"),
            ),
            DeclareLaunchArgument(
                "pointcloud_accum_z_min",
                default_value=os.getenv("MAP_SIM_POINTCLOUD_ACCUM_Z_MIN", "0.05"),
            ),
            DeclareLaunchArgument(
                "pointcloud_enable_keyboard_save",
                default_value=os.getenv("MAP_SIM_POINTCLOUD_ENABLE_KEYBOARD_SAVE", "0"),
            ),
            DeclareLaunchArgument(
                "pointcloud_sensor_offset_x",
                default_value=os.getenv("MAP_SIM_POINTCLOUD_SENSOR_OFFSET_X", "0.0"),
            ),
            DeclareLaunchArgument(
                "pointcloud_sensor_offset_y",
                default_value=os.getenv("MAP_SIM_POINTCLOUD_SENSOR_OFFSET_Y", "0.0"),
            ),
            DeclareLaunchArgument(
                "pointcloud_sensor_offset_z",
                default_value=os.getenv("MAP_SIM_POINTCLOUD_SENSOR_OFFSET_Z", "0.4"),
            ),
            DeclareLaunchArgument(
                "pointcloud_sensor_pitch_deg",
                default_value=os.getenv("MAP_SIM_POINTCLOUD_SENSOR_PITCH_DEG", "30.0"),
            ),
            DeclareLaunchArgument(
                "enable_fastlio2",
                default_value=os.getenv("MAP_SIM_ENABLE_FASTLIO2", "0"),
                description="Whether to start the external FAST-LIO2 lio_node process.",
            ),
            DeclareLaunchArgument(
                "fastlio2_bin",
                default_value=os.getenv(
                    "MAP_SIM_FASTLIO2_BIN",
                    os.path.join(_REPO_ROOT, "third_party", "FASTLIO2_ROS2", "install_nexus", "fastlio2", "lib", "fastlio2", "lio_node"),
                ),
            ),
            DeclareLaunchArgument(
                "fastlio2_config",
                default_value=os.getenv(
                    "MAP_SIM_FASTLIO2_CONFIG",
                    os.path.join(
                        get_package_share_directory("ros2_livox_simulation"),
                        "config",
                        "fastlio2_sim.yaml",
                    ),
                ),
            ),
            DeclareLaunchArgument(
                "fastlio2_namespace",
                default_value=os.getenv("MAP_SIM_FASTLIO2_NAMESPACE", "/fastlio2"),
            ),
            DeclareLaunchArgument(
                "fastlio2_tf_topic",
                default_value=os.getenv("MAP_SIM_FASTLIO2_TF_TOPIC", ""),
                description="Optional remap target for FAST-LIO /tf output. Empty keeps /tf.",
            ),
            DeclareLaunchArgument(
                "fastlio2_enable_rviz",
                default_value=os.getenv("MAP_SIM_FASTLIO2_ENABLE_RVIZ", "0"),
            ),
            DeclareLaunchArgument(
                "fastlio2_rviz_config",
                default_value=os.getenv(
                    "MAP_SIM_FASTLIO2_RVIZ_CONFIG",
                    os.path.join(_REPO_ROOT, "third_party", "FASTLIO2_ROS2", "fastlio2", "rviz", "fastlio2.rviz"),
                ),
            ),
            DeclareLaunchArgument(
                "fastlio2_lidar_input_topic",
                default_value=os.getenv("MAP_SIM_FASTLIO2_LIDAR_INPUT_TOPIC", "/livox/lidar"),
            ),
            DeclareLaunchArgument(
                "fastlio2_lidar_output_topic",
                default_value=os.getenv("MAP_SIM_FASTLIO2_LIDAR_OUTPUT_TOPIC", "/lidar_fastlio"),
            ),
            DeclareLaunchArgument(
                "fastlio2_lidar_rotation_pitch_deg",
                default_value=os.getenv("MAP_SIM_FASTLIO2_LIDAR_ROTATION_PITCH_DEG", "30.0"),
            ),
            DeclareLaunchArgument(
                "fastlio2_imu_input_topic",
                default_value=os.getenv("MAP_SIM_FASTLIO2_IMU_INPUT_TOPIC", "/imu_fixed"),
            ),
            DeclareLaunchArgument(
                "fastlio2_imu_output_topic",
                default_value=os.getenv("MAP_SIM_FASTLIO2_IMU_OUTPUT_TOPIC", "/imu_fastlio"),
            ),
            DeclareLaunchArgument(
                "fastlio2_imu_linear_accel_scale",
                default_value=os.getenv("MAP_SIM_FASTLIO2_IMU_LINEAR_ACCEL_SCALE", "0.1"),
            ),
            DeclareLaunchArgument(
                "fastlio2_imu_rotation_pitch_deg",
                default_value=os.getenv("MAP_SIM_FASTLIO2_IMU_ROTATION_PITCH_DEG", "30.0"),
            ),
            DeclareLaunchArgument("spawn_x", default_value=os.getenv("MAP_SIM_SPAWN_X", "0.0")),
            DeclareLaunchArgument("spawn_y", default_value=os.getenv("MAP_SIM_SPAWN_Y", "0.0")),
            DeclareLaunchArgument("spawn_z", default_value=os.getenv("MAP_SIM_SPAWN_Z", "0.19")),
            OpaqueFunction(function=_launch_setup),
        ]
    )
