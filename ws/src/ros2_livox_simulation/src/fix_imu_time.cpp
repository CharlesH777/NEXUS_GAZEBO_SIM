#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <geometry_msgs/msg/quaternion.hpp>

#include <cmath>
#include <string>

using sensor_msgs::msg::Imu;

class FixImuTime : public rclcpp::Node
{
public:
  FixImuTime()
  : Node("fix_imu_time")
  {
    input_topic_ = this->declare_parameter<std::string>("input_topic", "/livox/imu");
    output_topic_ = this->declare_parameter<std::string>("output_topic", "/imu_fixed");
    timestamp_offset_sec_ = this->declare_parameter<double>("timestamp_offset_sec", 0.0);
    apply_rotation_ = this->declare_parameter<bool>("apply_rotation", false);
    rotation_pitch_deg_ = this->declare_parameter<double>("rotation_pitch_deg", 0.0);

    double theta = rotation_pitch_deg_ * M_PI / 180.0;
    cos_t_ = std::cos(theta);
    sin_t_ = std::sin(theta);

    auto imu_qos = rclcpp::QoS(rclcpp::KeepLast(200)).reliable();

    sub_ = this->create_subscription<Imu>(
      input_topic_,
      imu_qos,
      std::bind(&FixImuTime::cb, this, std::placeholders::_1));

    pub_ = this->create_publisher<Imu>(
      output_topic_,
      imu_qos);

    RCLCPP_INFO(
      this->get_logger(),
      "FixImuTime started: %s -> %s, timestamp_offset_sec=%.3f, apply_rotation=%s, rotation_pitch_deg=%.1f",
      input_topic_.c_str(),
      output_topic_.c_str(),
      timestamp_offset_sec_,
      apply_rotation_ ? "true" : "false",
      rotation_pitch_deg_);
  }

private:
  void cb(const Imu::SharedPtr msg)
  {
    Imu out = *msg;

    if (std::abs(timestamp_offset_sec_) > 1e-9) {
      rclcpp::Time t(msg->header.stamp);
      t = t + rclcpp::Duration::from_seconds(timestamp_offset_sec_);
      out.header.stamp = t;
    }

    if (apply_rotation_) {
      rotate_vec(
        out.angular_velocity.x,
        out.angular_velocity.y,
        out.angular_velocity.z
      );

      rotate_vec(
        out.linear_acceleration.x,
        out.linear_acceleration.y,
        out.linear_acceleration.z
      );

      rotate_quaternion(out.orientation);
    }

    pub_->publish(out);
  }

  // ===== 绕 Y 轴旋转向量 =====
  inline void rotate_vec(double &x, double &y, double &z)
  {
    double x_new =  cos_t_ * x + sin_t_ * z;
    double z_new = -sin_t_ * x + cos_t_ * z;
    x = x_new;
    z = z_new;
    // y 不变
  }

  // ===== 绕 Y 轴旋转四元数 =====
  void rotate_quaternion(geometry_msgs::msg::Quaternion &q)
  {
    double half = (rotation_pitch_deg_ * M_PI / 180.0) * 0.5;
    double sr = std::sin(half);
    double cr = std::cos(half);

    geometry_msgs::msg::Quaternion r;
    r.x = 0.0;
    r.y = sr;
    r.z = 0.0;
    r.w = cr;

    geometry_msgs::msg::Quaternion res;
    res.w = r.w*q.w - r.x*q.x - r.y*q.y - r.z*q.z;
    res.x = r.w*q.x + r.x*q.w + r.y*q.z - r.z*q.y;
    res.y = r.w*q.y - r.x*q.z + r.y*q.w + r.z*q.x;
    res.z = r.w*q.z + r.x*q.y - r.y*q.x + r.z*q.w;

    q = res;
  }

  rclcpp::Subscription<Imu>::SharedPtr sub_;
  rclcpp::Publisher<Imu>::SharedPtr pub_;
  std::string input_topic_;
  std::string output_topic_;
  double timestamp_offset_sec_;
  bool apply_rotation_;
  double rotation_pitch_deg_;

  double cos_t_;
  double sin_t_;
};

int main(int argc, char **argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<FixImuTime>());
  rclcpp::shutdown();
  return 0;
}
