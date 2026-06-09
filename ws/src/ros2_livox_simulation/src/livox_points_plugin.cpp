#include <rclcpp/rclcpp.hpp>
#include <gazebo_ros/node.hpp>
#include <rclcpp/logging.hpp>

#include <gazebo/physics/Model.hh>
#include <gazebo/physics/MultiRayShape.hh>// Store the latest laser scans into laserMsg
#include <gazebo/physics/PhysicsEngine.hh>
#include <gazebo/physics/World.hh>
#include <gazebo/sensors/RaySensor.hh>
#include <gazebo/transport/Node.hh>
#include <cmath>
#include <chrono>
#include <limits>
#include <cstdint>
#include "ros2_livox/livox_points_plugin.h"
#include "ros2_livox/csv_reader.hpp"
#include "ros2_livox/livox_ode_multiray_shape.h"
#include <livox_ros_driver2/msg/custom_msg.hpp>

namespace gazebo
{
    namespace
    {
        struct LivoxPointXyzitlPacked
        {
            float x;
            float y;
            float z;
            float intensity;
            uint8_t tag;
            uint8_t line;
            uint16_t padding;
        };
    }

    GZ_REGISTER_SENSOR_PLUGIN(LivoxPointsPlugin)

    LivoxPointsPlugin::LivoxPointsPlugin() {}

    LivoxPointsPlugin::~LivoxPointsPlugin() {}

    void convertDataToRotateInfo(const std::vector<std::vector<double>> &datas, std::vector<AviaRotateInfo> &avia_infos)
    {
        avia_infos.reserve(datas.size());
        double deg_2_rad = M_PI / 180.0;
        for (auto &data : datas)
        {
            if (data.size() == 3)
            {
                avia_infos.emplace_back();
                avia_infos.back().time = data[0];
                avia_infos.back().azimuth = data[1] * deg_2_rad;
                avia_infos.back().zenith = data[2] * deg_2_rad - M_PI_2; //转化成标准的右手系角度
            } else {
            RCLCPP_ERROR(rclcpp::get_logger("convertDataToRotateInfo"), "data size is not 3!");
        }
        }
    }

