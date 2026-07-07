#pragma once

#include "voxblox_msgs/msg/block.hpp"
#include "voxblox_msgs/msg/layer.hpp"
#include "voxblox_msgs/msg/mesh.hpp"
#include "voxblox_msgs/msg/mesh_block.hpp"
#include "voxblox_msgs/msg/voxel_evaluation_details.hpp"
#include "voxblox_msgs/srv/file_path.hpp"

namespace voxblox_msgs {

using Block = msg::Block;
using Layer = msg::Layer;
using Mesh = msg::Mesh;
using MeshBlock = msg::MeshBlock;
using VoxelEvaluationDetails = msg::VoxelEvaluationDetails;

using FilePath = srv::FilePath;

}  // namespace voxblox_msgs
