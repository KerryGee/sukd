**Latest Ubuntu Upstream Kernel Downloader Python Script**

AUTHOR: Kerem Gümrükcü  
EMAIL: kerem.g@arcor.de  
LICENSE: MIT-License  

**DESCRIPTION:** Nice little python script to facilitate the download (and installation if you like) of the latest public stable kernel DEB packages from the Ubuntu usptream kernels archive in "http://kernel.ubuntu.com/~kernel-ppa/mainline/". For those who want or need to run the latest stable kernel on their ubuntu-based systems. Successfully tested on 14.04 and 16.04 ubuntu and ubuntu-based systems like kubuntu, lubuntu, xubuntu, etc. with installed python 2.7 and 3.5 who are already installed on most linux systems including all ubuntu-based and based fork systems. This script will likely run on any Linux system that comes with python 2.7+.

**HOW IT WORKS:** The script pulls the latest stable kernel version information from the official linux kernel archive "https://www.kernel.org/" by accessing the "https://www.kernel.org/releases.json" JSON file and extracts the latest stable kernel version number. Afterwards it contacts the ubuntu upstream kernel archives online directory "http://kernel.ubuntu.com/~kernel-ppa/mainline/" to switch into the actual stable kernel version directory with the DEB files, for instance the "4.9.6" directory and parses the "CHECKSUMS" file contents to build a pretty little menu for the selection of all the available kernel flavors and architectures you could get from that directory. After selecting what DEB files for what architecture and flavor you exactly want, the application uses either wget or curl to download the selected files. If there is no wget or curl available, it will use its internal downloader. After successfully downloading the files, they will be checked against their SHA1 sum from the online CHECKSUMS file. If you run the script as root, you will be optionally asked, whether you would like to install the DEB kernel files with "dpkg" and finally reboot into your new kernel. But this step is optional and comes only with the script executed with root permissions.

**!!! WARNING:** You should exactly know what you are doing now, since a new or wrong kernel can render your system entirely useless or instable if something fails or the kernel has bugs. Remember that these kernels are not supported from Ubuntu and are not appropriate for production use. **YOU HAVE BEEN WARNED!!!**

**WHERE ARE THE DOWNLOADED FILES:** The downloaded files will be placed in your home directory under "~/Downloads/StableUpstreamKernels/". They will be grouped by ``"/Downloads/StableUpstreamKernels/<version>/<architecture>/<flavor>/*.deb"``. Any missing directories/sub-directories will be created on demand. If you want to force the script to download any specific kernel version and/or download into a specific directory, you could set these variables in the script to:

```python
##########################
# User defined variables #
##########################
# force the script to use this version
# FORCE_KERNEL_VERSION = "4.9.6"
FORCE_KERNEL_VERSION = None
# force the script to use this absolute location
# FORCE_DOWNLOAD_LOCATION = "/tmp/Downloads"
FORCE_DOWNLOAD_LOCATION = None
```

**DO I NEED TO RUN THE SCRIPT AS ROOT:** No, you dont need to run the script as root. You only need the permissions to run the python script and the permissions to download the file into your home directory. These permissions are already granted by design. You can install the kernel DEB files later.

Thats it! It makes dowloading the latest stable kernel DEB packages from the Ubuntu Upstream kernels archive a breeze.

Have fun.

K. 
