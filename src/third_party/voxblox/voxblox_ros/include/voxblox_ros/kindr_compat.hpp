#pragma once

#include "geometry_msgs/msg/transform.hpp"
#include "planner_common/ros1_compat.hpp"
#include "voxblox/core/common.h"

namespace tf {

template <typename Scalar>
inline void transformKindrToTF(
    const kindr::minimal::QuatTransformationTemplate<Scalar>& transform_kindr,
    tf::Transform* transform_tf) {
  CHECK_NOTNULL(transform_tf);
  const auto& q = transform_kindr.getEigenQuaternion();
  transform_tf->setOrigin(
      tf::Vector3(transform_kindr.getPosition().x(),
                  transform_kindr.getPosition().y(),
                  transform_kindr.getPosition().z()));
  transform_tf->setRotation(
      tf::Quaternion(q.x(), q.y(), q.z(), q.w()));
}

template <typename Scalar>
inline void transformKindrToMsg(
    const kindr::minimal::QuatTransformationTemplate<Scalar>& transform_kindr,
    geometry_msgs::msg::Transform* transform_msg) {
  CHECK_NOTNULL(transform_msg);
  const auto& q = transform_kindr.getEigenQuaternion();
  transform_msg->translation.x = transform_kindr.getPosition().x();
  transform_msg->translation.y = transform_kindr.getPosition().y();
  transform_msg->translation.z = transform_kindr.getPosition().z();
  transform_msg->rotation.x = q.x();
  transform_msg->rotation.y = q.y();
  transform_msg->rotation.z = q.z();
  transform_msg->rotation.w = q.w();
}

template <typename Scalar>
inline void transformTFToKindr(
    const tf::StampedTransform& transform_tf,
    kindr::minimal::QuatTransformationTemplate<Scalar>* transform_kindr) {
  CHECK_NOTNULL(transform_kindr);
  const auto rotation = transform_tf.getRotation();
  typename kindr::minimal::RotationQuaternionTemplate<Scalar>::Implementation q(
      static_cast<Scalar>(rotation.w()), static_cast<Scalar>(rotation.x()),
      static_cast<Scalar>(rotation.y()), static_cast<Scalar>(rotation.z()));
  typename kindr::minimal::PositionTemplate<Scalar> p(
      static_cast<Scalar>(transform_tf.getOrigin().x()),
      static_cast<Scalar>(transform_tf.getOrigin().y()),
      static_cast<Scalar>(transform_tf.getOrigin().z()));
  *transform_kindr =
      kindr::minimal::QuatTransformationTemplate<Scalar>(q, p);
}

template <typename Scalar>
inline void transformMsgToKindr(
    const geometry_msgs::msg::Transform& transform_msg,
    kindr::minimal::QuatTransformationTemplate<Scalar>* transform_kindr) {
  CHECK_NOTNULL(transform_kindr);
  typename kindr::minimal::RotationQuaternionTemplate<Scalar>::Implementation q(
      static_cast<Scalar>(transform_msg.rotation.w),
      static_cast<Scalar>(transform_msg.rotation.x),
      static_cast<Scalar>(transform_msg.rotation.y),
      static_cast<Scalar>(transform_msg.rotation.z));
  typename kindr::minimal::PositionTemplate<Scalar> p(
      static_cast<Scalar>(transform_msg.translation.x),
      static_cast<Scalar>(transform_msg.translation.y),
      static_cast<Scalar>(transform_msg.translation.z));
  *transform_kindr =
      kindr::minimal::QuatTransformationTemplate<Scalar>(q, p);
}

}  // namespace tf
