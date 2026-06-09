#!/usr/bin/env python3

from controller_manager import (
    configure_controller,
    list_controllers,
    load_controller,
    switch_controllers,
)
import rclpy
from rclpy.node import Node


class OmniControllerSpawner(Node):
    def __init__(self) -> None:
        super().__init__("spawn_omni_controllers")
        self.controller_manager = str(
            self.declare_parameter("controller_manager", "/controller_manager").value
        )
        self.controller_manager_timeout = float(
            self.declare_parameter("controller_manager_timeout", 180.0).value
        )
        self.service_call_timeout = float(
            self.declare_parameter("service_call_timeout", 180.0).value
        )
        self.switch_timeout = float(self.declare_parameter("switch_timeout", 180.0).value)
        raw_controllers = self.declare_parameter(
            "controllers",
            [
                "joint_state_broadcaster",
                "steering_position_controller",
                "wheel_velocity_controller",
            ],
        ).value
        self.controllers = [str(name) for name in raw_controllers]

    def _controller_states(self) -> dict[str, str]:
        response = list_controllers(
            self,
            self.controller_manager,
            self.controller_manager_timeout,
            self.service_call_timeout,
        )
        return {controller.name: controller.state for controller in response.controller}

    def run(self) -> int:
        self.get_logger().info(
            "spawning omni controllers via %s with %.1fs service timeout"
            % (self.controller_manager, self.service_call_timeout)
        )

        states = self._controller_states()
        for controller_name in self.controllers:
            if controller_name not in states:
                result = load_controller(
                    self,
                    self.controller_manager,
                    controller_name,
                    self.controller_manager_timeout,
                    self.service_call_timeout,
                )
                if not result.ok:
                    self.get_logger().error("failed to load %s" % controller_name)
                    return 1
                self.get_logger().info("loaded %s" % controller_name)
                states = self._controller_states()

            if states.get(controller_name) == "unconfigured":
                result = configure_controller(
                    self,
                    self.controller_manager,
                    controller_name,
                    self.controller_manager_timeout,
                    self.service_call_timeout,
                )
                if not result.ok:
                    self.get_logger().error("failed to configure %s" % controller_name)
                    return 1
                self.get_logger().info("configured %s" % controller_name)
                states = self._controller_states()

        activate = [
            controller_name
            for controller_name in self.controllers
            if states.get(controller_name) != "active"
        ]
        if activate:
            result = switch_controllers(
                self,
                self.controller_manager,
                [],
                activate,
                strict=True,
                activate_asap=True,
                timeout=self.switch_timeout,
                call_timeout=self.service_call_timeout,
            )
            if not result.ok:
                self.get_logger().error("failed to activate controllers: %s" % ", ".join(activate))
                return 1
            self.get_logger().info("activated controllers: %s" % ", ".join(activate))

        final_states = self._controller_states()
        for controller_name in self.controllers:
            self.get_logger().info(
                "controller %s state=%s"
                % (controller_name, final_states.get(controller_name, "missing"))
            )
        return 0


def main() -> None:
    rclpy.init()
    node = OmniControllerSpawner()
    exit_code = 1
    try:
        exit_code = node.run()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
