#pragma once

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <thread>
#include <utility>

#include <Eigen/Core>
#include "geometry_msgs/msg/point.hpp"
#include "geometry_msgs/msg/point32.hpp"
#include "geometry_msgs/msg/point_stamped.hpp"
#include "geometry_msgs/msg/polygon.hpp"
#include "geometry_msgs/msg/polygon_stamped.hpp"
#include "geometry_msgs/msg/pose.hpp"
#include "geometry_msgs/msg/pose_stamped.hpp"
#include "geometry_msgs/msg/pose_with_covariance_stamped.hpp"
#include "geometry_msgs/msg/transform.hpp"
#include "geometry_msgs/msg/transform_stamped.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "nav_msgs/msg/path.hpp"
#include "planner_msgs/ros1_compat.hpp"
#include "planner_semantic_msgs/ros1_compat.hpp"
#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/point_cloud2.hpp"
#include "sensor_msgs/msg/point_field.hpp"
#include "std_msgs/msg/bool.hpp"
#include "std_msgs/msg/color_rgba.hpp"
#include "std_msgs/msg/float32_multi_array.hpp"
#include "std_msgs/msg/header.hpp"
#include "std_srvs/srv/empty.hpp"
#include "std_srvs/srv/set_bool.hpp"
#include "std_srvs/srv/trigger.hpp"
#include "tf2/LinearMath/Quaternion.h"
#include "tf2/LinearMath/Transform.h"
#include "tf2/LinearMath/Vector3.h"
#include "tf2/utils.h"
#include "tf2_geometry_msgs/tf2_geometry_msgs.hpp"
#include "tf2_ros/buffer.h"
#include "tf2_ros/transform_broadcaster.h"
#include "tf2_ros/transform_listener.h"
#include "visualization_msgs/msg/marker.hpp"
#include "visualization_msgs/msg/marker_array.hpp"

namespace geometry_msgs {

using Point = msg::Point;
using Point32 = msg::Point32;
using PointStamped = msg::PointStamped;
using Polygon = msg::Polygon;
using PolygonStamped = msg::PolygonStamped;
using Pose = msg::Pose;
using PoseStamped = msg::PoseStamped;
using PoseWithCovarianceStamped = msg::PoseWithCovarianceStamped;
using Transform = msg::Transform;
using TransformStamped = msg::TransformStamped;

}  // namespace geometry_msgs

namespace nav_msgs {

using Odometry = msg::Odometry;
using Path = msg::Path;

}  // namespace nav_msgs

namespace sensor_msgs {

using PointCloud2 = msg::PointCloud2;
using PointField = msg::PointField;

}  // namespace sensor_msgs

namespace std_msgs {

using Bool = msg::Bool;
using ColorRGBA = msg::ColorRGBA;
using Float32MultiArray = msg::Float32MultiArray;
using Header = msg::Header;

}  // namespace std_msgs

namespace std_srvs {

struct Empty {
  using ServiceType = srv::Empty;
  using Request = ServiceType::Request;
  using Response = ServiceType::Response;

  Request request;
  Response response;
};

struct SetBool {
  using ServiceType = srv::SetBool;
  using Request = ServiceType::Request;
  using Response = ServiceType::Response;

  Request request;
  Response response;
};

struct Trigger {
  using ServiceType = srv::Trigger;
  using Request = ServiceType::Request;
  using Response = ServiceType::Response;

  Request request;
  Response response;
};

}  // namespace std_srvs

namespace visualization_msgs {

using Marker = msg::Marker;
using MarkerArray = msg::MarkerArray;

}  // namespace visualization_msgs

namespace ros {

class Duration {
 public:
  Duration() : nanoseconds_(0) {}
  explicit Duration(double seconds)
      : nanoseconds_(static_cast<int64_t>(seconds * 1000000000.0)) {}
  Duration(int32_t sec, uint32_t nsec = 0)
      : nanoseconds_(static_cast<int64_t>(sec) * 1000000000LL +
                     static_cast<int64_t>(nsec)) {}

  double toSec() const {
    return static_cast<double>(nanoseconds_) / 1000000000.0;
  }

  int64_t toNSec() const { return nanoseconds_; }

  int64_t nanoseconds() const { return nanoseconds_; }

