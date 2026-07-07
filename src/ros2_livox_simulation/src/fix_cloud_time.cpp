#include <rclcpp/rclcpp.hpp>

#include <geometry_msgs/msg/pose_stamped.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>

#include <Eigen/Core>
#include <Eigen/Geometry>

#include <algorithm>
#include <cmath>
#include <cstring>
#include <deque>
#include <mutex>
#include <string>

using geometry_msgs::msg::PoseStamped;
using sensor_msgs::msg::PointCloud2;

class LidarToWorld : public rclcpp::Node
{
public:
  LidarToWorld()
  : Node("lidar_to_world")
  {
    input_topic_ = this->declare_parameter<std::string>(
      "input_topic", "/livox/lidar_PointCloud2");
    base_pose_topic_ = this->declare_parameter<std::string>(
      "base_pose_topic", "/cube_robot/world_pose");
    sensor_pose_topic_ = this->declare_parameter<std::string>(
      "sensor_pose_topic", "/livox/world_pose");
    world_topic_ = this->declare_parameter<std::string>("world_topic", "");
    body_topic_ = this->declare_parameter<std::string>("body_topic", "");
    body_frame_id_ = this->declare_parameter<std::string>("body_frame_id", "base_link");
    world_frame_id_ = this->declare_parameter<std::string>("world_frame_id", "world");

    use_dynamic_sensor_pose_ = this->declare_parameter<bool>(
      "use_dynamic_sensor_pose", false);
    require_dynamic_sensor_pose_ = this->declare_parameter<bool>(
      "require_dynamic_sensor_pose", false);
    sensor_offset_x_ = this->declare_parameter<double>("sensor_offset_x", 0.0);
    sensor_offset_y_ = this->declare_parameter<double>("sensor_offset_y", 0.0);
    sensor_offset_z_ = this->declare_parameter<double>("sensor_offset_z", 0.4);
    sensor_pitch_deg_ = this->declare_parameter<double>("sensor_pitch_deg", 30.0);
    world_downsample_stride_ = std::max<int>(
      1,
      this->declare_parameter<int>("world_downsample_stride", 3));
    pose_time_tolerance_sec_ = this->declare_parameter<double>("pose_time_tolerance_sec", 0.10);
    time_sync_warn_interval_sec_ = this->declare_parameter<double>("time_sync_warn_interval_sec", 2.0);
    dynamic_pose_fallback_warn_interval_sec_ = this->declare_parameter<double>(
      "dynamic_pose_fallback_warn_interval_sec", 5.0);

    auto qos = rclcpp::SensorDataQoS().reliable();

    cloud_sub_ = this->create_subscription<PointCloud2>(
      input_topic_,
      qos,
      std::bind(&LidarToWorld::cloudCb, this, std::placeholders::_1));

    base_pose_sub_ = this->create_subscription<PoseStamped>(
      base_pose_topic_,
      50,
      std::bind(&LidarToWorld::basePoseCb, this, std::placeholders::_1));

    if (use_dynamic_sensor_pose_)
    {
      sensor_pose_sub_ = this->create_subscription<PoseStamped>(
        sensor_pose_topic_,
        50,
        std::bind(&LidarToWorld::sensorPoseCb, this, std::placeholders::_1));
    }

    if (!world_topic_.empty())
    {
      cloud_pub_ = this->create_publisher<PointCloud2>(world_topic_, qos);
    }
    if (!body_topic_.empty())
    {
      cloud_body_pub_ = this->create_publisher<PointCloud2>(body_topic_, qos);
    }

    const double theta = sensor_pitch_deg_ * M_PI / 180.0;
    R_bs_static_ = Eigen::AngleAxisd(theta, Eigen::Vector3d::UnitY()).toRotationMatrix();
    t_bs_static_ = Eigen::Vector3d(sensor_offset_x_, sensor_offset_y_, sensor_offset_z_);

    if (use_dynamic_sensor_pose_)
    {
      RCLCPP_INFO(
        this->get_logger(),
        "LidarToWorld started (dynamic sensor pose: %s + %s, required=%s)",
        sensor_pose_topic_.c_str(),
        base_pose_topic_.c_str(),
        require_dynamic_sensor_pose_ ? "true" : "false");
    }
    else
    {
      RCLCPP_INFO(
        this->get_logger(),
        "LidarToWorld started (fixed extrinsic: xyz=(%.3f, %.3f, %.3f), pitch=%.1f deg)",
        sensor_offset_x_,
        sensor_offset_y_,
        sensor_offset_z_,
        sensor_pitch_deg_);
    }
    RCLCPP_INFO(
      this->get_logger(),
      "LidarToWorld time sync: pose_time_tolerance=%.1f ms warn_interval=%.1f s",
      pose_time_tolerance_sec_ * 1000.0,
      time_sync_warn_interval_sec_);
  }

private:
  struct TimedPose
  {
    double t_sec;
    Eigen::Quaterniond q_wf;
    Eigen::Vector3d t_wf;
  };

