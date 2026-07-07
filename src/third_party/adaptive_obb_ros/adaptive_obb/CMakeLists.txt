cmake_minimum_required(VERSION 3.8)
project(adaptive_obb)

foreach(_local_pkg kdtree planner_msgs planner_semantic_msgs voxblox voxblox_msgs voxblox_ros planner_common)
  set(_local_prefix
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../install/${_local_pkg}"
  )
  if(EXISTS "${_local_prefix}/share/${_local_pkg}/cmake/${_local_pkg}Config.cmake")
    list(APPEND CMAKE_PREFIX_PATH "${_local_prefix}")
  endif()
endforeach()

find_package(ament_cmake REQUIRED)
find_package(Eigen3 REQUIRED NO_MODULE)
find_package(PCL REQUIRED COMPONENTS common filters)
find_package(planner_common REQUIRED)

add_library(${PROJECT_NAME} SHARED
  src/adaptive_obb.cpp
)
target_compile_features(${PROJECT_NAME} PUBLIC cxx_std_14)
target_include_directories(${PROJECT_NAME} PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
  ${PCL_INCLUDE_DIRS}
)
target_link_libraries(${PROJECT_NAME}
  Eigen3::Eigen
  ${PCL_LIBRARIES}
)
ament_target_dependencies(${PROJECT_NAME}
  planner_common
)
add_definitions(${PCL_DEFINITIONS})

install(DIRECTORY include/ DESTINATION include)
install(TARGETS ${PROJECT_NAME}
  EXPORT export_${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

ament_export_targets(export_${PROJECT_NAME} HAS_LIBRARY_TARGET)
ament_export_dependencies(planner_common)
ament_export_include_directories(include)

ament_package()