  void fromSec(double seconds) {
    nanoseconds_ = static_cast<int64_t>(seconds * 1000000000.0);
  }

  void fromNSec(int64_t nanoseconds) { nanoseconds_ = nanoseconds; }

  bool isZero() const { return nanoseconds_ == 0; }

  builtin_interfaces::msg::Duration to_msg() const {
    builtin_interfaces::msg::Duration msg;
    msg.sec = static_cast<int32_t>(nanoseconds_ / 1000000000LL);
    msg.nanosec = static_cast<uint32_t>(nanoseconds_ % 1000000000LL);
    return msg;
  }

  rclcpp::Duration to_rclcpp() const {
    return rclcpp::Duration(std::chrono::nanoseconds(nanoseconds_));
  }

  operator builtin_interfaces::msg::Duration() const { return to_msg(); }

  void sleep() const {
    std::this_thread::sleep_for(std::chrono::nanoseconds(nanoseconds_));
  }

 private:
  int64_t nanoseconds_;
};

class Time {
 public:
  Time() : nanoseconds_(0) {}
  explicit Time(int sec) : Time(static_cast<uint32_t>(sec), 0) {}
  Time(uint32_t sec, uint32_t nsec = 0)
      : nanoseconds_(static_cast<int64_t>(sec) * 1000000000LL +
                     static_cast<int64_t>(nsec)) {}
  explicit Time(const builtin_interfaces::msg::Time& time_msg)
      : Time(time_msg.sec, time_msg.nanosec) {}
  explicit Time(const rclcpp::Time& time) : nanoseconds_(time.nanoseconds()) {}
  explicit Time(int64_t nanoseconds) : nanoseconds_(nanoseconds) {}

  static Time now();

  double toSec() const {
    return static_cast<double>(nanoseconds_) / 1000000000.0;
  }

  int64_t toNSec() const { return nanoseconds_; }

  int64_t nanoseconds() const { return nanoseconds_; }

  builtin_interfaces::msg::Time to_msg() const {
    builtin_interfaces::msg::Time msg;
    msg.sec = static_cast<int32_t>(nanoseconds_ / 1000000000LL);
    msg.nanosec = static_cast<uint32_t>(nanoseconds_ % 1000000000LL);
    return msg;
  }

  rclcpp::Time to_rclcpp() const {
    return rclcpp::Time(nanoseconds_, RCL_SYSTEM_TIME);
  }

  operator builtin_interfaces::msg::Time() const { return to_msg(); }

  Time& fromNSec(int64_t nanoseconds) {
    nanoseconds_ = nanoseconds;
    return *this;
  }

 private:
  int64_t nanoseconds_;
};

class WallTime {
 public:
  WallTime() : nanoseconds_(0) {}
  explicit WallTime(int64_t nanoseconds) : nanoseconds_(nanoseconds) {}

  static WallTime now() {
    return WallTime(std::chrono::duration_cast<std::chrono::nanoseconds>(
                        std::chrono::steady_clock::now().time_since_epoch())
                        .count());
  }

  int64_t nanoseconds() const { return nanoseconds_; }

