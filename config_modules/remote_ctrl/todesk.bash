wget -O /tmp/todesk.deb https://newdl.todesk.com/linux/todesk-v4.3.1.0-amd64.deb
echo $PASSWORD | sudo -S apt install /tmp/todesk.deb
