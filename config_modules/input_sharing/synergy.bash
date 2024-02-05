#!/bin/bash
wget -O /tmp/synergy.deb  http://archive.ubuntu.com/ubuntu/pool/universe/s/synergy/synergy_1.8.8-stable+dfsg.1-1build1_amd64.deb
# echo $PASSWORD | sudo -S apt install /tmp/synergy.deb
echo $PASSWORD | sudo -S add-apt-repository ppa:rock-core/qt4
sudo apt-get update
sudo apt-get install libcanberra-gtk-module
sudo dpkg -i /tmp/synergy.deb
sudo apt-get -f install