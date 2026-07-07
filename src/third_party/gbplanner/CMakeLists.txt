cmake_minimum_required(VERSION 3.8)
project(gbplanner)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_definitions(-Wall -Wno-sign-compare -Wno-catch-value -Wno-switch -Wno-maybe-uninitialized -Werror=return-type)

foreach(_local_pkg adaptive_obb kdtree planner_common planner_msgs planner_semantic_msgs voxblox voxblox_msgs voxblox_ros)
  set(_local_prefix
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../install/${_local_pkg}"
  )
  if(EXISTS "${_local_prefix}/share/${_local_pkg}/cmake/${_local_pkg}Config.cmake")
    list(APPEND CMAKE_PREFIX_PATH "${_local_prefix}")
  endif()
endforeach()

find_package(ament_cmake REQUIRED)
find_package(Boost REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(OpenCV REQUIRED)
find_package(PCL REQUIRED COMPONENTS common filters)
find_package(gflags REQUIRED)
find_package(glog REQUIRED)
find_package(adaptive_obb REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(kdtree REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(planner_common REQUIRED)
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

set(GBPLANNER_GFLAGS_TARGET "")
if(TARGET gflags::gflags)
  set(GBPLANNER_GFLAGS_TARGET gflags::gflags)
elseif(TARGET gflags::gflags_shared)
  set(GBPLANNER_GFLAGS_TARGET gflags::gflags_shared)
elseif(TARGET gflags_shared)
  set(GBPLANNER_GFLAGS_TARGET gflags_shared)
endif()

if(GBPLANNER_GFLAGS_TARGET STREQUAL "")
  message(FATAL_ERROR "Unable to determine a usable gflags CMake target.")
endif()

include_directories(
  ${Boost_INCLUDE_DIRS}
  ${OpenCV_INCLUDE_DIRS}
  ${PCL_INCLUDE_DIRS}
)

add_library(${PROJECT_NAME}
  src/gbplanner.cpp
  src/rrg.cpp
  src/gbplanner_rviz.cpp
)
target_include_directories(${PROJECT_NAME}
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../planner_msgs/include>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../planner_semantic_msgs/include>
    $<INSTALL_INTERFACE:include>
    ${PCL_INCLUDE_DIRS}
    ${OpenCV_INCLUDE_DIRS}
)
target_link_libraries(${PROJECT_NAME}
  Eigen3::Eigen
  ${OpenCV_LIBRARIES}
  ${PCL_LIBRARIES}
)
add_definitions(${PCL_DEFINITIONS})
ament_target_dependencies(${PROJECT_NAME}
  adaptive_obb
  geometry_msgs
  kdtree
  nav_msgs
  planner_common
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
)

add_executable(gbplanner_node src/gbplanner_ros_node.cpp)
target_link_libraries(gbplanner_node
  ${PROJECT_NAME}
  ${GBPLANNER_GFLAGS_TARGET}
  glog::glog
)

install(
  TARGETS ${PROJECT_NAME} gbplanner_node
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY include/
  DESTINATION include
)

ament_export_include_directories(include)
ament_export_libraries(${PROJECT_NAME})
ament_export_dependencies(
  adaptive_obb
  geometry_msgs
  kdtree
  nav_msgs
  planner_common
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
)

ament_package()
