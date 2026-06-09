#include <gazebo/common/common.hh>
#include <gazebo/gazebo.hh>
#include <gazebo/physics/physics.hh>

#include <geometry_msgs/msg/pose_stamped.hpp>
#include <geometry_msgs/msg/transform_stamped.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rosgraph_msgs/msg/clock.hpp>
#include <tf2/LinearMath/Matrix3x3.h>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2_ros/transform_broadcaster.h>

#include <atomic>
#include <cmath>
#include <string>
#include <thread>
#include <vector>

namespace gazebo
{

class CubeRobotWorldPosePlugin : public ModelPlugin
{
public:
  static double NormalizeAngle(double angle)
  {
    while (angle > M_PI) angle -= 2.0 * M_PI;
    while (angle < -M_PI) angle += 2.0 * M_PI;
    return angle;
  }

  physics::LinkPtr ResolveSensorLink(const std::string &preferred_name)
  {
    std::vector<std::string> candidates;
    if (!preferred_name.empty())
    {
      candidates.push_back(preferred_name);
    }
    candidates.push_back("livox_mount_link");
    candidates.push_back("livox");
    candidates.push_back("livox_yaw_link");

    for (const auto &candidate : candidates)
    {
      auto link = model_->GetLink(candidate);
      if (link)
      {
        if (candidate != preferred_name)
        {
          gzmsg << "[tf_pub] Sensor link fallback: requested [" << preferred_name
                << "], using [" << candidate << "]" << std::endl;
        }
        resolved_sensor_link_name_ = candidate;
        return link;
      }
    }

    gzerr << "[tf_pub] Cannot find sensor link. Tried:";
    for (const auto &candidate : candidates)
    {
      gzerr << " " << candidate;
    }
    gzerr << std::endl;

    return nullptr;
  }

