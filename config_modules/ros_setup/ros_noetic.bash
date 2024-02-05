#!/bin/bash

# Update sources.list and add ROS key
echo $PASSWORD | sudo -S sh -c 'echo "deb http://packages.ros.org/ros/ubuntu $(lsb_release -sc) main" > /etc/apt/sources.list.d/ros-latest.list'
curl -s https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc | sudo apt-key add -
# TODO: check if the key is successfully added
sudo apt update

# Install ROS Noetic
sudo apt install -y ros-noetic-desktop-full

# Misc installs
sudo apt install -y python3-rosdep
sudo rosdep init && rosdep update
sudo apt install -y python3-rosinstall
# sudo apt install -y python3-roslaunch
sudo apt install -y ros-noetic-roslaunch
sudo apt install -y python3-catkin-tools python3-osrf-pycommon

# Add ROS to bashrc
echo "source /opt/ros/noetic/setup.bash" >> ~/.bashrc
# echo "source /opt/ros/noetic/setup.zsh" >> ~/.zshrc