    void LivoxPointsPlugin::Load(gazebo::sensors::SensorPtr _parent, sdf::ElementPtr sdf)
    {
        node_ = gazebo_ros::Node::Get(sdf);
        
        std::vector<std::vector<double>> datas;
        std::string file_name = sdf->Get<std::string>("csv_file_name");
        RCLCPP_INFO(rclcpp::get_logger("LivoxPointsPlugin"), "load csv file name: %s", file_name.c_str());
        if (!CsvReader::ReadCsvFile(file_name, datas))
        {   
            RCLCPP_INFO(rclcpp::get_logger("LivoxPointsPlugin"), "cannot get csv file! %s will return !", file_name.c_str());
            return;
        }
        sdfPtr = sdf;
        auto rayElem = sdfPtr->GetElement("ray");
        auto scanElem = rayElem->GetElement("scan");
        auto rangeElem = rayElem->GetElement("range");


        raySensor = _parent;
        auto sensor_pose = raySensor->Pose();
        auto curr_scan_topic = sdf->Get<std::string>("topic");
        RCLCPP_INFO(rclcpp::get_logger("LivoxPointsPlugin"), "ros topic name: %s", curr_scan_topic.c_str());

        child_name = raySensor->Name();
        parent_name = raySensor->ParentName();
        size_t delimiter_pos = parent_name.find("::");
        parent_name = parent_name.substr(delimiter_pos + 2);

        node = transport::NodePtr(new transport::Node());
        node->Init(raySensor->WorldName());
        // PointCloud2 publisher
        cloud2_pub = node_->create_publisher<sensor_msgs::msg::PointCloud2>(curr_scan_topic + "_PointCloud2", 10);
        // CustomMsg publisher
        custom_pub = node_->create_publisher<livox_ros_driver2::msg::CustomMsg>(curr_scan_topic, 10);

        scanPub = node->Advertise<msgs::LaserScanStamped>(curr_scan_topic+"laserscan", 50);

        aviaInfos.clear();
        convertDataToRotateInfo(datas, aviaInfos);
        RCLCPP_INFO(rclcpp::get_logger("LivoxPointsPlugin"), "scan info size: %ld", aviaInfos.size());
        maxPointSize = aviaInfos.size();

        RayPlugin::Load(_parent, sdfPtr);
        laserMsg.mutable_scan()->set_frame(_parent->ParentName());
        // parentEntity = world->GetEntity(_parent->ParentName());
        parentEntity = this->world->EntityByName(_parent->ParentName());
        //SendRosTf(sensor_pose, raySensor->ParentName(), raySensor->Name());
        auto physics = world->Physics();
        laserCollision = physics->CreateCollision("multiray", _parent->ParentName());
        laserCollision->SetName("ray_sensor_collision");
        laserCollision->SetRelativePose(_parent->Pose());
        laserCollision->SetInitialRelativePose(_parent->Pose());
        rayShape.reset(new gazebo::physics::LivoxOdeMultiRayShape(laserCollision));
        laserCollision->SetShape(rayShape);
        samplesStep = sdfPtr->Get<int>("samples");
        downSample = sdfPtr->Get<int>("downsample");
        if (sdfPtr->HasElement("scan_line_count"))
        {
            scanLineCount = std::max<uint32_t>(1, sdfPtr->Get<unsigned int>("scan_line_count"));
        }
        if (downSample < 1)
        {
            downSample = 1;
        }
        RCLCPP_INFO(rclcpp::get_logger("LivoxPointsPlugin"), "sample: %ld", samplesStep);
        RCLCPP_INFO(rclcpp::get_logger("LivoxPointsPlugin"), "downsample: %ld", downSample);
        rayShape->RayShapes().reserve(samplesStep / downSample);
        rayShape->Load(sdfPtr);
        rayShape->Init();

        // Force sensor active in headless mode; ensure OnNewLaserScans is driven
        auto ray_sensor_ptr = std::dynamic_pointer_cast<gazebo::sensors::RaySensor>(raySensor);
        if (ray_sensor_ptr)
        {
            const double update_rate = ray_sensor_ptr->UpdateRate();
            if (update_rate > 0.0)
            {
                scanPeriodNs = 1e9 / update_rate;
            }
            ray_sensor_ptr->SetActive(true);
            update_connection_ = ray_sensor_ptr->ConnectUpdated(
                std::bind(&LivoxPointsPlugin::OnNewLaserScans, this));
            RCLCPP_INFO(rclcpp::get_logger("LivoxPointsPlugin"), "ray sensor forced active + update callback connected");
        }
        minDist = rangeElem->Get<double>("min");
        maxDist = rangeElem->Get<double>("max");
        auto offset = laserCollision->RelativePose();
        ignition::math::Vector3d start_point, end_point;
        for (int j = 0; j < samplesStep; j += downSample)
        {
            int index = j % maxPointSize;
            auto &rotate_info = aviaInfos[index];
            ignition::math::Quaterniond ray;
            ray.Euler(ignition::math::Vector3d(0.0, rotate_info.zenith, rotate_info.azimuth));
            auto axis = offset.Rot() * ray * ignition::math::Vector3d(1.0, 0.0, 0.0);
            start_point = minDist * axis + offset.Pos();
            end_point = maxDist * axis + offset.Pos();
            rayShape->AddRay(start_point, end_point);
        }
    }
    void LivoxPointsPlugin::OnNewLaserScans()
{
    if (!rayShape) return;

    std::vector<RaySample> points_pair;
    InitializeRays(points_pair, rayShape);
    rayShape->Update();

    // ================================
    // 1. CustomMsg（保持原行为）
    // ================================
    livox_ros_driver2::msg::CustomMsg pp_livox;
    pp_livox.header.stamp = node_->get_clock()->now();
    pp_livox.header.frame_id = raySensor->Name();
    pp_livox.timebase = static_cast<uint64_t>(rclcpp::Time(pp_livox.header.stamp).nanoseconds());
    pp_livox.lidar_id = 0;
    pp_livox.rsvd.fill(0);
    pp_livox.points.reserve(points_pair.size());

    // ================================
    // 2. 直接构造 PointCloud2（关键）
    // ================================
    sensor_msgs::msg::PointCloud2 cloud2;
    cloud2.header.stamp = pp_livox.header.stamp;
    cloud2.header.frame_id = raySensor->Name();

    cloud2.height = 1;
    cloud2.width  = points_pair.size();
    cloud2.is_dense = true;
    cloud2.is_bigendian = false;

    // x y z intensity tag line + padding = 20 bytes
    cloud2.point_step = sizeof(LivoxPointXyzitlPacked);
    cloud2.row_step   = cloud2.point_step * cloud2.width;

    cloud2.fields.resize(6);
    cloud2.fields[0].name = "x";
    cloud2.fields[0].offset = 0;
    cloud2.fields[0].datatype = sensor_msgs::msg::PointField::FLOAT32;
    cloud2.fields[0].count = 1;

    cloud2.fields[1].name = "y";
    cloud2.fields[1].offset = 4;
    cloud2.fields[1].datatype = sensor_msgs::msg::PointField::FLOAT32;
    cloud2.fields[1].count = 1;

    cloud2.fields[2].name = "z";
    cloud2.fields[2].offset = 8;
    cloud2.fields[2].datatype = sensor_msgs::msg::PointField::FLOAT32;
    cloud2.fields[2].count = 1;

    cloud2.fields[3].name = "intensity";
    cloud2.fields[3].offset = 12;
    cloud2.fields[3].datatype = sensor_msgs::msg::PointField::FLOAT32;
    cloud2.fields[3].count = 1;

    cloud2.fields[4].name = "tag";
    cloud2.fields[4].offset = 16;
    cloud2.fields[4].datatype = sensor_msgs::msg::PointField::UINT8;
    cloud2.fields[4].count = 1;

    cloud2.fields[5].name = "line";
    cloud2.fields[5].offset = 17;
    cloud2.fields[5].datatype = sensor_msgs::msg::PointField::UINT8;
    cloud2.fields[5].count = 1;

    cloud2.data.resize(cloud2.row_step);

    uint8_t *dst = cloud2.data.data();
    size_t valid_count = 0;
    const double scan_span_ns = points_pair.size() > 1 ? scanPeriodNs : 0.0;

    // ================================
    // 3. 主循环：一次算完，双消息复用
    // ================================
    for (const auto &sample : points_pair)
    {
        auto range = rayShape->GetRange(sample.ray_index);
        auto intensity = rayShape->GetRetro(sample.ray_index);

        if (range <= RangeMin() || range >= RangeMax())
            continue;

        const auto &rotate_info = sample.rotate_info;
        ignition::math::Quaterniond ray;
        ray.Euler({0.0, rotate_info.zenith, rotate_info.azimuth});
        auto axis = ray * ignition::math::Vector3d(1.0, 0.0, 0.0);
        auto point = range * axis;
        const uint8_t line = static_cast<uint8_t>(((sample.scan_sample_index / downSample) % scanLineCount));
        const uint64_t point_offset_ns = static_cast<uint64_t>(std::llround(
            scan_span_ns * static_cast<double>(sample.scan_sample_index) /
            static_cast<double>(std::max<int64_t>(1, samplesStep - 1))));

        // ---- PointCloud2 ----
        auto *p = reinterpret_cast<LivoxPointXyzitlPacked *>(
            dst + valid_count * cloud2.point_step);
        p->x = point.X();
        p->y = point.Y();
        p->z = point.Z();
        p->intensity = static_cast<float>(intensity);
        p->tag = 0;
        p->line = line;
        p->padding = 0;

        // ---- CustomMsg ----
        livox_ros_driver2::msg::CustomPoint cp;
        cp.x = p->x;
        cp.y = p->y;
        cp.z = p->z;
        cp.reflectivity = intensity;
        cp.tag = 0;
        cp.line = line;
        cp.offset_time = static_cast<uint32_t>(
            point_offset_ns > std::numeric_limits<uint32_t>::max()
                ? std::numeric_limits<uint32_t>::max()
                : point_offset_ns);

        pp_livox.points.push_back(cp);
        valid_count++;
    }

    // ================================
    // 4. 收尾 & 发布
    // ================================
    cloud2.width = valid_count;
    cloud2.row_step = cloud2.point_step * valid_count;
    cloud2.data.resize(cloud2.row_step);

    pp_livox.point_num = valid_count;

    custom_pub->publish(pp_livox);
    cloud2_pub->publish(cloud2);
}

  