 private:
  int64_t nanoseconds_;
};

inline Duration operator-(const Time& lhs, const Time& rhs) {
  return Duration(
      static_cast<int32_t>((lhs.nanoseconds() - rhs.nanoseconds()) /
                           1000000000LL),
      static_cast<uint32_t>((lhs.nanoseconds() - rhs.nanoseconds()) %
                            1000000000LL));
}

inline Time operator+(const Time& lhs, const Duration& rhs) {
  return Time(lhs.nanoseconds() + rhs.nanoseconds());
}

inline Time operator-(const Time& lhs, const Duration& rhs) {
  return Time(lhs.nanoseconds() - rhs.nanoseconds());
}

inline Duration operator-(const WallTime& lhs, const WallTime& rhs) {
  return Duration(
      static_cast<int32_t>((lhs.nanoseconds() - rhs.nanoseconds()) /
                           1000000000LL),
      static_cast<uint32_t>((lhs.nanoseconds() - rhs.nanoseconds()) %
                            1000000000LL));
}

inline bool operator<(const Time& lhs, const Time& rhs) {
  return lhs.nanoseconds() < rhs.nanoseconds();
}

inline bool operator>(const Time& lhs, const Time& rhs) {
  return rhs < lhs;
}

inline bool operator<=(const Time& lhs, const Time& rhs) {
  return !(rhs < lhs);
}

inline bool operator>=(const Time& lhs, const Time& rhs) {
  return !(lhs < rhs);
}

inline bool operator==(const Time& lhs, const Time& rhs) {
  return lhs.nanoseconds() == rhs.nanoseconds();
}

inline bool operator!=(const Time& lhs, const Time& rhs) {
  return !(lhs == rhs);
}

inline bool operator<(const Duration& lhs, const Duration& rhs) {
  return lhs.nanoseconds() < rhs.nanoseconds();
}

inline bool operator>(const Duration& lhs, const Duration& rhs) {
  return rhs < lhs;
}

inline bool operator<=(const Duration& lhs, const Duration& rhs) {
  return !(rhs < lhs);
}

inline bool operator>=(const Duration& lhs, const Duration& rhs) {
  return !(lhs < rhs);
}

inline bool operator==(const Duration& lhs, const Duration& rhs) {
  return lhs.nanoseconds() == rhs.nanoseconds();
}

inline bool operator!=(const Duration& lhs, const Duration& rhs) {
  return !(lhs == rhs);
}

struct TimerEvent {};

namespace detail {

inline std::shared_ptr<rclcpp::Node>& default_node_storage() {
  static std::shared_ptr<rclcpp::Node> node;
  return node;
}

inline std::shared_ptr<rclcpp::Node> ensure_default_node() {
  auto& node = default_node_storage();
  if (!node) {
    rclcpp::NodeOptions options;
    options.allow_undeclared_parameters(true);
    options.automatically_declare_parameters_from_overrides(true);
    node = std::make_shared<rclcpp::Node>("ros1_compat", options);
  }
  return node;
}

inline void set_default_node(const std::shared_ptr<rclcpp::Node>& node) {
  default_node_storage() = node;
}

inline std::shared_ptr<rclcpp::Node> default_node() {
  return ensure_default_node();
}

inline rclcpp::Logger get_logger() { return default_node()->get_logger(); }

inline rclcpp::Clock::SharedPtr get_clock() {
  return default_node()->get_clock();
}

inline std::string trim_leading_slashes(std::string value) {
  while (!value.empty() && value.front() == '/') {
    value.erase(value.begin());
  }
  return value;
}

inline std::string node_name_for_params() {
  return trim_leading_slashes(default_node()->get_name());
}

inline std::string normalize_param_key(std::string key) {
  if (key.empty()) {
    return key;
  }
  if (key[0] == '~') {
    key.erase(key.begin());
  }
  key = trim_leading_slashes(key);
  const std::string node_name = node_name_for_params();
  if (!node_name.empty() &&
      key.compare(0, node_name.size(), node_name) == 0 &&
      (key.size() == node_name.size() || key[node_name.size()] == '/')) {
    key.erase(0, node_name.size());
    key = trim_leading_slashes(key);
  }
  std::replace(key.begin(), key.end(), '/', '.');
  while (!key.empty() && key.front() == '.') {
    key.erase(key.begin());
  }
  return key;
}

inline std::string normalize_param_key(const std::string& ns,
                                       const std::string& key) {
  if (key.empty()) {
    return key;
  }
  if (key[0] == '/' || key[0] == '~') {
    return normalize_param_key(key);
  }
  if (ns.empty() || ns == "~") {
    return normalize_param_key(key);
  }
  return normalize_param_key(ns + "/" + key);
}

inline std::string resolve_topic_name(const std::string& ns,
                                      const std::string& topic) {
  if (topic.empty() || topic[0] == '/' || ns.empty() || ns == "~") {
    return topic;
  }
  return ns + "/" + topic;
}

template <typename T>
inline bool get_parameter(const std::string& key, T& value) {
  return default_node()->get_parameter(normalize_param_key(key), value);
}

template <typename T>
inline bool get_parameter(const std::string& ns, const std::string& key,
                          T& value) {
  return default_node()->get_parameter(normalize_param_key(ns, key), value);
}

}  // namespace detail

inline Time Time::now() { return Time(detail::default_node()->now().nanoseconds()); }

class NodeHandle;

class Publisher {
 public:
  Publisher() = default;

