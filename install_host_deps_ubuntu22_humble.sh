#!/usr/bin/env bash
set -euo pipefail

echo "[INFO] This script installs the host dependencies for the no-docker source version."
echo "[INFO] It does NOT install Livox-SDK2 automatically. Please install that separately if missing."

sudo apt update
sudo apt install -y \
  build-essential cmake git pkg-config curl \
  python3-colcon-common-extensions python3-rosdep python3-vcstool \
  gazebo libgazebo-dev \
  ros-humble-desktop \
  ros-humble-gazebo-ros-pkgs \
  ros-humble-gazebo-plugins \
  ros-humble-gazebo-msgs \
  ros-humble-robot-state-publisher \
  ros-humble-controller-manager \
  ros-humble-ros2-controllers \
  ros-humble-joint-state-broadcaster \
  ros-humble-velocity-controllers \
  ros-humble-xacro \
  libeigen3-dev libpcl-dev \
  libapr1-dev libprotobuf-dev protobuf-compiler \
  libboost-chrono-dev libboost-system-dev libboost-thread-dev \
  python3-pygame python3-opencv python3-numpy

echo "[OK] Host apt dependencies installed."
echo "[NEXT] If needed, install Livox-SDK2 into /usr/local and run sudo ldconfig."
