cmake_minimum_required(VERSION 3.8)
project(planner_common)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_definitions(-Wall -Wno-sign-compare -Wno-unused-variable -Wno-unused-but-set-variable -Wno-format -Werror=return-type)

# Point collision checking:
#   0 - Orignal
#   1 - Direct TSDF/ESDF distance check (requires continuous path check during execution)
#   2 - Using interpolated tsdf distance
add_definitions(-DCOL_CHECK_METHOD=0)
# Line collision checking: 
#   0 - Orignal
#   1 - Cuboid around the edge
#   2 - Direct TSDF/ESDF distance check (requires continuous path check during execution)
#   3 - Using interpolated tsdf distance
add_definitions(-DEDGE_CHECK_METHOD=1)
# Ray casting: 
#   0 - Original
#   1 - Iterative ray casting
add_definitions(-DRAY_CAST_METHOD=1)

# Verify the values of the definitions
get_directory_property( DirDefs COMPILE_DEFINITIONS ) 
message( "COMPILE DEFINITIONS: ${DirDefs}" )

find_package(ament_cmake REQUIRED)
find_package(Boost REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(kdtree REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(PCL REQUIRED COMPONENTS common)
find_package(FLANN REQUIRED)
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

foreach(_optional_local_pkg voxblox_msgs voxblox_ros)
  set(_optional_local_prefix
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../install/${_optional_local_pkg}"
  )
  if(EXISTS
      "${_optional_local_prefix}/share/${_optional_local_pkg}/cmake/${_optional_local_pkg}Config.cmake")
    list(APPEND CMAKE_PREFIX_PATH "${_optional_local_prefix}")
  endif()
endforeach()

find_package(voxblox_ros QUIET)

set(PLANNER_COMMON_SOURCES
  src/graph_manager.cpp
  src/graph.cpp
  src/params.cpp
  src/trajectory.cpp
  src/random_sampler.cpp
  src/geofence_manager.cpp
)

if(voxblox_ros_FOUND)
  list(APPEND PLANNER_COMMON_SOURCES
    src/voxblox/voxblox_common_impl.cpp
    src/voxblox/voxblox_alt_impl.cpp
  )
endif()

add_library(${PROJECT_NAME} ${PLANNER_COMMON_SOURCES})
set_target_properties(${PROJECT_NAME} PROPERTIES
  POSITION_INDEPENDENT_CODE ON
)
target_include_directories(${PROJECT_NAME}
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../planner_msgs/include>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../planner_semantic_msgs/include>
    $<INSTALL_INTERFACE:include>
    ${PCL_INCLUDE_DIRS}
)
target_link_libraries(${PROJECT_NAME}
  Eigen3::Eigen
  ${PCL_LIBRARIES}
)
add_definitions(${PCL_DEFINITIONS})
ament_target_dependencies(${PROJECT_NAME}
  geometry_msgs
  kdtree
  nav_msgs
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
)

if(voxblox_ros_FOUND)
  ament_target_dependencies(${PROJECT_NAME}
    voxblox_ros
  )
else()
  message(WARNING "voxblox_ros not found. planner_common will be built without the original Voxblox backend sources.")
endif()

install(
  TARGETS ${PROJECT_NAME}
  EXPORT export_${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

install(DIRECTORY include/
  DESTINATION include
)

ament_export_include_directories(include)
ament_export_libraries(${PROJECT_NAME})
set(PLANNER_COMMON_EXPORT_DEPENDENCIES
  geometry_msgs
  kdtree
  nav_msgs
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
)

if(voxblox_ros_FOUND)
  list(APPEND PLANNER_COMMON_EXPORT_DEPENDENCIES
    voxblox_ros
  )
endif()

ament_export_dependencies(${PLANNER_COMMON_EXPORT_DEPENDENCIES})

ament_package()
