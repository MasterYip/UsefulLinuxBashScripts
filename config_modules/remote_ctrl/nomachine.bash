#!/bin/bash
wget -O /tmp/nomachine.deb https://download.nomachine.com/download/8.11/Linux/nomachine_8.11.3_4_amd64.deb
echo $PASSWORD | sudo -S apt install /tmp/nomachine.deb