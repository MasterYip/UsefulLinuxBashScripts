#!/bin/bash
source $PRJ_ROOT/auto_config_lib/utils/install_package.bash

# Debug
install_package net-tools
install_package ssh
install_package wget
install_package curl
install_package terminator
install_package tree
install_package mlocate

# Edit
install_package vim
install_package gedit

# Coding
install_package git
install_package cmake
install_package build-essential