  static double ToSec(const builtin_interfaces::msg::Time &t)
  {
    return static_cast<double>(t.sec) + 1e-9 * static_cast<double>(t.nanosec);
  }

  void AppendPose(
    const PoseStamped::SharedPtr msg,
    std::deque<TimedPose> &pose_buf,
    std::mutex &pose_mutex)
  {
    if (!msg)
    {
      return;
    }

    TimedPose tp;
    tp.t_sec = ToSec(msg->header.stamp);
    tp.q_wf = Eigen::Quaterniond(
      msg->pose.orientation.w,
      msg->pose.orientation.x,
      msg->pose.orientation.y,
      msg->pose.orientation.z);

    if (tp.q_wf.norm() < 1e-9)
    {
      return;
    }
    tp.q_wf.normalize();

    tp.t_wf = Eigen::Vector3d(
      msg->pose.position.x,
      msg->pose.position.y,
      msg->pose.position.z);

    std::lock_guard<std::mutex> lock(pose_mutex);
    if (!pose_buf.empty() && tp.t_sec < pose_buf.back().t_sec)
    {
      pose_buf.clear();
    }

    pose_buf.push_back(tp);
    constexpr size_t kMaxPoseBuf = 4000;
    while (pose_buf.size() > kMaxPoseBuf)
    {
      pose_buf.pop_front();
    }
  }

  void basePoseCb(const PoseStamped::SharedPtr msg)
  {
    AppendPose(msg, base_pose_buf_, base_pose_mutex_);
  }

  void sensorPoseCb(const PoseStamped::SharedPtr msg)
  {
    AppendPose(msg, sensor_pose_buf_, sensor_pose_mutex_);
  }

  bool QueryPoseAt(
    double t_query,
    const std::deque<TimedPose> &pose_buf,
    std::mutex &pose_mutex,
    const char *pose_label,
    bool warn_on_failure,
    Eigen::Quaterniond &q_wf,
    Eigen::Vector3d &t_wf)
  {
    std::lock_guard<std::mutex> lock(pose_mutex);
    if (pose_buf.empty())
    {
      if (warn_on_failure)
      {
        RCLCPP_WARN_THROTTLE(
          this->get_logger(),
          *this->get_clock(),
          static_cast<int64_t>(std::max(0.1, time_sync_warn_interval_sec_) * 1000.0),
          "Dropping cloud: %s buffer empty for cloud stamp %.6f",
          pose_label,
          t_query);
      }
      return false;
    }

    auto within_tolerance = [this, t_query, pose_label, warn_on_failure](double pose_stamp_sec) -> bool {
      if (pose_time_tolerance_sec_ <= 0.0)
      {
        return true;
      }
      const double diff_sec = std::fabs(t_query - pose_stamp_sec);
      if (diff_sec <= pose_time_tolerance_sec_)
      {
        return true;
      }

      if (warn_on_failure)
      {
        RCLCPP_WARN_THROTTLE(
          this->get_logger(),
          *this->get_clock(),
          static_cast<int64_t>(std::max(0.1, time_sync_warn_interval_sec_) * 1000.0),
          "Dropping cloud: %s time mismatch cloud=%.6f pose=%.6f diff=%.1fms tol=%.1fms",
          pose_label,
          t_query,
          pose_stamp_sec,
          diff_sec * 1000.0,
          pose_time_tolerance_sec_ * 1000.0);
      }
      return false;
    };

    if (pose_buf.size() == 1)
    {
      if (!within_tolerance(pose_buf.front().t_sec))
      {
        return false;
      }
      q_wf = pose_buf.front().q_wf;
      t_wf = pose_buf.front().t_wf;
      return true;
    }

    auto it = std::lower_bound(
      pose_buf.begin(),
      pose_buf.end(),
      t_query,
      [](const TimedPose &p, double t) { return p.t_sec < t; });

    if (it == pose_buf.begin())
    {
      if (!within_tolerance(it->t_sec))
      {
        return false;
      }
      q_wf = it->q_wf;
      t_wf = it->t_wf;
      return true;
    }

    if (it == pose_buf.end())
    {
      if (!within_tolerance(pose_buf.back().t_sec))
      {
        return false;
      }
      q_wf = pose_buf.back().q_wf;
      t_wf = pose_buf.back().t_wf;
      return true;
    }

    const TimedPose &right = *it;
    const TimedPose &left = *(it - 1);
    const double dt = right.t_sec - left.t_sec;
    if (dt <= 1e-9)
    {
      if (!within_tolerance(right.t_sec))
      {
        return false;
      }
      q_wf = right.q_wf;
      t_wf = right.t_wf;
      return true;
    }

    if (pose_time_tolerance_sec_ > 0.0)
    {
      const double nearest_dt_sec = std::min(t_query - left.t_sec, right.t_sec - t_query);
      if (nearest_dt_sec > pose_time_tolerance_sec_)
      {
        if (warn_on_failure)
        {
          RCLCPP_WARN_THROTTLE(
            this->get_logger(),
            *this->get_clock(),
            static_cast<int64_t>(std::max(0.1, time_sync_warn_interval_sec_) * 1000.0),
            "Dropping cloud: %s has no pose near cloud stamp cloud=%.6f left=%.6f right=%.6f nearest=%.1fms tol=%.1fms",
            pose_label,
            t_query,
            left.t_sec,
            right.t_sec,
            nearest_dt_sec * 1000.0,
            pose_time_tolerance_sec_ * 1000.0);
        }
        return false;
      }
    }

    const double alpha = std::clamp((t_query - left.t_sec) / dt, 0.0, 1.0);
    q_wf = left.q_wf.slerp(alpha, right.q_wf);
    q_wf.normalize();
    t_wf = (1.0 - alpha) * left.t_wf + alpha * right.t_wf;
    return true;
  }

