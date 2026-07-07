#include <gflags/gflags.h>
#include <glog/logging.h>

#include "planner_common/ros1_compat.hpp"
#include "gbplanner/gbplanner.h"

int main(int argc, char** argv) {
  google::InitGoogleLogging(argv[0]);
  google::InstallFailureSignalHandler();
  google::ParseCommandLineFlags(&argc, &argv, false);

  ros::init(argc, argv, "gbplanner_node");
  ros::NodeHandle nh;
  ros::NodeHandle nh_private("~");

  explorer::Gbplanner planner(nh, nh_private);

  if (ros::ok()) {
    ros::spin();
  }

  return 0;
}
