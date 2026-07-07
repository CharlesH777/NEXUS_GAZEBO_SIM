"""
Minimal Nav2 launch for the NEXUS swerve robot.

Uses the official nav2_mppi_controller with Omni motion model.
Frames: world (global) / base_footprint (robot).
Costmap source: /traversability_map OccupancyGrid.
Goal input: /goal_pose via nav2_goal_bridge -> NavigateToPose action.

cmd_vel routing:
  - Without Sand MPC (default): controller -> /cmd_vel -> cmd_vel_to_swerve
  - With Sand MPC: controller -> /mppi/cmd_vel_raw -> sand_mpc -> /cmd_vel -> cmd_vel_to_swerve
  Set cmd_vel_topic launch arg to control this.
"""
import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, TimerAction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from nav2_common.launch import RewrittenYaml
from launch_ros.descriptions import ParameterFile


def generate_launch_description():
    use_sim_time = LaunchConfiguration("use_sim_time")
    params_file = LaunchConfiguration("params_file")
    cmd_vel_topic = LaunchConfiguration("cmd_vel_topic")

    root_dir = os.environ.get("MAP_SIM_ROOT", os.getcwd())
    default_params = os.path.join(root_dir, "config", "nav2_mppi_params.yaml")

    configured_params = ParameterFile(
        RewrittenYaml(
            source_file=params_file,
            param_rewrites={"use_sim_time": use_sim_time},
            convert_types=True,
        ),
        allow_substs=True,
    )

    lifecycle_nodes = [
        "controller_server",
        "smoother_server",
        "planner_server",
        "behavior_server",
        "bt_navigator",
        "waypoint_follower",
    ]

    remappings = [("/tf", "tf"), ("/tf_static", "tf_static")]
    # Both controller_server and behavior_server publish velocity commands.
    # Remap cmd_vel so Sand MPC can sit in the middle when enabled.
    vel_remappings = remappings + [("cmd_vel", cmd_vel_topic)]

    return LaunchDescription(
        [
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            DeclareLaunchArgument("params_file", default_value=default_params),
            DeclareLaunchArgument(
                "cmd_vel_topic",
                default_value="/cmd_vel",
                description="Topic for controller velocity output. "
                "Use /mppi/cmd_vel_raw when Sand MPC is enabled.",
            ),
            # controller_server — publishes to cmd_vel_topic
            Node(
                package="nav2_controller",
                executable="controller_server",
                output="screen",
                parameters=[configured_params],
                remappings=vel_remappings,
            ),
            # planner_server — NavFn global planner
            Node(
                package="nav2_planner",
                executable="planner_server",
                name="planner_server",
                output="screen",
                parameters=[configured_params],
                remappings=remappings,
            ),
            # behavior_server — recovery behaviors (spin, backup, wait)
            Node(
                package="nav2_behaviors",
                executable="behavior_server",
                name="behavior_server",
                output="screen",
                parameters=[configured_params],
                remappings=vel_remappings,
            ),
            # smoother_server — path smoother (optional, used by BT)
            Node(
                package="nav2_smoother",
                executable="smoother_server",
                name="smoother_server",
                output="screen",
                parameters=[configured_params],
                remappings=remappings,
            ),
            # bt_navigator — orchestrates planner + controller via behavior tree
            Node(
                package="nav2_bt_navigator",
                executable="bt_navigator",
                name="bt_navigator",
                output="screen",
                parameters=[configured_params],
                remappings=remappings,
            ),
            # waypoint_follower
            Node(
                package="nav2_waypoint_follower",
                executable="waypoint_follower",
                name="waypoint_follower",
                output="screen",
                parameters=[configured_params],
                remappings=remappings,
            ),
            # lifecycle_manager — starts all lifecycle nodes in order
            Node(
                package="nav2_lifecycle_manager",
                executable="lifecycle_manager",
                name="lifecycle_manager",
                output="screen",
                parameters=[
                    {"use_sim_time": use_sim_time},
                    {"autostart": True},
                    {"node_names": lifecycle_nodes},
                    {"bond_timeout": 10.0},
                    {"bond_connect_timeout": 30.0},
                    {"attempt_respawn_reconnection": True},
                ],
            ),
            # Continuous navigator: /goal_pose -> planner + controller
            # Pre-plans next path while current one executes → no stop-and-go.
            # Coasts forward when no goal is active so the robot never stops.
            TimerAction(
                period=8.0,
                actions=[
                    ExecuteProcess(
                        cmd=[
                            "/usr/bin/python3",
                            os.path.join(root_dir, "scripts", "continuous_navigator.py"),
                            "--ros-args",
                            "-p",
                            "use_sim_time:=true",
                            "-p",
                            "global_frame:=world",
                            "-p",
                            "robot_frame:=base_footprint",
                            "-p",
                            "preplan_distance:=3.0",
                            "-p",
                            "switch_distance:=1.5",
                            "-p",
                            "coast_velocity:=0.3",
                        ],
                        output="screen",
                    ),
                ],
            ),
        ]
    )
