cmake_minimum_required(VERSION 3.5)
project(nexus_fastlio)

find_package(ament_cmake REQUIRED)

# Install Python scripts
install(PROGRAMS
  scripts/fastlio_imu_adapter.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME fastlio_imu_adapter
)
install(PROGRAMS
  scripts/fastlio_lidar_adapter.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME fastlio_lidar_adapter
)

# Install config files
install(DIRECTORY config/
  DESTINATION share/${PROJECT_NAME}/config
)

ament_package()
