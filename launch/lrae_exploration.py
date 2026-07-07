#!/usr/bin/env python3
"""
LRAE 探索规划 Launch 文件
集成到 NEXUS Livox MID-360 仿真环境
"""
from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    # 参数
    use_sim_time = LaunchConfiguration("use_sim_time")
    local_planner_share = Path(get_package_share_directory("local_planner"))

    # LRAE 探索规划节点
    lrae_planner_node = Node(
        package="lrae_planner",
        executable="lrae_planner_node",
        name="lrae_planner_node",
        parameters=[{
            "use_sim_time": use_sim_time,
            "autonomyMode": True,  # 启用自主探索模式
            "autonomySpeed": 1.0,
            "angle_pen": 0.45,
            "update_cen_thre": 6,  # README 推荐值
            "unknown_num_thre": 200,  # README 推荐值 - 关键参数！
            "minrange": 20.0,  # README 推荐值
            "limit_max_square": True,  # README 推荐值
            "use_go_end_nearest": True,  # README 推荐值
            "end_neacen_disthre": 10.0,
            "end_cur_disrate": 2.0,
        }],
        remappings=[
            ("/registered_scan", "/cloud_registered"),       # Livox 点云
            ("/state_estimation", "/cube_robot/world_pose"), # 机器人位姿
            ("/terrain_map", "/plane_OccMap"),               # 通行性地图
        ],
        output="screen",
    )

    # 探索地图合并节点
    exploration_map_merge = Node(
        package="lrae_planner",
        executable="exploration_map_merge",
        name="exploration_map_merge",
        parameters=[{
            "use_sim_time": use_sim_time,
            "map_w": 216,
            "map_h": 216,
            # Center the stitched global map around the spawn area so the robot
            # does not immediately walk outside the map bounds in marsyard2020.
            "mapinitox": -32.4,
            "mapinitoy": -32.4,
            "merge_size": 9.0,
            "safe_obs_dis": 0.8,
        }],
        output="screen",
    )

    # 通行性建图节点
    traversibility_mapping = Node(
        package="fitplane",
        executable="Traversibility_mapping",
        name="Traversibility_mapping",
        parameters=[{
            "PointCloud_Map_topic": "/cloud_registered",
            "Grid_Map_topic": "/grid_map",
            "use_sim_time": use_sim_time,
            # Slightly relax terrain classification so low roughness bumps and
            # obstacle halos do not block exploration as aggressively.
            "max_angle_deg": 48.0,
            "max_flatness": 0.02,
            "angle_weight": 0.8,
            "occupied_value": 100,
            "inflation_value": 94,
            "near_obstacle_value": 118,
        }],
        output="screen",
    )

    # 局部规划器
    local_planner = Node(
        package="local_planner",
        executable="localPlanner",
        name="localPlanner",
        parameters=[{
            "use_sim_time": use_sim_time,
            "pathFolder": str(local_planner_share / "paths"),
            "vehicleLength": 0.6,
            "vehicleWidth": 0.6,
            "twoWayDrive": True,
            "laserVoxelSize": 0.05,
            "terrainVoxelSize": 0.2,
            "useTerrainAnalysis": True,
            "obstacleHeightThre": 0.5,
            "autonomyMode": True,
            "autonomySpeed": 1.0,
            "goalStaleTime": 2.0,
        }],
        remappings=[
            ("/state_estimation", "/cube_robot/world_odom"),
            ("/terrain_map", "/local_traversibility_ponit_cloud"),
            ("/way_point", "/look_ahead_goal"),  # 关键：映射到 look_ahead_goal
        ],
        output="screen",
    )

    # 路径跟随器
    path_follower = Node(
        package="local_planner",
        executable="pathFollower",
        name="pathFollower",
        parameters=[{
            "use_sim_time": use_sim_time,
            "sensorOffsetX": 0.0,
            "sensorOffsetY": 0.0,
            "twoWayDrive": True,
            "lookAheadDis": 1.0,
            "yawRateGain": 3.0,
            "stopYawRateGain": 5.0,
            "maxSpeed": 0.5,
            "autonomyMode": True,
            "autonomySpeed": 0.5,
            "maxYawRate": 25.0,
            "dirDiffThre": 1.2,
            "pathStaleTime": 2.0,
        }],
        remappings=[
            ("/state_estimation", "/cube_robot/world_odom"),
        ],
        output="screen",
    )

    # 局部目标生成
    gen_local_goal = Node(
        package="gen_local_goal",
        executable="gen_local_goal_node",
        name="gen_local_goal_node",
        parameters=[{
            "use_sim_time": use_sim_time,
            "enable_blind_forward_fallback": False,
            "enable_scan_recovery": True,
            "scan_recovery_yaw_rate": 0.6,
            "recovery_trigger_cycles": 20,
            "path_stale_timeout_sec": 2.0,
        }],
        output="screen",
    )

    # TF 桥接：使用仿真真值发布完整 TF 树
    sim_truth_tf = Node(
        package="sensor_conversion",
        executable="sim_truth_tf_publisher.py",
        name="sim_truth_tf_publisher",
        parameters=[{
            "use_sim_time": use_sim_time,
        }],
        output="screen",
    )

    return LaunchDescription([
        DeclareLaunchArgument("use_sim_time", default_value="true"),

        sim_truth_tf,  # 先启动 TF 发布器
        traversibility_mapping,
        exploration_map_merge,  # 探索地图合并
        lrae_planner_node,
        local_planner,  # 现在启用 localPlanner
        path_follower,  # 启用 pathFollower
        gen_local_goal,
    ])
