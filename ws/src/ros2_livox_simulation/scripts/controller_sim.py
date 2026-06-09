#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import Float64MultiArray

import pygame


class PygameWASDController(Node):
    def __init__(self):
        super().__init__('pygame_wasd_controller')

        # ---------- ROS2 Publisher ----------
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.pub = self.create_publisher(
            Float64MultiArray,
            '/rear_wheel_velocity_controller/commands',
            qos
        )

        # ---------- 运动参数（轮速 rad/s） ----------
        self.v = 0.0          # 前进分量（左右同号）
        self.w = 0.0          # 原地转向分量（左右异号）
        self.v_acc = 0.35     # 长按每帧加速度（越大越“猛”）
        self.w_acc = 0.45
        self.max_v = 10.0
        self.max_w = 10.0

        # 松手衰减（越接近1越“滑”，越小越“立停”）
        self.v_decay = 0.92
        self.w_decay = 0.85

        # ---------- pygame ----------
        pygame.init()
        pygame.display.set_caption("WASD Robot Controller (Skid-Steer)")
        self.screen = pygame.display.set_mode((420, 230))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("monospace", 16)

        # 让“按住键”也能触发（有的系统需要这个）
        pygame.key.set_repeat(1, 1)

        self.get_logger().info("Pygame WASD controller started")

    def clamp(self, x, lo, hi):
        return max(lo, min(x, hi))

    def publish_wheels(self):
        # ✅ 你要的逻辑：
        # - 前进：四轮同号（v）
        # - 转弯（原地转）：左轮 +w，右轮 -w （相反号）
        v_left = self.v + self.w
        v_right = self.v - self.w

        v_left = self.clamp(v_left, -self.max_v, self.max_v)
        v_right = self.clamp(v_right, -self.max_v, self.max_v)

        msg = Float64MultiArray()
        # 四轮 skid-steer：LF, RF, LR, RR（左边=LF/LR，右边=RF/RR）
        msg.data = [-v_left, -v_right, -v_left, -v_right]
        self.pub.publish(msg)

    def draw_ui(self):
        self.screen.fill((30, 30, 30))
        lines = [
            "Hold keys (no Enter):",
            "W/S : forward / back (all wheels same sign)",
            "A/D : spin left/right (left +, right -)",
            "SPACE : stop",
            f"v(forward) = {self.v:.2f}   w(spin) = {self.w:.2f}",
            f"LF/LR = v+w = {(self.v + self.w):.2f}   RF/RR = v-w = {(self.v - self.w):.2f}",
        ]
        y = 18
        for t in lines:
            surf = self.font.render(t, True, (220, 220, 220))
            self.screen.blit(surf, (14, y))
            y += 26
        pygame.display.flip()

    def run(self):
        running = True
        while running and rclpy.ok():
            # --- 处理退出/急停等离散事件 ---
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        self.v = 0.0
                        self.w = 0.0

            # --- ✅ 关键：每帧读取按键状态，长按持续生效 ---
            keys = pygame.key.get_pressed()

            if keys[pygame.K_w]:
                self.v += self.v_acc
            if keys[pygame.K_s]:
                self.v -= self.v_acc

            if keys[pygame.K_a]:
                self.w += self.w_acc    # 左转：左轮更正、右轮更负
            if keys[pygame.K_d]:
                self.w -= self.w_acc

            # 限幅
            self.v = self.clamp(self.v, -self.max_v, self.max_v)
            self.w = self.clamp(self.w, -self.max_w, self.max_w)

            # 松手衰减（只有在没按对应方向键时衰减更合理，但先用简版）
            if not (keys[pygame.K_w] or keys[pygame.K_s]):
                self.v *= self.v_decay
            if not (keys[pygame.K_a] or keys[pygame.K_d]):
                self.w *= self.w_decay

            self.publish_wheels()
            self.draw_ui()
            self.clock.tick(30)  # 30 Hz

        pygame.quit()


def main():
    rclpy.init()
    node = PygameWASDController()
    try:
        node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
