#include "voxblox_ros/transformer.h"

#include "voxblox_ros/kindr_compat.hpp"

namespace voxblox {

namespace {

bool loadTransformParameter(const ros::NodeHandle& nh_private,
                            const std::string& key,
                            Transformation* transform) {
  CHECK_NOTNULL(transform);
  std::vector<double> values;
  if (!nh_private.getParam(key, values) || values.size() != 16) {
    return false;
  }

  Eigen::Matrix4f matrix = Eigen::Matrix4f::Identity();
  for (size_t row = 0; row < 4; ++row) {
    for (size_t col = 0; col < 4; ++col) {
      matrix(static_cast<Eigen::Index>(row), static_cast<Eigen::Index>(col)) =
          static_cast<float>(values[row * 4 + col]);
    }
  }
  *transform = Transformation(matrix);
  return true;
}

}  // namespace

Transformer::Transformer(const ros::NodeHandle& nh,
                         const ros::NodeHandle& nh_private)
    : nh_(nh),
      nh_private_(nh_private),
      world_frame_("world"),
      sensor_frame_(""),
      use_tf_transforms_(true),
      timestamp_tolerance_ns_(1000000) {
  nh_private_.param("world_frame", world_frame_, world_frame_);
  nh_private_.param("sensor_frame", sensor_frame_, sensor_frame_);

  const double kNanoSecondsInSecond = 1.0e9;
  double timestamp_tolerance_sec =
      timestamp_tolerance_ns_ / kNanoSecondsInSecond;
  nh_private_.param("timestamp_tolerance_sec", timestamp_tolerance_sec,
                    timestamp_tolerance_sec);
  timestamp_tolerance_ns_ =
      static_cast<int64_t>(timestamp_tolerance_sec * kNanoSecondsInSecond);

  // Transform settings.
  nh_private_.param("use_tf_transforms", use_tf_transforms_,
                    use_tf_transforms_);
  // If we use topic transforms, we have 2 parts: a dynamic transform from a
  // topic and a static transform from parameters.
  // Static transform should be T_G_D (where D is whatever sensor the
  // dynamic coordinate frame is in) and the static should be T_D_C (where
  // C is the sensor frame that produces the depth data). It is possible to
  // specify T_C_D and set invert_static_tranform to true.
  if (!use_tf_transforms_) {
    transform_sub_ =
        nh_.subscribe("transform", 40, &Transformer::transformCallback, this);
    // Retrieve T_D_C from params.
    if (loadTransformParameter(nh_private_, "T_B_D", &T_B_D_)) {
      // See if we need to invert it.
      bool invert_static_tranform = false;
      nh_private_.param("invert_T_B_D", invert_static_tranform,
                        invert_static_tranform);
      if (invert_static_tranform) {
        T_B_D_ = T_B_D_.inverse();
      }
    }
    if (loadTransformParameter(nh_private_, "T_B_C", &T_B_C_)) {
      // See if we need to invert it.
      bool invert_static_tranform = false;
      nh_private_.param("invert_T_B_C", invert_static_tranform,
                        invert_static_tranform);
      if (invert_static_tranform) {
        T_B_C_ = T_B_C_.inverse();
      }
    }
  }
}

void Transformer::transformCallback(
    const geometry_msgs::TransformStamped& transform_msg) {
  transform_queue_.push_back(transform_msg);
}

bool Transformer::lookupTransform(const std::string& from_frame,
                                  const std::string& to_frame,
                                  const ros::Time& timestamp,
                                  Transformation* transform) {
  CHECK_NOTNULL(transform);
  if (use_tf_transforms_) {
    return lookupTransformTf(from_frame, to_frame, timestamp, transform);
  } else {
    return lookupTransformQueue(timestamp, transform);
  }
}

// Stolen from octomap_manager
bool Transformer::lookupTransformTf(const std::string& from_frame,
                                    const std::string& to_frame,
                                    const ros::Time& timestamp,
                                    Transformation* transform) {
  CHECK_NOTNULL(transform);
  tf::StampedTransform tf_transform;
  ros::Time time_to_lookup = timestamp;

  // Allow overwriting the TF frame for the sensor.
  std::string from_frame_modified = from_frame;
  if (!sensor_frame_.empty()) {
    from_frame_modified = sensor_frame_;
  }

  // Previous behavior was just to use the latest transform if the time is in
  // the future. Now we will just wait.
  if (!tf_listener_.canTransform(to_frame, from_frame_modified,
                                 time_to_lookup)) {
    return false;
  }

  try {
    tf_listener_.lookupTransform(to_frame, from_frame_modified, time_to_lookup,
                                 tf_transform);
  } catch (tf::TransformException& ex) {  // NOLINT
    ROS_ERROR_STREAM(
        "Error getting TF transform from sensor data: " << ex.what());
    return false;
  }

  tf::transformTFToKindr(tf_transform, transform);
  return true;
}

bool Transformer::lookupTransformQueue(const ros::Time& timestamp,
                                       Transformation* transform) {
  CHECK_NOTNULL(transform);
  if (transform_queue_.empty()) {
    ROS_WARN_STREAM_THROTTLE(30, "No match found for transform timestamp: "
                                     << timestamp.toSec()
                                     << " as transform queue is empty.");
    return false;
  }
  // Try to match the transforms in the queue.
  bool match_found = false;
  std::deque<geometry_msgs::TransformStamped>::iterator it =
      transform_queue_.begin();
  for (; it != transform_queue_.end(); ++it) {
    const ros::Time transform_stamp(it->header.stamp);
    // If the current transform is newer than the requested timestamp, we need
    // to break.
    if (transform_stamp > timestamp) {
      if ((transform_stamp - timestamp).toNSec() < timestamp_tolerance_ns_) {
        match_found = true;
      }
      break;
    }

    if ((timestamp - transform_stamp).toNSec() < timestamp_tolerance_ns_) {
      match_found = true;
      break;
    }
  }

  // Match found basically means an exact match.
  Transformation T_G_D;
  if (match_found) {
    tf::transformMsgToKindr(it->transform, &T_G_D);
  } else {
    // If we think we have an inexact match, have to check that we're still
    // within bounds and interpolate.
    if (it == transform_queue_.begin() || it == transform_queue_.end()) {
      ROS_WARN_STREAM_THROTTLE(
          30, "No match found for transform timestamp: "
                  << timestamp.toSec()
                  << " Queue front: "
                  << ros::Time(transform_queue_.front().header.stamp).toSec()
                  << " back: "
                  << ros::Time(transform_queue_.back().header.stamp).toSec());
      return false;
    }
    // Newest should be 1 past the requested timestamp, oldest should be one
    // before the requested timestamp.
    Transformation T_G_D_newest;
    tf::transformMsgToKindr(it->transform, &T_G_D_newest);
    int64_t offset_newest_ns =
        (ros::Time(it->header.stamp) - timestamp).toNSec();
    // We already checked that this is not the beginning.
    it--;
    Transformation T_G_D_oldest;
    tf::transformMsgToKindr(it->transform, &T_G_D_oldest);
    int64_t offset_oldest_ns =
        (timestamp - ros::Time(it->header.stamp)).toNSec();

    // Interpolate between the two transformations using the exponential map.
    FloatingPoint t_diff_ratio =
        static_cast<FloatingPoint>(offset_oldest_ns) /
        static_cast<FloatingPoint>(offset_newest_ns + offset_oldest_ns);

    Transformation::Vector6 diff_vector =
        (T_G_D_oldest.inverse() * T_G_D_newest).log();
    T_G_D = T_G_D_oldest * Transformation::exp(t_diff_ratio * diff_vector);
  }

  // If we have a static transform, apply it too.
  // Transform should actually be T_G_C. So need to take it through the full
  // chain.
  *transform = T_G_D * T_B_D_.inverse() * T_B_C_;

  // And also clear the queue up to this point. This leaves the current
  // message in place.
  transform_queue_.erase(transform_queue_.begin(), it);
  return true;
}

}  // namespace voxblox
