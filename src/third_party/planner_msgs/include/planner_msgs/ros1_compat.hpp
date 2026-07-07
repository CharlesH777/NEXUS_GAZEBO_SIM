#pragma once

#include "planner_msgs/action/path_follower.hpp"
#include "planner_msgs/msg/behaviour_planner_logger.hpp"
#include "planner_msgs/msg/bound_mode.hpp"
#include "planner_msgs/msg/coverage_planner_logger.hpp"
#include "planner_msgs/msg/edge.hpp"
#include "planner_msgs/msg/execution_path_mode.hpp"
#include "planner_msgs/msg/graph.hpp"
#include "planner_msgs/msg/planner_status.hpp"
#include "planner_msgs/msg/planning_bound.hpp"
#include "planner_msgs/msg/planning_mode.hpp"
#include "planner_msgs/msg/rectangle_shape.hpp"
#include "planner_msgs/msg/robot_status.hpp"
#include "planner_msgs/msg/trigger_mode.hpp"
#include "planner_msgs/msg/vertex.hpp"
#include "planner_msgs/srv/pci_geofence.hpp"
#include "planner_msgs/srv/pci_global.hpp"
#include "planner_msgs/srv/pci_homing_trigger.hpp"
#include "planner_msgs/srv/pci_initialization.hpp"
#include "planner_msgs/srv/pci_search.hpp"
#include "planner_msgs/srv/pci_set_homing_pos.hpp"
#include "planner_msgs/srv/pci_stop.hpp"
#include "planner_msgs/srv/pci_trigger.hpp"
#include "planner_msgs/srv/planner_dynamic_global_bound.hpp"
#include "planner_msgs/srv/planner_geofence.hpp"
#include "planner_msgs/srv/planner_global.hpp"
#include "planner_msgs/srv/planner_go_to_waypoint.hpp"
#include "planner_msgs/srv/planner_homing.hpp"
#include "planner_msgs/srv/planner_request_path.hpp"
#include "planner_msgs/srv/planner_search.hpp"
#include "planner_msgs/srv/planner_set_exp_mode.hpp"
#include "planner_msgs/srv/planner_set_global_bound.hpp"
#include "planner_msgs/srv/planner_set_homing_pos.hpp"
#include "planner_msgs/srv/planner_set_planning_mode.hpp"
#include "planner_msgs/srv/planner_set_search_mode.hpp"
#include "planner_msgs/srv/planner_set_vel.hpp"
#include "planner_msgs/srv/planner_srv.hpp"
#include "planner_msgs/srv/planner_string_trigger.hpp"

namespace planner_msgs {

using BehaviourPlannerLogger = msg::BehaviourPlannerLogger;
using BoundMode = msg::BoundMode;
using CoveragePlannerLogger = msg::CoveragePlannerLogger;
using Edge = msg::Edge;
using ExecutionPathMode = msg::ExecutionPathMode;
using Graph = msg::Graph;
using PlannerStatus = msg::PlannerStatus;
using PlanningBound = msg::PlanningBound;
using PlanningMode = msg::PlanningMode;
using RectangleShape = msg::RectangleShape;
using RobotStatus = msg::RobotStatus;
using TriggerMode = msg::TriggerMode;
using Vertex = msg::Vertex;

using pathFollowerAction = action::PathFollower;

using pci_geofence = srv::PciGeofence;
using pci_global = srv::PciGlobal;
using pci_homing_trigger = srv::PciHomingTrigger;
using pci_initialization = srv::PciInitialization;
using pci_search = srv::PciSearch;
using pci_set_homing_pos = srv::PciSetHomingPos;
using pci_stop = srv::PciStop;
using pci_trigger = srv::PciTrigger;
using planner_dynamic_global_bound = srv::PlannerDynamicGlobalBound;
using planner_geofence = srv::PlannerGeofence;
using planner_global = srv::PlannerGlobal;
using planner_go_to_waypoint = srv::PlannerGoToWaypoint;
using planner_homing = srv::PlannerHoming;
using planner_request_path = srv::PlannerRequestPath;
using planner_search = srv::PlannerSearch;
using planner_set_exp_mode = srv::PlannerSetExpMode;
using planner_set_global_bound = srv::PlannerSetGlobalBound;
using planner_set_homing_pos = srv::PlannerSetHomingPos;
using planner_set_planning_mode = srv::PlannerSetPlanningMode;
using planner_set_search_mode = srv::PlannerSetSearchMode;
using planner_set_vel = srv::PlannerSetVel;
using planner_srv = srv::PlannerSrv;
using planner_string_trigger = srv::PlannerStringTrigger;

}  // namespace planner_msgs