  void Load(physics::ModelPtr model, sdf::ElementPtr sdf) override
  {
    model_ = model;

    if (!model_)
    {
      gzerr << "[tf_pub] model is null" << std::endl;
      return;
    }

    expected_model_name_ = model_->GetName();
    if (sdf && sdf->HasElement("expected_model_name"))
    {
      expected_model_name_ = sdf->Get<std::string>("expected_model_name");
    }
    if (model_->GetName() != expected_model_name_)
    {
      gzerr << "[tf_pub] Wrong model: " << model_->GetName()
            << ", expected: " << expected_model_name_ << std::endl;
      return;
    }

    publish_nav_odom_ = true;
    if (sdf && sdf->HasElement("publish_nav_odom"))
    {
      publish_nav_odom_ = sdf->Get<bool>("publish_nav_odom");
    }

    publish_legacy_odom_ = true;
    if (sdf && sdf->HasElement("publish_legacy_odom"))
    {
      publish_legacy_odom_ = sdf->Get<bool>("publish_legacy_odom");
    }

    enable_livox_yaw_follow_ = false;
    if (sdf && sdf->HasElement("enable_livox_yaw_follow"))
    {
      enable_livox_yaw_follow_ = sdf->Get<bool>("enable_livox_yaw_follow");
    }

    publish_livox_world_pose_ = true;
    if (sdf && sdf->HasElement("publish_livox_world_pose"))
    {
      publish_livox_world_pose_ = sdf->Get<bool>("publish_livox_world_pose");
    }

    livox_fixed_pitch_deg_ = 0.0;
    if (sdf && sdf->HasElement("livox_fixed_pitch_deg"))
    {
      livox_fixed_pitch_deg_ = sdf->Get<double>("livox_fixed_pitch_deg");
    }

    livox_yaw_joint_name_ = "livox_yaw_joint";
    if (sdf && sdf->HasElement("livox_yaw_joint_name"))
    {
      livox_yaw_joint_name_ = sdf->Get<std::string>("livox_yaw_joint_name");
    }

    livox_link_name_ = "livox";
    if (sdf && sdf->HasElement("livox_link_name"))
    {
      livox_link_name_ = sdf->Get<std::string>("livox_link_name");
    }

    livox_speed_heading_threshold_ = 0.05;
    if (sdf && sdf->HasElement("livox_speed_heading_threshold"))
    {
      livox_speed_heading_threshold_ = sdf->Get<double>("livox_speed_heading_threshold");
    }

    if (!rclcpp::ok())
    {
      int argc = 0;
      char **argv = nullptr;
      rclcpp::init(argc, argv);
    }

    ros_node_ = std::make_shared<rclcpp::Node>("cube_robot_world_pose_plugin");
    if (!ros_node_->has_parameter("use_sim_time"))
    {
      ros_node_->declare_parameter<bool>("use_sim_time", true);
    }
    ros_node_->set_parameter(rclcpp::Parameter("use_sim_time", true));

    pose_pub_ = ros_node_->create_publisher<geometry_msgs::msg::PoseStamped>(
      "/cube_robot/world_pose", 10);

    if (publish_livox_world_pose_)
    {
      livox_pose_pub_ = ros_node_->create_publisher<geometry_msgs::msg::PoseStamped>(
        "/livox/world_pose", 10);
    }

    clock_sub_ = ros_node_->create_subscription<rosgraph_msgs::msg::Clock>(
      "/clock",
      rclcpp::ClockQoS(),
      [this](const rosgraph_msgs::msg::Clock::SharedPtr msg)
      {
        const auto stamp_ns =
          static_cast<int64_t>(msg->clock.sec) * 1000000000LL + msg->clock.nanosec;
        latest_clock_ns_.store(stamp_ns, std::memory_order_relaxed);
        clock_msg_received_.store(true, std::memory_order_release);
      });

    nav_odom_topic_ = "/nav_odom";
    if (sdf && sdf->HasElement("nav_odom_topic"))
    {
      nav_odom_topic_ = sdf->Get<std::string>("nav_odom_topic");
    }

    legacy_odom_topic_ = "/odom";
    if (sdf && sdf->HasElement("legacy_odom_topic"))
    {
      legacy_odom_topic_ = sdf->Get<std::string>("legacy_odom_topic");
    }

    if (publish_nav_odom_)
    {
      nav_odom_pub_ = ros_node_->create_publisher<nav_msgs::msg::Odometry>(nav_odom_topic_, 10);
      tf_broadcaster_ = std::make_shared<tf2_ros::TransformBroadcaster>(ros_node_);
    }

    if (publish_legacy_odom_)
    {
      legacy_odom_pub_ = ros_node_->create_publisher<nav_msgs::msg::Odometry>(
        legacy_odom_topic_, 10);
    }

    if (enable_livox_yaw_follow_)
    {
      livox_yaw_joint_ = model_->GetJoint(livox_yaw_joint_name_);
      if (!livox_yaw_joint_)
      {
        gzerr << "[tf_pub] Cannot find joint: " << livox_yaw_joint_name_ << std::endl;
        enable_livox_yaw_follow_ = false;
      }
    }

    if (publish_livox_world_pose_)
    {
      livox_link_ = ResolveSensorLink(livox_link_name_);
      if (!livox_link_)
      {
        gzerr << "[tf_pub] Sensor world pose publishing disabled" << std::endl;
        publish_livox_world_pose_ = false;
      }
      else if (resolved_sensor_link_name_ == "livox_yaw_link")
      {
        sensor_pose_in_link_ = ignition::math::Pose3d(
          0.0,
          0.0,
          0.0,
          0.0,
          livox_fixed_pitch_deg_ * M_PI / 180.0,
          0.0);
        gzmsg << "[tf_pub] Applying fixed sensor pitch to livox_yaw_link fallback"
              << std::endl;
      }
    }

    executor_ = std::make_shared<rclcpp::executors::SingleThreadedExecutor>();
    executor_->add_node(ros_node_);
    spin_thread_ = std::thread([this]() { executor_->spin(); });

    update_connection_ = event::Events::ConnectWorldUpdateBegin(
      std::bind(&CubeRobotWorldPosePlugin::OnUpdate, this));

    gzmsg << "[tf_pub] CubeRobotWorldPosePlugin loaded, waiting for /clock..." << std::endl;
  }