  void cloudCb(const PointCloud2::SharedPtr msg)
  {
    if (!msg || msg->data.empty())
    {
      return;
    }

    if (!cloud_pub_ && !cloud_body_pub_)
    {
      return;
    }

    const bool need_base_pose = static_cast<bool>(cloud_pub_) || use_dynamic_sensor_pose_;
    const double stamp_sec = ToSec(msg->header.stamp);

    Eigen::Quaterniond q_wb = Eigen::Quaterniond::Identity();
    Eigen::Vector3d t_wb = Eigen::Vector3d::Zero();
    if (
      need_base_pose &&
      !QueryPoseAt(
        stamp_sec,
        base_pose_buf_,
        base_pose_mutex_,
        "base/world pose",
        true,
        q_wb,
        t_wb))
    {
      return;
    }

    Eigen::Matrix3d R_bs = R_bs_static_;
    Eigen::Vector3d t_bs = t_bs_static_;
    Eigen::Matrix3d R_ws = Eigen::Matrix3d::Identity();
    Eigen::Vector3d t_ws = Eigen::Vector3d::Zero();

    if (use_dynamic_sensor_pose_)
    {
      Eigen::Quaterniond q_ws;
      if (!QueryPoseAt(
            stamp_sec,
            sensor_pose_buf_,
            sensor_pose_mutex_,
            "sensor/world pose",
            require_dynamic_sensor_pose_,
            q_ws,
            t_ws))
      {
        if (require_dynamic_sensor_pose_)
        {
          return;
        }

        R_ws = q_wb.toRotationMatrix() * R_bs;
        t_ws = q_wb.toRotationMatrix() * t_bs + t_wb;
        WarnDynamicPoseFallback(stamp_sec);
      }
      else
      {
        R_ws = q_ws.toRotationMatrix();
        const Eigen::Matrix3d R_bw = q_wb.conjugate().toRotationMatrix();
        R_bs = R_bw * R_ws;
        t_bs = R_bw * (t_ws - t_wb);
      }
    }
    else
    {
      const Eigen::Matrix3d R_wb = q_wb.toRotationMatrix();
      R_ws = R_wb * R_bs;
      t_ws = R_wb * t_bs + t_wb;
    }

    int off_x = -1;
    int off_y = -1;
    int off_z = -1;
    for (const auto &f : msg->fields)
    {
      if (f.name == "x") off_x = f.offset;
      else if (f.name == "y") off_y = f.offset;
      else if (f.name == "z") off_z = f.offset;
    }
    if (off_x < 0 || off_y < 0 || off_z < 0)
    {
      return;
    }

    const size_t num_points = static_cast<size_t>(msg->width) * msg->height;
    const size_t step = msg->point_step;

    PointCloud2 body_cloud;
    PointCloud2 world_cloud;
    uint8_t *body_data = nullptr;
    uint8_t *world_data = nullptr;

    if (cloud_body_pub_)
    {
      body_cloud = *msg;
      body_cloud.header.frame_id = body_frame_id_;
      body_data = body_cloud.data.data();
    }
    if (cloud_pub_)
    {
      world_cloud = *msg;
      world_cloud.header.frame_id = world_frame_id_;
      world_data = world_cloud.data.data();
    }

    for (size_t i = 0; i < num_points; ++i)
    {
      const uint8_t *src = msg->data.data() + i * step;
      const Eigen::Vector3d ps(
        *reinterpret_cast<const float *>(src + off_x),
        *reinterpret_cast<const float *>(src + off_y),
        *reinterpret_cast<const float *>(src + off_z));

      if (cloud_body_pub_)
      {
        uint8_t *body_dst = body_data + i * step;
        const Eigen::Vector3d pb = R_bs * ps + t_bs;
        const float bx = static_cast<float>(pb.x());
        const float by = static_cast<float>(pb.y());
        const float bz = static_cast<float>(pb.z());
        std::memcpy(body_dst + off_x, &bx, sizeof(float));
        std::memcpy(body_dst + off_y, &by, sizeof(float));
        std::memcpy(body_dst + off_z, &bz, sizeof(float));
      }

      if (cloud_pub_)
      {
        uint8_t *world_dst = world_data + i * step;
        const Eigen::Vector3d pw = R_ws * ps + t_ws;
        const float wx = static_cast<float>(pw.x());
        const float wy = static_cast<float>(pw.y());
        const float wz = static_cast<float>(pw.z());
        std::memcpy(world_dst + off_x, &wx, sizeof(float));
        std::memcpy(world_dst + off_y, &wy, sizeof(float));
        std::memcpy(world_dst + off_z, &wz, sizeof(float));
      }
    }

    if (cloud_body_pub_)
    {
      cloud_body_pub_->publish(body_cloud);
    }

    if (!cloud_pub_)
    {
      return;
    }

    if (world_downsample_stride_ <= 1 || num_points < static_cast<size_t>(world_downsample_stride_))
    {
      cloud_pub_->publish(world_cloud);
      return;
    }

    PointCloud2 out_ds = world_cloud;
    const size_t new_points = num_points / static_cast<size_t>(world_downsample_stride_);
    out_ds.width = static_cast<uint32_t>(new_points);
    out_ds.height = 1;
    out_ds.row_step = out_ds.width * step;
    out_ds.data.resize(new_points * step);

    for (size_t i = 0; i < new_points; ++i)
    {
      const uint8_t *src =
        world_cloud.data.data() + (i * static_cast<size_t>(world_downsample_stride_)) * step;
      uint8_t *dst = out_ds.data.data() + i * step;
      std::memcpy(dst, src, step);
    }

    cloud_pub_->publish(out_ds);
  }