  template <typename MessageT>
  void publish(const MessageT& message) const {
    auto publisher =
        std::static_pointer_cast<rclcpp::Publisher<MessageT>>(publisher_);
    if (publisher) {
      publisher->publish(message);
    }
  }

  size_t getNumSubscribers() const {
    if (subscriber_count_getter_) {
      return subscriber_count_getter_();
    }
    return 0;
  }

 private:
  friend class NodeHandle;

  template <typename MessageT>
  friend class NodeHandlePublisherFactory;

  template <typename MessageT>
  void set(const typename rclcpp::Publisher<MessageT>::SharedPtr& publisher) {
    publisher_ = publisher;
    subscriber_count_getter_ = [publisher]() {
      return publisher ? publisher->get_subscription_count() : 0U;
    };
  }

  std::shared_ptr<void> publisher_;
  std::function<size_t()> subscriber_count_getter_;
};

class Subscriber {
 public:
  Subscriber() = default;

  void shutdown() { subscription_.reset(); }

 private:
  friend class NodeHandle;

  template <typename MessageT>
  friend class NodeHandleSubscriptionFactory;

  template <typename MessageT>
  void set(
      const typename rclcpp::Subscription<MessageT>::SharedPtr& subscription) {
    subscription_ = subscription;
  }

  std::shared_ptr<void> subscription_;
};

class ServiceServer {
 public:
  ServiceServer() = default;

  void shutdown() { service_.reset(); }

 private:
  friend class NodeHandle;

  template <typename ServiceT>
  friend class NodeHandleServiceFactory;

  template <typename ServiceT>
  void set(const typename rclcpp::Service<ServiceT>::SharedPtr& service) {
    service_ = service;
  }

  std::shared_ptr<void> service_;
};

class ServiceClient {
 public:
  ServiceClient() = default;

  template <typename ServiceWrapperT>
  bool call(ServiceWrapperT& service) const {
    typedef typename ServiceWrapperT::ServiceType ServiceT;
    auto client = std::static_pointer_cast<rclcpp::Client<ServiceT>>(client_);
    if (!client) {
      return false;
    }
    if (!client->wait_for_service(std::chrono::seconds(1))) {
      return false;
    }
    auto request =
        std::make_shared<typename ServiceT::Request>(service.request);
    auto future = client->async_send_request(request);
    const auto ret = rclcpp::spin_until_future_complete(
        detail::default_node(), future, std::chrono::seconds(5));
    if (ret != rclcpp::FutureReturnCode::SUCCESS) {
      return false;
    }
    service.response = *future.get();
    return true;
  }

 private:
  friend class NodeHandle;

  template <typename ServiceT>
  friend class NodeHandleClientFactory;

  template <typename ServiceT>
  void set(const typename rclcpp::Client<ServiceT>::SharedPtr& client) {
    client_ = client;
  }

  std::shared_ptr<void> client_;
};

class Timer {
 public:
  Timer() = default;

  void start() {
    if (timer_) {
      timer_->reset();
    }
  }

  void stop() {
    if (timer_) {
      timer_->cancel();
    }
  }

  void setPeriod(const Duration& period) {
    if (!timer_) {
      return;
    }
    int64_t old_period = 0;
    const auto ret = rcl_timer_exchange_period(
        timer_->get_timer_handle().get(), period.nanoseconds(), &old_period);
    (void)old_period;
    if (ret != RCL_RET_OK) {
      throw std::runtime_error("Failed to update timer period");
    }
  }

 private:
  friend class NodeHandle;

  void set(const rclcpp::TimerBase::SharedPtr& timer) { timer_ = timer; }

  rclcpp::TimerBase::SharedPtr timer_;
};

class NodeHandle {
 public:
  NodeHandle() : node_(detail::default_node()) {}
  explicit NodeHandle(const std::string& ns)
      : node_(detail::default_node()), namespace_(ns) {}

  template <typename MessageT>
  Publisher advertise(const std::string& topic, uint32_t queue_size) const {
    return advertise<MessageT>(topic, queue_size, false);
  }

