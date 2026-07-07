#include <gazebo/common/common.hh>
#include <gazebo/common/Events.hh>
#include <gazebo/gazebo.hh>
#include <gazebo/msgs/msgs.hh>
#include <gazebo/physics/physics.hh>
#include <gazebo/transport/transport.hh>

#include <ignition/math/Color.hh>
#include <ignition/math/Pose3.hh>
#include <ignition/math/Vector3.hh>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp/executors/single_threaded_executor.hpp>
#include <std_msgs/msg/float32.hpp>

#include <atomic>
#include <cmath>
#include <cstdio>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <thread>

namespace gazebo
{

class SolarLightingWorldPlugin : public WorldPlugin
{
public:
  static constexpr double kPi = 3.14159265358979323846;

  ~SolarLightingWorldPlugin() override
  {
    world_update_connection_.reset();
    if (executor_) {
      executor_->cancel();
    }
    if (executor_thread_.joinable()) {
      executor_thread_.join();
    }
  }

  void Load(physics::WorldPtr world, sdf::ElementPtr sdf) override
  {
    world_ = world;
    if (!world_) {
      gzerr << "[solar_light] world is null" << std::endl;
      return;
    }

    light_name_ = "map_sim_sun";
    if (sdf && sdf->HasElement("light_name")) {
      light_name_ = sdf->Get<std::string>("light_name");
    }

    topic_name_ = "/map_sim/solar_time_hours";
    if (sdf && sdf->HasElement("topic_name")) {
      topic_name_ = sdf->Get<std::string>("topic_name");
    }

    initial_time_hours_ = 12.0;
    if (sdf && sdf->HasElement("initial_time_hours")) {
      initial_time_hours_ = sdf->Get<double>("initial_time_hours");
    }
    initial_time_hours_ = NormalizeHours(initial_time_hours_);

    if (!rclcpp::ok()) {
      int argc = 0;
      char ** argv = nullptr;
      rclcpp::init(argc, argv);
    }

    ros_node_ = std::make_shared<rclcpp::Node>("map_sim_solar_lighting");
    if (!ros_node_->has_parameter("use_sim_time")) {
      ros_node_->declare_parameter<bool>("use_sim_time", true);
    }
    ros_node_->set_parameter(rclcpp::Parameter("use_sim_time", true));

    solar_time_sub_ = ros_node_->create_subscription<std_msgs::msg::Float32>(
      topic_name_,
      10,
      [this](const std_msgs::msg::Float32::SharedPtr msg) {
        QueueSolarTimeHours(static_cast<double>(msg->data));
      });

    gazebo_node_ = transport::NodePtr(new transport::Node());
    gazebo_node_->Init(world_->Name());
    light_pub_ = gazebo_node_->Advertise<msgs::Light>("~/light/modify");

    executor_ = std::make_shared<rclcpp::executors::SingleThreadedExecutor>();
    executor_->add_node(ros_node_);
    executor_thread_ = std::thread([this]() {
      executor_->spin();
    });

    world_update_connection_ = event::Events::ConnectWorldUpdateBegin(
      std::bind(&SolarLightingWorldPlugin::OnWorldUpdate, this));
    QueueSolarTimeHours(initial_time_hours_);
    gzmsg << "[solar_light] realtime solar lighting ready:"
          << " topic=" << topic_name_
          << " initial=" << FormatTime(initial_time_hours_)
          << " frame=+X east,-X west,+Y north,+Z up"
          << std::endl;
  }

private:
  struct SolarState
  {
    ignition::math::Vector3d direction;
    ignition::math::Color diffuse;
    ignition::math::Color specular;
    bool cast_shadows{true};
  };

  static double NormalizeHours(double hours)
  {
    double wrapped = std::fmod(hours, 24.0);
    if (wrapped < 0.0) {
      wrapped += 24.0;
    }
    return wrapped;
  }

  static double Clamp01(double value)
  {
    return std::max(0.0, std::min(1.0, value));
  }

  static double Lerp(double left, double right, double t)
  {
    return left + (right - left) * t;
  }