    void LivoxPointsPlugin::InitializeRays(std::vector<RaySample> &points_pair,
                                           boost::shared_ptr<physics::LivoxOdeMultiRayShape> &ray_shape)
    {
        auto &rays = ray_shape->RayShapes();
        ignition::math::Vector3d start_point, end_point;
        ignition::math::Quaterniond ray;
        auto offset = laserCollision->RelativePose();
        int64_t end_index = currStartIndex + samplesStep;
        long unsigned int ray_index = 0;
        auto ray_size = rays.size();
        points_pair.reserve(rays.size());
        for (int k = currStartIndex; k < end_index; k += downSample)
        {
            auto index = k % maxPointSize;
            auto &rotate_info = aviaInfos[index];
            ray.Euler(ignition::math::Vector3d(0.0, rotate_info.zenith, rotate_info.azimuth));
            auto axis = offset.Rot() * ray * ignition::math::Vector3d(1.0, 0.0, 0.0);
            start_point = minDist * axis + offset.Pos();
            end_point = maxDist * axis + offset.Pos();
            if (ray_index < ray_size)
            {
                rays[ray_index]->SetPoints(start_point, end_point);
                points_pair.push_back({static_cast<int>(ray_index), static_cast<uint32_t>(k - currStartIndex), rotate_info});
            }
            ray_index++;
        }
        currStartIndex += samplesStep;
    }

