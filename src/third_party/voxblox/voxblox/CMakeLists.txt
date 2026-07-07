cmake_minimum_required(VERSION 3.8)
project(voxblox)

find_package(ament_cmake REQUIRED)
find_package(Eigen3 REQUIRED NO_MODULE)
find_package(minkindr REQUIRED)
find_package(Protobuf REQUIRED)

find_package(glog QUIET)
if(NOT TARGET glog::glog)
  find_path(GLOG_INCLUDE_DIR glog/logging.h REQUIRED)
  find_library(GLOG_LIBRARY NAMES glog REQUIRED)
  add_library(glog::glog UNKNOWN IMPORTED)
  set_target_properties(glog::glog PROPERTIES
    IMPORTED_LOCATION "${GLOG_LIBRARY}"
    INTERFACE_INCLUDE_DIRECTORIES "${GLOG_INCLUDE_DIR}"
  )
endif()

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MACOSX_RPATH 0)
add_compile_options(-Wall -Wextra)

set(PROTO_DEFNS
  proto/voxblox/Block.proto
  proto/voxblox/Layer.proto
)
protobuf_generate_cpp(PROTO_SRCS PROTO_HDRS ${PROTO_DEFNS})

set(${PROJECT_NAME}_SRCS
  src/alignment/icp.cc
  src/core/block.cc
  src/core/esdf_map.cc
  src/core/tsdf_map.cc
  src/integrator/esdf_integrator.cc
  src/integrator/esdf_occ_integrator.cc
  src/integrator/integrator_utils.cc
  src/integrator/intensity_integrator.cc
  src/integrator/tsdf_integrator.cc
  src/io/mesh_ply.cc
  src/io/sdf_ply.cc
  src/mesh/marching_cubes.cc
  src/simulation/objects.cc
  src/simulation/simulation_world.cc
  src/utils/camera_model.cc
  src/utils/evaluation_utils.cc
  src/utils/layer_utils.cc
  src/utils/neighbor_tools.cc
  src/utils/protobuf_utils.cc
  src/utils/timing.cc
  src/utils/voxel_utils.cc
)

add_library(${PROJECT_NAME} SHARED
  ${${PROJECT_NAME}_SRCS}
  ${PROTO_SRCS}
)
target_include_directories(${PROJECT_NAME} PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}>
  $<INSTALL_INTERFACE:include>
  ${Protobuf_INCLUDE_DIRS}
)
target_link_libraries(${PROJECT_NAME}
  Eigen3::Eigen
  ${GLOG_LIBRARY}
  ${Protobuf_LIBRARIES}
)
ament_target_dependencies(${PROJECT_NAME}
  minkindr
)

install(DIRECTORY include/ DESTINATION include)
install(FILES ${PROTO_HDRS} DESTINATION include/voxblox/core)
install(FILES ${PROTO_HDRS} DESTINATION include/voxblox/io)
install(TARGETS ${PROJECT_NAME}
  EXPORT export_${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

ament_export_targets(export_${PROJECT_NAME} HAS_LIBRARY_TARGET)
ament_export_dependencies(minkindr)
ament_export_include_directories(include)

ament_package()
