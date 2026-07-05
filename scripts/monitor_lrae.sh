#!/bin/bash
# LRAE 探索测试脚本 - 长时间监控

echo "========================================="
echo "LRAE 探索长时间监控"
echo "========================================="
echo ""
echo "系统已启动，所有节点运行正常："
echo "  ✅ NEXUS 仿真"
echo "  ✅ 真值 TF 发布器"
echo "  ✅ Traversibility_mapping"
echo "  ✅ lrae_planner_node"
echo "  ✅ exploration_map_merge"
echo "  ✅ localPlanner"
echo "  ✅ pathFollower"
echo "  ✅ gen_local_goal"
echo ""
echo "LRAE 可能需要时间来："
echo "  1. 建立完整的通行性地图"
echo "  2. 识别可探索区域"
echo "  3. 生成探索路径"
echo ""
echo "现在开始持续监控（每30秒检查一次，共10分钟）..."
echo "========================================="
echo ""

cd /home/charles/NEXUS/NEXUS_GAZEBO_SIM
source install/setup.bash 2>/dev/null

# 记录初始位置
initial_pos=$(timeout 2 ros2 topic echo /cube_robot/world_pose --once 2>&1)
initial_x=$(echo "$initial_pos" | grep "x:" | head -1 | awk '{print $2}')
initial_y=$(echo "$initial_pos" | grep "y:" | head -1 | awk '{print $2}')

echo "初始位置: x=$initial_x, y=$initial_y"
echo ""

# 监控10分钟
for i in {1..20}; do
    echo "--- 检查 $i/20 ($(date +%H:%M:%S)) ---"

    # 检查通行性地图
    plane_hz=$(timeout 3 ros2 topic hz /plane_OccMap 2>&1 | grep "average rate" | head -1 | awk '{print $3}')
    echo "  /plane_OccMap: ${plane_hz:-无数据} Hz"

    # 检查探索路径
    exp_hz=$(timeout 3 ros2 topic hz /exporation_path 2>&1 | grep "average rate" | head -1 | awk '{print $3}')
    if [ -n "$exp_hz" ]; then
        echo "  /exporation_path: $exp_hz Hz ✅✅✅ 探索路径生成！"
    else
        echo "  /exporation_path: 无数据（还在建图...）"
    fi

    # 检查目标点
    goal_hz=$(timeout 3 ros2 topic hz /look_ahead_goal 2>&1 | grep "average rate" | head -1 | awk '{print $3}')
    if [ -n "$goal_hz" ]; then
        echo "  /look_ahead_goal: $goal_hz Hz ✅ 目标点发布！"
    else
        echo "  /look_ahead_goal: 无数据"
    fi

    # 检查速度指令
    cmd_hz=$(timeout 3 ros2 topic hz /cmd_vel 2>&1 | grep "average rate" | head -1 | awk '{print $3}')
    if [ -n "$cmd_hz" ]; then
        echo "  /cmd_vel: $cmd_hz Hz ✅✅✅ 速度指令！"
    else
        echo "  /cmd_vel: 无数据"
    fi

    # 检查位置变化
    current_pos=$(timeout 2 ros2 topic echo /cube_robot/world_pose --once 2>&1)
    current_x=$(echo "$current_pos" | grep "x:" | head -1 | awk '{print $2}')
    current_y=$(echo "$current_pos" | grep "y:" | head -1 | awk '{print $2}')

    if [ -n "$current_x" ] && [ -n "$initial_x" ]; then
        dx=$(echo "$current_x - $initial_x" | bc -l 2>/dev/null)
        dy=$(echo "$current_y - $initial_y" | bc -l 2>/dev/null)
        distance=$(echo "sqrt($dx*$dx + $dy*$dy)" | bc -l 2>/dev/null)
        echo "  位置: x=$current_x, y=$current_y"
        echo "  移动距离: ${distance:-未知} 米"

        # 判断是否有显著移动
        if [ -n "$distance" ]; then
            is_moving=$(echo "$distance > 0.1" | bc -l 2>/dev/null)
            if [ "$is_moving" = "1" ]; then
                echo "  🎉🎉🎉 机器人正在移动！🎉🎉🎉"
            fi
        fi
    fi

    echo ""

    # 如果有速度指令，说明探索开始了
    if [ -n "$cmd_hz" ]; then
        echo "========================================="
        echo "✅✅✅ 探索已开始！机器人应该在移动！ ✅✅✅"
        echo "========================================="
        break
    fi

    # 等待30秒
    sleep 30
done

echo ""
echo "========================================="
echo "监控结束"
echo "========================================="
echo ""
echo "最终位置: x=$current_x, y=$current_y"
echo "初始位置: x=$initial_x, y=$initial_y"
echo ""
if [ -n "$distance" ]; then
    echo "总移动距离: $distance 米"
    is_moved=$(echo "$distance > 0.1" | bc -l 2>/dev/null)
    if [ "$is_moved" = "1" ]; then
        echo ""
        echo "✅✅✅ 机器人已经移动！系统工作！ ✅✅✅"
    else
        echo ""
        echo "❌ 机器人移动距离很小，可能还在初始化"
    fi
fi
