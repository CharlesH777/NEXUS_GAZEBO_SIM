cmake_minimum_required(VERSION 3.8)
project(planner_msgs)
find_package(ament_cmake REQUIRED)
find_package(action_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)

set(msg_files
  "msg/RobotStatus.msg"
  "msg/RectangleShape.msg"
  "msg/BoundMode.msg"
  "msg/PlanningMode.msg"
  "msg/ExecutionPathMode.msg"
  "msg/TriggerMode.msg"
  "msg/PlannerStatus.msg"
  "msg/PlanningBound.msg"
  "msg/Vertex.msg"
  "msg/Edge.msg"
  "msg/Graph.msg"
  "msg/CoveragePlannerLogger.msg"
  "msg/BehaviourPlannerLogger.msg"
)

set(srv_files
  "srv/PlannerSrv.srv"
  "srv/PlannerGlobal.srv"
  "srv/PlannerSearch.srv"
  "srv/PlannerHoming.srv"
  "srv/PlannerSetHomingPos.srv"
  "srv/PlannerGeofence.srv"
  "srv/PlannerRequestPath.srv"
  "srv/PciTrigger.srv"
  "srv/PciHomingTrigger.srv"
  "srv/PciSetHomingPos.srv"
  "srv/PciInitialization.srv"
  "srv/PciSearch.srv"
  "srv/PciGlobal.srv"
  "srv/PciStop.srv"
  "srv/PciGeofence.srv"
  "srv/PlannerSetGlobalBound.srv"
  "srv/PlannerSetVel.srv"
  "srv/PlannerSetExpMode.srv"
  "srv/PlannerStringTrigger.srv"
  "srv/PlannerSetSearchMode.srv"
  "srv/PlannerGoToWaypoint.srv"
  "srv/PlannerDynamicGlobalBound.srv"
  "srv/PlannerSetPlanningMode.srv"
)

set(action_files
  "action/PathFollower.action"
)

rosidl_generate_interfaces(${PROJECT_NAME}
  ${msg_files}
  ${srv_files}
  ${action_files}
  DEPENDENCIES
    geometry_msgs
    std_msgs
)

install(DIRECTORY include/
  DESTINATION include
)

ament_export_include_directories(include)
ament_export_dependencies(rosidl_default_runtime)

ament_package()