  template <typename MessageT>
  Publisher advertise(const std::string& topic, uint32_t queue_size,
                      bool /*latch*/) const {
    Publisher publisher;
    auto ros2_publisher = node_->create_publisher<MessageT>(
        detail::resolve_topic_name(namespace_, topic),
        rclcpp::QoS(rclcpp::KeepLast(queue_size)));
    publisher.set<MessageT>(ros2_publisher);
    return publisher;
  }

  template <typename MessageT, typename T>
  Subscriber subscribe(const std::string& topic, uint32_t queue_size,
                       void (T::*callback)(const MessageT&), T* object) const {
    Subscriber subscriber;
    auto ros2_subscription = node_->create_subscription<MessageT>(
        detail::resolve_topic_name(namespace_, topic),
        rclcpp::QoS(rclcpp::KeepLast(queue_size)),
        [object, callback](const typename MessageT::SharedPtr message) {
          (object->*callback)(*message);
        });
    subscriber.set<MessageT>(ros2_subscription);
    return subscriber;
  }

  template <typename MessageT, typename T>
  Subscriber subscribe(
      const std::string& topic, uint32_t queue_size,
      void (T::*callback)(const typename MessageT::SharedPtr&),
      T* object) const {
    Subscriber subscriber;
    auto ros2_subscription = node_->create_subscription<MessageT>(
        detail::resolve_topic_name(namespace_, topic),
        rclcpp::QoS(rclcpp::KeepLast(queue_size)),
        [object, callback](const typename MessageT::SharedPtr message) {
          (object->*callback)(message);
        });
    subscriber.set<MessageT>(ros2_subscription);
    return subscriber;
  }

  template <typename ServiceT, typename T>
  ServiceServer advertiseService(
      const std::string& service_name,
      bool (T::*callback)(typename ServiceT::Request&,
                          typename ServiceT::Response&),
      T* object) const {
    ServiceServer service;
    auto ros2_service = node_->create_service<ServiceT>(
        detail::resolve_topic_name(namespace_, service_name),
        [object, callback](
            const std::shared_ptr<typename ServiceT::Request> request,
            std::shared_ptr<typename ServiceT::Response> response) {
          (object->*callback)(*request, *response);
        });
    service.set<ServiceT>(ros2_service);
    return service;
  }

  template <typename ServiceWrapperT>
  ServiceClient serviceClient(const std::string& service_name) const {
    typedef typename ServiceWrapperT::ServiceType ServiceT;
    ServiceClient client;
    auto ros2_client = node_->create_client<ServiceT>(
        detail::resolve_topic_name(namespace_, service_name));
    client.set<ServiceT>(ros2_client);
    return client;
  }

  template <typename T>
  Timer createTimer(const Duration& period,
                    void (T::*callback)(const TimerEvent&), T* object) const {
    Timer timer;
    auto ros2_timer = node_->create_wall_timer(
        std::chrono::nanoseconds(period.nanoseconds()),
        [object, callback]() {
          TimerEvent event;
          (object->*callback)(event);
        });
    timer.set(ros2_timer);
    return timer;
  }

  template <typename T>
  bool getParam(const std::string& key, T& value) const {
    return detail::get_parameter(namespace_, key, value);
  }

  template <typename T>
  void param(const std::string& key, T& value, const T& default_value) const {
    if (!getParam(key, value)) {
      value = default_value;
    }
  }

  template <typename T>
  T param(const std::string& key, const T& default_value) const {
    T value{};
    param(key, value, default_value);
    return value;
  }

  bool hasParam(const std::string& key) const {
    return node_->has_parameter(detail::normalize_param_key(namespace_, key));
  }

  std::string getNamespace() const { return namespace_.empty() ? std::string() : namespace_; }

  std::string resolveName(const std::string& name) const {
    return detail::resolve_topic_name(namespace_, name);
  }

  bool ok() const { return rclcpp::ok(); }

  void shutdown() { node_.reset(); }

  std::shared_ptr<rclcpp::Node> node() const { return node_; }

