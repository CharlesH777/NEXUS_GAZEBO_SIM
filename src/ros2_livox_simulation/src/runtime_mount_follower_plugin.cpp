#include <functional>
#include <memory>
#include <string>

#include <gazebo/common/Events.hh>
#include <gazebo/common/Plugin.hh>
#include <gazebo/physics/Link.hh>
#include <gazebo/physics/Model.hh>
#include <gazebo/physics/World.hh>
#include <ignition/math/Pose3.hh>

namespace gazebo
{
class RuntimeMountFollowerPlugin : public ModelPlugin
{
public:
  void Load(physics::ModelPtr model, sdf::ElementPtr sdf) override
  {
    this->model_ = std::move(model);
    if (!this->model_)
    {
      gzerr << "[runtime_mount_follower] model is null" << std::endl;
      return;
    }

    this->world_ = this->model_->GetWorld();
    if (!this->world_)
    {
      gzerr << "[runtime_mount_follower] world is null" << std::endl;
      return;
    }

    if (!sdf || !sdf->HasElement("target_model_name"))
    {
      gzerr << "[runtime_mount_follower] missing <target_model_name>" << std::endl;
      return;
    }

    this->target_model_name_ = sdf->Get<std::string>("target_model_name");
    this->target_link_name_ = sdf->HasElement("target_link_name")
      ? sdf->Get<std::string>("target_link_name")
      : std::string("depth_camera_mount_link");
    this->pose_offset_ = sdf->HasElement("pose_offset")
      ? sdf->Get<ignition::math::Pose3d>("pose_offset")
      : ignition::math::Pose3d::Zero;

    this->update_connection_ = event::Events::ConnectWorldUpdateBegin(
      std::bind(&RuntimeMountFollowerPlugin::OnUpdate, this));

    gzmsg << "[runtime_mount_follower] Loaded for model [" << this->model_->GetName()
          << "], target model [" << this->target_model_name_
          << "], target link [" << this->target_link_name_ << "]" << std::endl;
  }

private:
  void ResolveTarget()
  {
    if (this->target_link_)
    {
      return;
    }

    if (!this->target_model_)
    {
      this->target_model_ = this->world_->ModelByName(this->target_model_name_);
      if (!this->target_model_)
      {
        this->WarnThrottle(
          "target model [" + this->target_model_name_ + "] not found yet");
        return;
      }
    }

    this->target_link_ = this->target_model_->GetLink(this->target_link_name_);
    if (!this->target_link_)
    {
      this->WarnThrottle(
        "target link [" + this->target_link_name_ + "] not found on model [" +
        this->target_model_name_ + "]");
    }
  }

  void WarnThrottle(const std::string & message)
  {
    const common::Time now = this->world_->SimTime();
    if ((now - this->last_warn_time_).Double() < 2.0)
    {
      return;
    }

    this->last_warn_time_ = now;
    gzmsg << "[runtime_mount_follower] " << message << std::endl;
  }

  void OnUpdate()
  {
    this->ResolveTarget();
    if (!this->target_link_)
    {
      return;
    }

    const ignition::math::Pose3d target_pose =
      this->target_link_->WorldPose() * this->pose_offset_;

    this->model_->SetWorldPose(target_pose);
    this->model_->SetLinearVel(this->target_link_->WorldLinearVel());
    this->model_->SetAngularVel(this->target_link_->WorldAngularVel());
  }

  physics::WorldPtr world_;
  physics::ModelPtr model_;
  physics::ModelPtr target_model_;
  physics::LinkPtr target_link_;
  event::ConnectionPtr update_connection_;
  std::string target_model_name_;
  std::string target_link_name_;
  ignition::math::Pose3d pose_offset_{ignition::math::Pose3d::Zero};
  common::Time last_warn_time_;
};

GZ_REGISTER_MODEL_PLUGIN(RuntimeMountFollowerPlugin)
}  // namespace gazebo
