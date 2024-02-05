function install_package(){
    # $1: package name
    # $2: package installation command
    if ! command -v $1 > /dev/null; then
        echo "$1 is not installed. Installing..."
        echo $PASSWORD | sudo -S apt install $1
    else
        echo "$1 is already installed."
    fi
}

