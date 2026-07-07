cmake_minimum_required(VERSION 3.5)
project(ros2_livox_simulation)

if(POLICY CMP0167)
  cmake_policy(SET CMP0167 OLD)
endif()

set(CMAKE_POLICY_VERSION_MINIMUM 3.5)

add_compile_options(-std=c++17)

# Default to C99
if(NOT CMAKE_C_STANDARD)
  set(CMAKE_C_STANDARD 99)
endif()

# Default to C++14
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 14)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# ===============================
# find dependencies
# ===============================
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(gazebo_dev REQUIRED)
find_package(gazebo_ros REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(livox_ros_driver2 REQUIRED)
find_package(Boost REQUIRED COMPONENTS chrono)
find_package(Eigen3 REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(rosgraph_msgs REQUIRED)

# ===============================
# include & link directories
# ===============================
include_directories(
  include
)
include_directories(${GAZEBO_INCLUDE_DIRS})
include_directories(/usr/include/gazebo-11/gazebo)
link_directories(${GAZEBO_LIBRARY_DIRS})

# ===============================
# install include
# ===============================
install(DIRECTORY include/
        DESTINATION include
)

# ===============================
# Gazebo plugin library (Livox)
# ===============================
add_library(ros2_livox SHARED
  src/livox_points_plugin.cpp
  src/livox_ode_multiray_shape.cpp
)

target_link_libraries(ros2_livox
  ${GAZEBO_LIBRARIES}
  RayPlugin
  GpuRayPlugin
  libprotobuf.so.9
  libboost_chrono.so.1.71.0
)

ament_target_dependencies(ros2_livox
  rclcpp
  std_msgs
  sensor_msgs
  geometry_msgs
  gazebo_dev
  gazebo_ros
  tf2_ros
  livox_ros_driver2
)

target_include_directories(ros2_livox PRIVATE include)

install(TARGETS ros2_livox
  LIBRARY DESTINATION lib
)

# ===============================
# Gazebo plugin library (TF publisher)
# ===============================
add_library(tf_pub SHARED
  src/tf_pub.cpp
)

target_link_libraries(tf_pub
  ${GAZEBO_LIBRARIES}
)

ament_target_dependencies(tf_pub
  rclcpp
  tf2
  geometry_msgs
  tf2_ros
  gazebo_dev
  gazebo_ros
  nav_msgs
  rosgraph_msgs
)

target_include_directories(tf_pub PRIVATE include)

install(TARGETS tf_pub
  LIBRARY DESTINATION lib
)

# ===============================
# Gazebo plugin library (Solar lighting)
# ===============================
add_library(solar_lighting_world_plugin SHARED
  src/solar_lighting_world_plugin.cpp
)

target_link_libraries(solar_lighting_world_plugin
  ${GAZEBO_LIBRARIES}
)

ament_target_dependencies(solar_lighting_world_plugin
  rclcpp
  std_msgs
  gazebo_dev
)

target_include_directories(solar_lighting_world_plugin PRIVATE include)

install(TARGETS solar_lighting_world_plugin
  LIBRARY DESTINATION lib
)

# ===============================
# Gazebo plugin library (Runtime mount follower)
# ===============================
add_library(runtime_mount_follower_plugin SHARED
  src/runtime_mount_follower_plugin.cpp
)

target_link_libraries(runtime_mount_follower_plugin
  ${GAZEBO_LIBRARIES}
)

ament_target_dependencies(runtime_mount_follower_plugin
  gazebo_dev
)

target_include_directories(runtime_mount_follower_plugin PRIVATE include)

install(TARGETS runtime_mount_follower_plugin
  LIBRARY DESTINATION lib
)

# ===============================
# FixImuTime node (C++)
# ===============================
add_executable(fix_imu_time
  src/fix_imu_time.cpp
)

ament_target_dependencies(fix_imu_time
  rclcpp
  sensor_msgs
  geometry_msgs
)

install(TARGETS
  fix_imu_time
  DESTINATION lib/${PROJECT_NAME}
)

# ===============================
# LidarToWorld node (C++)
# ===============================
add_executable(lidar_to_world
  src/fix_cloud_time.cpp
)

target_link_libraries(lidar_to_world
  Eigen3::Eigen
)

ament_target_dependencies(lidar_to_world
  rclcpp
  sensor_msgs
  geometry_msgs
)

install(TARGETS
  lidar_to_world
  DESTINATION lib/${PROJECT_NAME}
)

install(PROGRAMS
  scripts/cmd_vel_to_swerve.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME cmd_vel_to_swerve
)

install(PROGRAMS
  scripts/spawn_omni_controllers.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME spawn_omni_controllers
)

install(PROGRAMS
  scripts/solar_time_panel.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME solar_time_panel
)

install(PROGRAMS
  scripts/clound_acc.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME cloud_accumulator
)

install(PROGRAMS
  scripts/runtime_depth_camera.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME runtime_depth_camera
)

# ===============================
# testing
# ===============================
if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

# ===============================
# export libraries
# ===============================
ament_export_libraries(
  ros2_livox
)

# ===============================
# install CSV files
# ===============================
set(CSV_FILES
  scan_mode/mid40.csv
  scan_mode/mid70.csv
  scan_mode/mid360.csv
  scan_mode/tele.csv
  scan_mode/horizon.csv
  scan_mode/HAP.csv
  scan_mode/avia.csv
)

foreach(CSV_FILE ${CSV_FILES})
  configure_file(${CSV_FILE} ${CMAKE_CURRENT_BINARY_DIR}/${CSV_FILE} COPYONLY)
  install(FILES ${CMAKE_CURRENT_BINARY_DIR}/${CSV_FILE}
    DESTINATION share/${PROJECT_NAME}/scan_mode
  )
endforeach()

# ===============================
# install URDF files
# ===============================
set(URDF_FILES
  urdf/depth_camera_gazebo.xacro
  urdf/mid40.xacro
  urdf/mid70.xacro
  urdf/mid360.xacro
  urdf/tele.xacro
  urdf/horizon.xacro
  urdf/HAP.xacro
  urdf/avia.xacro
  urdf/robot_sim.xacro
  urdf/robot_sim_omni.xacro
)

foreach(URDF_FILE ${URDF_FILES})
  configure_file(${URDF_FILE} ${CMAKE_CURRENT_BINARY_DIR}/${URDF_FILE} COPYONLY)
  install(FILES ${CMAKE_CURRENT_BINARY_DIR}/${URDF_FILE}
    DESTINATION share/${PROJECT_NAME}/urdf
  )
endforeach()

install(DIRECTORY launch urdf config world models
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
