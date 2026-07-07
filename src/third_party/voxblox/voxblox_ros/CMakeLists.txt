cmake_minimum_required(VERSION 3.8)
project(voxblox_ros)

find_package(ament_cmake REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(PCL REQUIRED COMPONENTS common filters)
find_package(pcl_conversions REQUIRED)
find_package(planner_msgs REQUIRED)
find_package(planner_semantic_msgs REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(std_srvs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(visualization_msgs REQUIRED)
find_package(voxblox REQUIRED)
find_package(voxblox_msgs REQUIRED)

set(PLANNER_COMMON_SOURCE_INCLUDE_DIR
  "${CMAKE_CURRENT_SOURCE_DIR}/../../planner_common/include"
)

add_library(${PROJECT_NAME} SHARED
  src/esdf_server.cc
  src/transformer.cc
  src/tsdf_server.cc
)
target_compile_features(${PROJECT_NAME} PUBLIC cxx_std_14)
target_include_directories(${PROJECT_NAME} PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<BUILD_INTERFACE:${PLANNER_COMMON_SOURCE_INCLUDE_DIR}>
  $<INSTALL_INTERFACE:include>
  ${PCL_INCLUDE_DIRS}
)
add_definitions(${PCL_DEFINITIONS})
ament_target_dependencies(${PROJECT_NAME}
  geometry_msgs
  nav_msgs
  pcl_conversions
  planner_msgs
  planner_semantic_msgs
  rclcpp
  sensor_msgs
  std_msgs
  std_srvs
  tf2
  tf2_geometry_msgs
  tf2_ros
  visualization_msgs
  voxblox
  voxblox_msgs
)

install(DIRECTORY include/ DESTINATION include)
install(TARGETS ${PROJECT_NAME}
  EXPORT export_${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

ament_export_targets(export_${PROJECT_NAME} HAS_LIBRARY_TARGET)
ament_export_dependencies(
  geometry_msgs
  nav_msgs
  pcl_conversions
  planner_msgs
  planner_semantic_msgs
  rclcpp
  sensor_msgs
  std_msgs
  std_srvs
  tf2
  tf2_geometry_msgs
  tf2_ros
  visualization_msgs
  voxblox
  voxblox_msgs
)
ament_export_include_directories(include)

ament_package()