  void WarnDynamicPoseFallback(double stamp_sec)
  {
    const auto now = std::chrono::steady_clock::now();
    if (
      warned_dynamic_pose_fallback_once_ &&
      std::chrono::duration<double>(now - last_dynamic_pose_fallback_warn_time_).count()
        < std::max(0.1, dynamic_pose_fallback_warn_interval_sec_))
    {
      return;
    }

    warned_dynamic_pose_fallback_once_ = true;
    last_dynamic_pose_fallback_warn_time_ = now;
    RCLCPP_WARN(
      this->get_logger(),
      "Dynamic sensor/world pose unavailable at cloud stamp %.6f; falling back to fixed sensor extrinsic",
      stamp_sec);
  }

private:
  std::string input_topic_;
  std::string base_pose_topic_;
  std::string sensor_pose_topic_;
  std::string world_topic_;
  std::string body_topic_;
  std::string body_frame_id_;
  std::string world_frame_id_;

  bool use_dynamic_sensor_pose_{false};
  bool require_dynamic_sensor_pose_{false};
  double sensor_offset_x_{0.0};
  double sensor_offset_y_{0.0};
  double sensor_offset_z_{0.4};
  double sensor_pitch_deg_{30.0};
  int world_downsample_stride_{3};
  double pose_time_tolerance_sec_{0.10};
  double time_sync_warn_interval_sec_{2.0};
  double dynamic_pose_fallback_warn_interval_sec_{5.0};

  rclcpp::Subscription<PointCloud2>::SharedPtr cloud_sub_;
  rclcpp::Subscription<PoseStamped>::SharedPtr base_pose_sub_;
  rclcpp::Subscription<PoseStamped>::SharedPtr sensor_pose_sub_;
  rclcpp::Publisher<PointCloud2>::SharedPtr cloud_pub_;
  rclcpp::Publisher<PointCloud2>::SharedPtr cloud_body_pub_;

  std::deque<TimedPose> base_pose_buf_;
  std::deque<TimedPose> sensor_pose_buf_;
  std::mutex base_pose_mutex_;
  std::mutex sensor_pose_mutex_;

  Eigen::Matrix3d R_bs_static_;
  Eigen::Vector3d t_bs_static_;
  std::chrono::steady_clock::time_point last_dynamic_pose_fallback_warn_time_{};
  bool warned_dynamic_pose_fallback_once_{false};
};

int main(int argc, char **argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<LidarToWorld>());
  rclcpp::shutdown();
  return 0;
}
