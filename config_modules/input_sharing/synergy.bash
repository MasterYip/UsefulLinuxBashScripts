#!/bin/bash
wget -O /tmp/synergy.deb  http://archive.ubuntu.com/ubuntu/pool/universe/s/synergy/synergy_1.8.8-stable+dfsg.1-1build1_amd64.deb
# echo $PASSWORD | sudo -S apt install /tmp/synergy.deb
echo $PASSWORD | sudo -S add-apt-repository ppa:rock-core/qt4
echo $PASSWORD | sudo -S apt-get update
echo $PASSWORD | sudo -S apt-get install -y libcanberra-gtk-module
echo $PASSWORD | sudo -S dpkg -i /tmp/synergy.deb
echo $PASSWORD | sudo -S apt-get -f install
# FIXME: use -y for the last line?