 private:
  std::shared_ptr<rclcpp::Node> node_;
  std::string namespace_;
};

namespace param {

template <typename T>
inline bool get(const std::string& key, T& value) {
  return detail::get_parameter(key, value);
}

}  // namespace param

namespace this_node {

inline std::string getName() {
  return std::string("/") + detail::default_node()->get_name();
}

}  // namespace this_node

inline void init(int argc, char** argv, const std::string& node_name) {
  if (!rclcpp::ok()) {
    rclcpp::init(argc, argv);
  }
  rclcpp::NodeOptions options;
  options.allow_undeclared_parameters(true);
  options.automatically_declare_parameters_from_overrides(true);
  detail::set_default_node(std::make_shared<rclcpp::Node>(node_name, options));
}

inline bool ok() { return rclcpp::ok(); }

inline void shutdown() { rclcpp::shutdown(); }

inline void spin() { rclcpp::spin(detail::default_node()); }

inline void spinOnce() { rclcpp::spin_some(detail::default_node()); }

}  // namespace ros

namespace tf {

using Pose = tf2::Transform;
using Quaternion = tf2::Quaternion;
using Transform = tf2::Transform;
using TransformException = tf2::TransformException;
using Vector3 = tf2::Vector3;

class StampedTransform {
 public:
  StampedTransform() = default;
  StampedTransform(const Transform& transform, const ros::Time& stamp,
                   std::string frame_id, std::string child_frame_id)
      : transform_(transform),
        frame_id_(std::move(frame_id)),
        child_frame_id_(std::move(child_frame_id)),
        stamp_(stamp) {}
  explicit StampedTransform(
      const geometry_msgs::msg::TransformStamped& transform_stamped)
      : frame_id_(transform_stamped.header.frame_id),
        child_frame_id_(transform_stamped.child_frame_id),
        stamp_(transform_stamped.header.stamp.sec,
               transform_stamped.header.stamp.nanosec) {
    tf2::fromMsg(transform_stamped.transform, transform_);
  }

  Vector3 operator*(const Vector3& vector) const { return transform_ * vector; }
  Vector3 getOrigin() const { return transform_.getOrigin(); }
  Quaternion getRotation() const { return transform_.getRotation(); }
  const Transform& transform() const { return transform_; }
  const std::string& frame_id() const { return frame_id_; }
  const std::string& child_frame_id() const { return child_frame_id_; }
  const ros::Time& stamp() const { return stamp_; }

 private:
  tf2::Transform transform_;
  std::string frame_id_;
  std::string child_frame_id_;
  ros::Time stamp_;
};

class TransformListener {
 public:
  TransformListener()
      : buffer_(ros::detail::get_clock()),
        listener_(buffer_, ros::detail::default_node(), false) {}

  void lookupTransform(const std::string& target_frame,
                       const std::string& source_frame, const ros::Time& time,
                       StampedTransform& transform) const {
    const auto tf = buffer_.lookupTransform(target_frame, source_frame,
                                            time.to_rclcpp());
    transform = StampedTransform(tf);
  }

  bool waitForTransform(const std::string& target_frame,
                        const std::string& source_frame, const ros::Time& time,
                        const ros::Duration& timeout) const {
    return buffer_.canTransform(target_frame, source_frame, time.to_rclcpp(),
                                timeout.to_rclcpp());
  }

  bool canTransform(const std::string& target_frame,
                    const std::string& source_frame,
                    const ros::Time& time) const {
    return buffer_.canTransform(target_frame, source_frame, time.to_rclcpp());
  }

  bool waitForTransform(const std::string& target_frame,
                        const std::string& source_frame, const ros::Time& time,
                        const ros::Duration& timeout,
                        const ros::Duration& /*polling_sleep_duration*/) const {
    return waitForTransform(target_frame, source_frame, time, timeout);
  }

  void transformPoint(const std::string& target_frame,
                      const geometry_msgs::PointStamped& point_in,
                      geometry_msgs::PointStamped& point_out) const {
    point_out = buffer_.transform(point_in, target_frame);
  }

 private:
  mutable tf2_ros::Buffer buffer_;
  mutable tf2_ros::TransformListener listener_;
};

class TransformBroadcaster {
 public:
  TransformBroadcaster()
      : broadcaster_(ros::detail::default_node()) {}

  void sendTransform(const StampedTransform& transform) const {
    geometry_msgs::msg::TransformStamped msg;
    msg.header.stamp = transform.stamp().to_msg();
    msg.header.frame_id = transform.frame_id();
    msg.child_frame_id = transform.child_frame_id();
    msg.transform = tf2::toMsg(transform.transform());
    broadcaster_.sendTransform(msg);
  }