    void LivoxPointsPlugin::InitializeScan(msgs::LaserScan *&scan)
    {
        // Store the latest laser scans into laserMsg
        msgs::Set(scan->mutable_world_pose(), raySensor->Pose() + parentEntity->WorldPose());
        scan->set_angle_min(AngleMin().Radian());
        scan->set_angle_max(AngleMax().Radian());
        scan->set_angle_step(AngleResolution());
        scan->set_count(RangeCount());

        scan->set_vertical_angle_min(VerticalAngleMin().Radian());
        scan->set_vertical_angle_max(VerticalAngleMax().Radian());
        scan->set_vertical_angle_step(VerticalAngleResolution());
        scan->set_vertical_count(VerticalRangeCount());

        scan->set_range_min(RangeMin());
        scan->set_range_max(RangeMax());

        scan->clear_ranges();
        scan->clear_intensities();

        unsigned int rangeCount = RangeCount();
        unsigned int verticalRangeCount = VerticalRangeCount();

        for (unsigned int j = 0; j < verticalRangeCount; ++j)
        {
            for (unsigned int i = 0; i < rangeCount; ++i)
            {
                scan->add_ranges(0);
                scan->add_intensities(0);
            }
        }
    }

    ignition::math::Angle LivoxPointsPlugin::AngleMin() const
    {
        if (rayShape)
            return rayShape->MinAngle();
        else
            return -1;
    }

    ignition::math::Angle LivoxPointsPlugin::AngleMax() const
    {
        if (rayShape)
        {
            return ignition::math::Angle(rayShape->MaxAngle().Radian());
        }
        else
            return -1;
    }

    double LivoxPointsPlugin::GetRangeMin() const { return RangeMin(); }

    double LivoxPointsPlugin::RangeMin() const
    {
        if (rayShape)
            return rayShape->GetMinRange();
        else
            return -1;
    }

    double LivoxPointsPlugin::GetRangeMax() const { return RangeMax(); }

    double LivoxPointsPlugin::RangeMax() const
    {
        if (rayShape)
            return rayShape->GetMaxRange();
        else
            return -1;
    }

    double LivoxPointsPlugin::GetAngleResolution() const { return AngleResolution(); }

    double LivoxPointsPlugin::AngleResolution() const { return (AngleMax() - AngleMin()).Radian() / (RangeCount() - 1); }

    double LivoxPointsPlugin::GetRangeResolution() const { return RangeResolution(); }

    double LivoxPointsPlugin::RangeResolution() const
    {
        if (rayShape)
            return rayShape->GetResRange();
        else
            return -1;
    }

    int LivoxPointsPlugin::GetRayCount() const { return RayCount(); }

    int LivoxPointsPlugin::RayCount() const
    {
        if (rayShape)
            return rayShape->GetSampleCount();
        else
            return -1;
    }

    int LivoxPointsPlugin::GetRangeCount() const { return RangeCount(); }

    int LivoxPointsPlugin::RangeCount() const
    {
        if (rayShape)
            return rayShape->GetSampleCount() * rayShape->GetScanResolution();
        else
            return -1;
    }

    int LivoxPointsPlugin::GetVerticalRayCount() const { return VerticalRayCount(); }

    int LivoxPointsPlugin::VerticalRayCount() const
    {
        if (rayShape)
            return rayShape->GetVerticalSampleCount();
        else
            return -1;
    }

    int LivoxPointsPlugin::GetVerticalRangeCount() const { return VerticalRangeCount(); }

    int LivoxPointsPlugin::VerticalRangeCount() const
    {
        if (rayShape)
            return rayShape->GetVerticalSampleCount() * rayShape->GetVerticalScanResolution();
        else
            return -1;
    }

    ignition::math::Angle LivoxPointsPlugin::VerticalAngleMin() const
    {
        if (rayShape)
        {
            return ignition::math::Angle(rayShape->VerticalMinAngle().Radian());
        }
        else
            return -1;
    }

    ignition::math::Angle LivoxPointsPlugin::VerticalAngleMax() const
    {
        if (rayShape)
        {
            return ignition::math::Angle(rayShape->VerticalMaxAngle().Radian());
        }
        else
            return -1;
    }

    double LivoxPointsPlugin::GetVerticalAngleResolution() const { return VerticalAngleResolution(); }

    double LivoxPointsPlugin::VerticalAngleResolution() const
    {
        return (VerticalAngleMax() - VerticalAngleMin()).Radian() / (VerticalRangeCount() - 1);
    }


}