  static ignition::math::Color MixColor(
    const ignition::math::Color & left,
    const ignition::math::Color & right,
    double t)
  {
    t = Clamp01(t);
    return ignition::math::Color(
      Lerp(left.R(), right.R(), t),
      Lerp(left.G(), right.G(), t),
      Lerp(left.B(), right.B(), t),
      Lerp(left.A(), right.A(), t));
  }

  static ignition::math::Color ScaleColor(
    const ignition::math::Color & color,
    double scale)
  {
    return ignition::math::Color(
      Clamp01(color.R() * scale),
      Clamp01(color.G() * scale),
      Clamp01(color.B() * scale),
      Clamp01(color.A()));
  }

  static std::string FormatTime(double hours)
  {
    const int total_minutes = static_cast<int>(std::round(NormalizeHours(hours) * 60.0)) % (24 * 60);
    const int hh = total_minutes / 60;
    const int mm = total_minutes % 60;
    char buffer[6];
    std::snprintf(buffer, sizeof(buffer), "%02d:%02d", hh, mm);
    return std::string(buffer);
  }

  static SolarState BuildSolarState(double hours)
  {
    const double normalized = NormalizeHours(hours);
    const double hour_angle = (normalized - 12.0) * kPi / 12.0;
    const double sun_east = -std::sin(hour_angle);
    const double sun_up = std::cos(hour_angle);
    const double above_horizon = std::max(0.0, sun_up);
    const double sun_level = std::pow(above_horizon, 0.85);
    const double warmth = Clamp01(1.0 - above_horizon * 2.5);
    const ignition::math::Color day_diffuse(1.0, 0.98, 0.94, 1.0);
    const ignition::math::Color warm_diffuse(1.0, 0.72, 0.45, 1.0);
    const ignition::math::Color day_specular(0.28, 0.28, 0.28, 1.0);
    const ignition::math::Color warm_specular(0.36, 0.25, 0.18, 1.0);

    SolarState state;
    state.direction = ignition::math::Vector3d(-sun_east, 0.0, -sun_up);
    state.diffuse = ScaleColor(MixColor(day_diffuse, warm_diffuse, warmth), sun_level);
    state.specular = ScaleColor(MixColor(day_specular, warm_specular, warmth), sun_level);
    state.cast_shadows = above_horizon > 0.05;
    return state;
  }

  void QueueSolarTimeHours(double hours)
  {
    std::lock_guard<std::mutex> guard(state_mutex_);
    pending_hours_ = NormalizeHours(hours);
  }

  void OnWorldUpdate()
  {
    std::optional<double> pending_hours;
    {
      std::lock_guard<std::mutex> guard(state_mutex_);
      pending_hours.swap(pending_hours_);
    }

    if (!pending_hours.has_value()) {
      return;
    }

    const double normalized = NormalizeHours(*pending_hours);
    if (last_applied_hours_.has_value() &&
        std::fabs(*last_applied_hours_ - normalized) < 1e-6) {
      return;
    }

    if (!light_pub_) {
      return;
    }

    const SolarState state = BuildSolarState(normalized);

    msgs::Light light_msg;
    light_msg.set_name(light_name_);
    light_msg.set_type(msgs::Light::DIRECTIONAL);
    msgs::Set(light_msg.mutable_pose(), ignition::math::Pose3d(0.0, 0.0, 120.0, 0.0, 0.0, 0.0));
    msgs::Set(light_msg.mutable_diffuse(), state.diffuse);
    msgs::Set(light_msg.mutable_specular(), state.specular);
    msgs::Set(light_msg.mutable_direction(), state.direction);
    light_msg.set_cast_shadows(state.cast_shadows);
    light_pub_->Publish(light_msg);
    last_applied_hours_ = normalized;
  }

  physics::WorldPtr world_;
  std::string light_name_;
  std::string topic_name_;
  double initial_time_hours_{12.0};
  std::mutex state_mutex_;
  std::optional<double> pending_hours_;
  std::optional<double> last_applied_hours_;

  rclcpp::Node::SharedPtr ros_node_;
  rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr solar_time_sub_;
  std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor_;
  std::thread executor_thread_;
  event::ConnectionPtr world_update_connection_;

  transport::NodePtr gazebo_node_;
  transport::PublisherPtr light_pub_;
};

GZ_REGISTER_WORLD_PLUGIN(SolarLightingWorldPlugin)

}  // namespace gazebo