 private:
  mutable tf2_ros::TransformBroadcaster broadcaster_;
};

inline double getYaw(const geometry_msgs::msg::Quaternion& quaternion_msg) {
  return tf2::getYaw(quaternion_msg);
}

inline void pointMsgToTF(const geometry_msgs::Point& point_msg,
                         Vector3& point_tf) {
  point_tf.setValue(point_msg.x, point_msg.y, point_msg.z);
}

inline void pointTFToMsg(const Vector3& point_tf,
                         geometry_msgs::Point& point_msg) {
  point_msg.x = point_tf.x();
  point_msg.y = point_tf.y();
  point_msg.z = point_tf.z();
}

template <typename Derived>
inline void pointEigenToMsg(const Eigen::MatrixBase<Derived>& point_eigen,
                            geometry_msgs::Point& point_msg) {
  point_msg.x = point_eigen.x();
  point_msg.y = point_eigen.y();
  point_msg.z = point_eigen.z();
}

inline void poseTFToMsg(const Pose& pose_tf, geometry_msgs::Pose& pose_msg) {
  pose_msg.position.x = pose_tf.getOrigin().x();
  pose_msg.position.y = pose_tf.getOrigin().y();
  pose_msg.position.z = pose_tf.getOrigin().z();
  pose_msg.orientation = tf2::toMsg(pose_tf.getRotation());
}

}  // namespace tf

#define ROS_INFO(...) \
  RCLCPP_INFO(::ros::detail::get_logger(), __VA_ARGS__)
#define ROS_WARN(...) \
  RCLCPP_WARN(::ros::detail::get_logger(), __VA_ARGS__)
#define ROS_ERROR(...) \
  RCLCPP_ERROR(::ros::detail::get_logger(), __VA_ARGS__)
#define ROS_INFO_COND(cond, ...)                  \
  do {                                            \
    if (cond) {                                   \
      RCLCPP_INFO(::ros::detail::get_logger(), __VA_ARGS__); \
    }                                             \
  } while (0)
#define ROS_WARN_COND(cond, ...)                  \
  do {                                            \
    if (cond) {                                   \
      RCLCPP_WARN(::ros::detail::get_logger(), __VA_ARGS__); \
    }                                             \
  } while (0)
#define ROS_ERROR_COND(cond, ...)                 \
  do {                                            \
    if (cond) {                                   \
      RCLCPP_ERROR(::ros::detail::get_logger(), __VA_ARGS__); \
    }                                             \
  } while (0)
#define ROS_WARN_THROTTLE(period_sec, ...)                                        \
  RCLCPP_WARN_THROTTLE(::ros::detail::get_logger(), *::ros::detail::get_clock(), \
                       static_cast<int64_t>((period_sec) * 1000.0), __VA_ARGS__)
#define ROS_ERROR_THROTTLE(period_sec, ...)                                       \
  RCLCPP_ERROR_THROTTLE(::ros::detail::get_logger(), *::ros::detail::get_clock(),\
                        static_cast<int64_t>((period_sec) * 1000.0), __VA_ARGS__)
#define ROS_INFO_STREAM(args) \
  RCLCPP_INFO_STREAM(::ros::detail::get_logger(), args)
#define ROS_WARN_STREAM(args) \
  RCLCPP_WARN_STREAM(::ros::detail::get_logger(), args)
#define ROS_ERROR_STREAM(args) \
  RCLCPP_ERROR_STREAM(::ros::detail::get_logger(), args)
#define ROS_WARN_STREAM_THROTTLE(period_sec, args)                                 \
  RCLCPP_WARN_STREAM_THROTTLE(::ros::detail::get_logger(),                        \
                              *::ros::detail::get_clock(),                        \
                              static_cast<int64_t>((period_sec) * 1000.0), args)
#define ROS_INFO_ONCE(...)                         \
  do {                                             \
    static bool _ros_info_once = false;            \
    if (!_ros_info_once) {                         \
      _ros_info_once = true;                       \
      RCLCPP_INFO(::ros::detail::get_logger(), __VA_ARGS__); \
    }                                              \
  } while (0)