  void OnUpdate()
  {
    if (!ros_node_)
    {
      return;
    }

    if (!clock_msg_received_.load(std::memory_order_acquire))
    {
      if (!warned_no_clock_)
      {
        RCLCPP_WARN(
          ros_node_->get_logger(),
          "[tf_pub] /clock not ready yet, suppressing odom/TF publish");
        warned_no_clock_ = true;
      }
      return;
    }

    const auto stamp_ns = latest_clock_ns_.load(std::memory_order_relaxed);
    if (stamp_ns <= 0)
    {
      if (!warned_no_clock_)
      {
        RCLCPP_WARN(
          ros_node_->get_logger(),
          "[tf_pub] /clock not ready yet, suppressing odom/TF publish");
        warned_no_clock_ = true;
      }
      return;
    }
    warned_no_clock_ = false;

    const rclcpp::Time stamp(stamp_ns, RCL_ROS_TIME);
    if (has_last_stamp_ && stamp < last_stamp_)
    {
      if (!warned_clock_backwards_)
      {
        RCLCPP_WARN(
          ros_node_->get_logger(),
          "[tf_pub] sim time moved backwards (now=%.3f, last=%.3f); suppressing stale odom/TF",
          stamp.seconds(),
          last_stamp_.seconds());
        warned_clock_backwards_ = true;
      }
      last_stamp_ = stamp;
      return;
    }

    if (has_last_stamp_ && stamp == last_stamp_)
    {
      return;
    }

    warned_clock_backwards_ = false;
    last_stamp_ = stamp;
    has_last_stamp_ = true;

    if (!clock_ready_)
    {
      RCLCPP_INFO(
        ros_node_->get_logger(),
        "[tf_pub] sim time ready, start publishing odom/TF");
      clock_ready_ = true;
    }

    ignition::math::Pose3d pose = model_->WorldPose();

    geometry_msgs::msg::PoseStamped pose_msg;
    pose_msg.header.stamp = stamp;
    pose_msg.header.frame_id = "world";
    pose_msg.pose.position.x = pose.Pos().X();
    pose_msg.pose.position.y = pose.Pos().Y();
    pose_msg.pose.position.z = pose.Pos().Z();
    pose_msg.pose.orientation.x = pose.Rot().X();
    pose_msg.pose.orientation.y = pose.Rot().Y();
    pose_msg.pose.orientation.z = pose.Rot().Z();
    pose_msg.pose.orientation.w = pose.Rot().W();
    pose_pub_->publish(pose_msg);

    tf2::Quaternion q_world_base(
      pose_msg.pose.orientation.x,
      pose_msg.pose.orientation.y,
      pose_msg.pose.orientation.z,
      pose_msg.pose.orientation.w);
    double roll = 0.0;
    double pitch = 0.0;
    double yaw = 0.0;
    tf2::Matrix3x3(q_world_base).getRPY(roll, pitch, yaw);

    tf2::Quaternion q_planar;
    q_planar.setRPY(0.0, 0.0, yaw);

    auto linear_vel = model_->WorldLinearVel();
    auto angular_vel = model_->WorldAngularVel();
    const double planar_speed = std::hypot(linear_vel.X(), linear_vel.Y());
    const double cos_yaw = std::cos(yaw);
    const double sin_yaw = std::sin(yaw);

    if (enable_livox_yaw_follow_ && livox_yaw_joint_)
    {
      if (planar_speed >= livox_speed_heading_threshold_)
      {
        const double velocity_heading = std::atan2(linear_vel.Y(), linear_vel.X());
        const double relative_sensor_yaw = NormalizeAngle(velocity_heading - yaw);
        livox_yaw_joint_->SetPosition(0, relative_sensor_yaw);
        last_livox_relative_yaw_ = relative_sensor_yaw;
        has_last_livox_relative_yaw_ = true;
      }
      else if (has_last_livox_relative_yaw_)
      {
        livox_yaw_joint_->SetPosition(0, last_livox_relative_yaw_);
      }
    }

    if (publish_nav_odom_ && nav_odom_pub_)
    {
      nav_msgs::msg::Odometry odom_msg;
      odom_msg.header.stamp = stamp;
      odom_msg.header.frame_id = "odom";
      odom_msg.child_frame_id = "base_footprint";
      odom_msg.pose.pose.position.x = pose.Pos().X();
      odom_msg.pose.pose.position.y = pose.Pos().Y();
      odom_msg.pose.pose.position.z = 0.0;
      odom_msg.pose.pose.orientation.x = q_planar.x();
      odom_msg.pose.pose.orientation.y = q_planar.y();
      odom_msg.pose.pose.orientation.z = q_planar.z();
      odom_msg.pose.pose.orientation.w = q_planar.w();
      odom_msg.twist.twist.linear.x =
        cos_yaw * linear_vel.X() + sin_yaw * linear_vel.Y();
      odom_msg.twist.twist.linear.y =
        -sin_yaw * linear_vel.X() + cos_yaw * linear_vel.Y();
      odom_msg.twist.twist.linear.z = 0.0;
      odom_msg.twist.twist.angular.x = 0.0;
      odom_msg.twist.twist.angular.y = 0.0;
      odom_msg.twist.twist.angular.z = angular_vel.Z();
      nav_odom_pub_->publish(odom_msg);

      if (tf_broadcaster_)
      {
        geometry_msgs::msg::TransformStamped tf_msg;
        tf_msg.header.stamp = stamp;
        tf_msg.header.frame_id = "odom";
        tf_msg.child_frame_id = "base_footprint";
        tf_msg.transform.translation.x = pose.Pos().X();
        tf_msg.transform.translation.y = pose.Pos().Y();
        tf_msg.transform.translation.z = 0.0;
        tf_msg.transform.rotation.x = q_planar.x();
        tf_msg.transform.rotation.y = q_planar.y();
        tf_msg.transform.rotation.z = q_planar.z();
        tf_msg.transform.rotation.w = q_planar.w();
        tf_broadcaster_->sendTransform(tf_msg);
      }
    }

    if (publish_legacy_odom_ && legacy_odom_pub_)
    {
      nav_msgs::msg::Odometry legacy_odom_msg;
      legacy_odom_msg.header.stamp = stamp;
      legacy_odom_msg.header.frame_id = "world";
      legacy_odom_msg.child_frame_id = "base_link";
      legacy_odom_msg.pose.pose = pose_msg.pose;
      legacy_odom_msg.twist.twist.linear.x = linear_vel.X();
      legacy_odom_msg.twist.twist.linear.y = linear_vel.Y();
      legacy_odom_msg.twist.twist.linear.z = linear_vel.Z();
      legacy_odom_msg.twist.twist.angular.x = angular_vel.X();
      legacy_odom_msg.twist.twist.angular.y = angular_vel.Y();
      legacy_odom_msg.twist.twist.angular.z = angular_vel.Z();
      legacy_odom_pub_->publish(legacy_odom_msg);
    }

    if (publish_livox_world_pose_ && livox_link_ && livox_pose_pub_)
    {
      const ignition::math::Pose3d livox_pose =
        livox_link_->WorldPose() + sensor_pose_in_link_;
      geometry_msgs::msg::PoseStamped livox_pose_msg;
      livox_pose_msg.header.stamp = stamp;
      livox_pose_msg.header.frame_id = "world";
      livox_pose_msg.pose.position.x = livox_pose.Pos().X();
      livox_pose_msg.pose.position.y = livox_pose.Pos().Y();
      livox_pose_msg.pose.position.z = livox_pose.Pos().Z();
      livox_pose_msg.pose.orientation.x = livox_pose.Rot().X();
      livox_pose_msg.pose.orientation.y = livox_pose.Rot().Y();
      livox_pose_msg.pose.orientation.z = livox_pose.Rot().Z();
      livox_pose_msg.pose.orientation.w = livox_pose.Rot().W();
      livox_pose_pub_->publish(livox_pose_msg);
    }
  }

  ~CubeRobotWorldPosePlugin() override
  {
    if (executor_)
    {
      executor_->cancel();
    }
    if (spin_thread_.joinable())
    {
      spin_thread_.join();
    }
  }

private:
  physics::ModelPtr model_;
  event::ConnectionPtr update_connection_;

  rclcpp::Node::SharedPtr ros_node_;
  rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr pose_pub_;
  rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr livox_pose_pub_;
  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr nav_odom_pub_;
  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr legacy_odom_pub_;
  rclcpp::Subscription<rosgraph_msgs::msg::Clock>::SharedPtr clock_sub_;
  std::shared_ptr<tf2_ros::TransformBroadcaster> tf_broadcaster_;
  std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor_;
  std::thread spin_thread_;

  std::atomic<bool> clock_ready_{false};
  std::atomic<bool> clock_msg_received_{false};
  std::atomic<bool> warned_no_clock_{false};
  std::atomic<bool> warned_clock_backwards_{false};
  std::atomic<int64_t> latest_clock_ns_{0};

  bool publish_nav_odom_{true};
  bool publish_legacy_odom_{true};
  bool publish_livox_world_pose_{false};
  bool enable_livox_yaw_follow_{false};
  std::string expected_model_name_{"cube_robot"};
  std::string nav_odom_topic_{"/nav_odom"};
  std::string legacy_odom_topic_{"/odom"};
  std::string livox_yaw_joint_name_{"livox_yaw_joint"};
  std::string livox_link_name_{"livox"};
  std::string resolved_sensor_link_name_;
  double livox_speed_heading_threshold_{0.05};
  double livox_fixed_pitch_deg_{0.0};
  physics::JointPtr livox_yaw_joint_;
  physics::LinkPtr livox_link_;
  ignition::math::Pose3d sensor_pose_in_link_{ignition::math::Pose3d::Zero};
  double last_livox_relative_yaw_{0.0};
  bool has_last_livox_relative_yaw_{false};

  rclcpp::Time last_stamp_{0, 0, RCL_ROS_TIME};
  bool has_last_stamp_{false};
};

GZ_REGISTER_MODEL_PLUGIN(CubeRobotWorldPosePlugin)

}  // namespace gazebo
