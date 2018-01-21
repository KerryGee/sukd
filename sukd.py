#!/usr/bin/env python
# -*- coding: utf-8 -*-

# treat all strings as unicode
from __future__ import unicode_literals

"""Stable Upstream kernel downloader.

This script aids you in downloading the latest stable Upstream kernel
DEB packages from the ubuntu mainline kernel archive in "http://kernel.ubuntu.com/~kernel-ppa/mainline"
by offering you several options like available architecture (amd64, i386,...) and flavors like
generic, lowlatency, etc. The downloaded files will be checked against the CHECKSUMS file from
the online mainline upstream kernel archive directory and will be grouped by version number,
architecture, flavor like:

[UserHome]
    |
    |--[Downloads]
            |
            |--[StableUpstreamKernels]
                     |
                     |--<KernelVersion>
                                |
                                |--<KernelArchitecture>
                                        |
                                        |--<KernelFlavor>
                                                |- *.deb
                                                |- *.deb
                                                |- ...

This could look like this on your file systemm:

/home/username/Downloads/StableUpstreamKernels/v4.9.5/amd64/generic/*.deb

~/username
    |
    |--Downloads
            |
            |--StableUpstreamKernels
                     |
                     |--v4.9.5
                          |
                          |--amd64
                              |
                              |--generic
                                    |- *.deb
                                    |- *.deb
                                    |- ...


Example:
    Simply run the script the way you want and from wherever you
    placed it like one of these:

        $ python sukd.py
        $ python2 sukd.py
        $ python3 sukd.py

    If you set the "chmod +x sukd.py" on the file, you can run it like:

        $ sukd.py

    or remove the file ending after making it executable, so you can
    simply run it like:

        $ sukd

    and it will just work.

"""

import distutils.spawn
import io
import itertools
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib
import fcntl
import socket

# conditional import of
# required modules
try:
    from shlex import quote
except ImportError:
    from pipes import quote

try:
    from urllib import request
    from urllib import error
except:
    pass

__author__ = "Kerem Gümrükcü"
__copyright__ = "Copyright 2017, Kerem Gümrükcü"
__credits__ = ["Kerem Gümrükcü", "AyVa74"]
__license__ = "MIT"
__email__ = "kerem.g@arcor.de"
__status__ = "Experimental"

#########################
# Source URI constants #
#########################
LATEST_KERNEL_VERSION_JSON_URL = "https://www.kernel.org/releases.json"
LATEST_UPSTREAM_KERNELS_ARCHIVE_URL = "http://kernel.ubuntu.com/~kernel-ppa/mainline"

####################################
# User download location constants #
####################################
USER_DOWNLOAD_PACKAGES_FOLDER = "StableUpstreamKernels"
USER_HOME_DOWNLOAD_DIRECTORY = "Downloads"

##########################
# User defined variables #
##########################
# force the script to use this version
# FORCE_KERNEL_VERSION = "4.9.6"
FORCE_KERNEL_VERSION = None
# force the script to use this absolute location
# FORCE_DOWNLOAD_LOCATION = "/root/Downloads"
FORCE_DOWNLOAD_LOCATION = None
# servers to probe internet
# connection availability
SERVERS_TO_PROBE_FOR_CONNECTION = ["www.ubuntu.com", "www.kernel.org", "www.gnu.org"]  # servers to probe
SERVER_PORT_TO_PROBE = 80  # ports to probe
SERVER_TIMEOUT_CYCLES_IN_SEC = [1, 5, 10]  # seconds to timeout

########################
# Application binaries #
########################
SHA1SUM_BIN_FILE = "sha1sum"
DPKG_BIN_FILE = "dpkg"
DPKG_LOCK_FILE = "/var/lib/dpkg/lock"
DPKG_BIN_FILE_PARAMS = "-i"
DOWNLOAD_TOOLS = {"wget": '-O "{0}" "{1}"', "curl": '-o "{0}" "{1}"'}  # {0} = destination, {1} = online source

####################
# Global constants #
####################
TRUE_STRING = " true."
FALSE_STRING = " false."
YES_STRING = " yes."
NO_STRING = " no."
SUCCESS_STRING = " success."
PASSED_STRING = " passed."
FAILED_STRING = " failed."
FINISHED_STRING = " finished."
MISSING_STRING = " missing."
AVAILABLE_STRING = " available."
SKIPPED_STRING = " skipped."
YES_NO = {1: "Yes", 2: "No"}
YES_NO_ABORT_MAP = {"y": "Yes", "yes": "Yes", "n": "No", "no": "No", "a": "Abort", "abort": "Abort"}
YES_PRESSED = 1
NO_PRESSED = 2
CANCEL_PRESSED = 0
ABORT_PRESSED = CANCEL_PRESSED
STATE_TRUE = 1
STATE_FALSE = 0
STATE_UNKNOWN = 2
PYTHON_MAJOR_VERSION = sys.version_info[0]
IS_PYTHON3 = (PYTHON_MAJOR_VERSION == 3)

####################
# Fixed file names #
####################
CHECKSUMS_FILE = "CHECKSUMS"

####################
# Global bin paths #
####################
sha1sum_bin_file_full_path = None
dpkg_bin_file_full_path = None
downloader_bin_full_path_and_param = None

#########################
# Global user variables #
#########################
user_home_directory = os.path.expanduser("~")
user_home_download_directory = os.path.join(user_home_directory, USER_HOME_DOWNLOAD_DIRECTORY)
user_kernel_package_download_dir = os.path.join(user_home_download_directory, USER_DOWNLOAD_PACKAGES_FOLDER)
user_downloaded_kernel_deb_files = list()

##########################################
# Global OS/Kernel environment variables #
##########################################
os_linux_architecture = platform.machine()
os_linux_platform = platform.platform()
os_python_version = sys.version.split()[0]

###############################
# Downloaded kernel info data #
###############################
latest_stable_kernel_version = None
latest_stable_kernel_checksums_file = None
kernel_hashes_and_files = dict()
kernel_available_architectures = list()
kernel_available_flavors = list()


##################
# Global classes #
##################
class SpinningProgress:
    spinner_thread = None
    abort_progress_sentinel = None
    spinner_thread_running = None
    progress_states = ['\\', '|', '/', '-']

    def __init__(self):
        self.spinner_thread_running = False
        self.progress_indicator = itertools.cycle(self.progress_states)

    def start(self):
        if not self.abort_progress_sentinel:
            self.abort_progress_sentinel = False
            self.spinner_thread = threading.Thread(target=self.run_progress_indicator)
            self.spinner_thread.start()

    def stop(self):
        self.abort_progress_sentinel = True

    def run_progress_indicator(self):
        self.spinner_thread_running = True
        print_nlb(" ")
        while not self.abort_progress_sentinel:
            if IS_PYTHON3:
                print_nlb(next(self.progress_indicator))
            else:
                print_nlb(self.progress_indicator.next())
            time.sleep(0.1)
            print_nlb("\b")

        print_nlb("\b")
        self.spinner_thread_running = False


class WebFileDownloadError(Exception):
    def __init__(self, arg):
        # Set some exception information
        self.errmsg = arg


###########################
# Global object instances #
###########################
progress_spinner = SpinningProgress()


###################
# Global functions
###################

def print_elb():
    sys.stdout.write(os.linesep)
    sys.stdout.flush()


def print_nelb(n):
    for i in range(0, n - 1):
        sys.stdout.write(os.linesep)
        sys.stdout.flush()


def print_lb(string):
    sys.stdout.write(string + os.linesep)
    sys.stdout.flush()


def read_ch():
    ret = sys.stdin.read(1)
    sys.stdin.flush()
    return ret


def read_ln():
    ret = sys.stdin.readline()
    sys.stdin.flush()
    return ret


def print_nlb(string):
    sys.stdout.write(string)
    sys.stdout.flush()


def start_progress_spinner():
    progress_spinner.start()


def stop_progress_spinner():
    if progress_spinner.spinner_thread_running:
        progress_spinner.stop()
        progress_spinner.spinner_thread.join()


def strlen_unicode(s):
    return len(s.encode('utf-8'))


def string_to_unicode(string):
    if IS_PYTHON3:  # running python 3
        return str(string)
    else:  # running python 2
        return unicode(string)


def exit_script(n):
    sys.exit(n)


def is_internet_available():
    try:
        for server_address in SERVERS_TO_PROBE_FOR_CONNECTION:
            for connection_timeout in SERVER_TIMEOUT_CYCLES_IN_SEC:
                try:
                    socket.setdefaulttimeout(connection_timeout)
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect((socket.gethostbyname(server_address), SERVER_PORT_TO_PROBE))
                    s.close()
                    return [server_address, SERVER_PORT_TO_PROBE]
                except:
                    pass

        return None

    except:
        return None


def download_file(
        fromurl,
        tofile):
    try:  # use the system available download tools
        # if its not none
        if downloader_bin_full_path_and_param is not None:
            print_elb()
            # get the bin and command line params
            download_tool = [downloader_bin_full_path_and_param[0]]
            download_tool = download_tool + shlex.split(downloader_bin_full_path_and_param[1].format(tofile, fromurl))
            print_elb()
            ret = execute_process_wait_get_returncode(download_tool)
            print_elb()
            return not ret
        else:
            if IS_PYTHON3:
                source_url = urllib.request.URLopener()
            else:
                source_url = urllib.URLopener()

            source_url.retrieve(fromurl, tofile)
        return True
    except:
        return False


def open_webfile_get_response(fileuri):
    try:
        if IS_PYTHON3:
            try:

                return [200, urllib.request.urlopen(fileuri).read().decode()]

            except urllib.error.HTTPError as e:
                return [e.code, None]
            except urllib.error.URLError as e:
                return [e.code, None]
        else:
            response = urllib.urlopen(fileuri)
            return [response.getcode(), response.read()]
    except:
        return [0, None]


def get_string_unicode_stream(string):
    try:
        return io.StringIO(string_to_unicode(string))
    except:
        return None


def get_string_index(string, index):
    if IS_PYTHON3:
        return str.index(string, index)
    else:
        return unicode.index(string, index)


def execute_process_wait_get_returncode(
        params):
    try:
        return subprocess.check_call(params)
    except subprocess.CalledProcessError as cerr:
        return cerr.returncode


def execute_process_wait_get_output(
        params):
    try:
        return subprocess.Popen(
            params,
            stdout=subprocess.PIPE).communicate()[0].split()[0].decode()
    except:
        return None


def request_user_yes_no_abort_script():
    invalid_input = True

    request_valid_char_message = "Please enter [Y]es, [N]o, or [A]bort and press Enter to confirm: "
    your_decision_was = "Your decision was: "

    print_nlb(request_valid_char_message)

    while invalid_input:

        invalid_input = False

        user_input_line = read_ln().rstrip().lower()
        print_lb(os.linesep + "Your selection: " + user_input_line)

        if user_input_line not in "yna" and user_input_line not in ["yes", "no", "abort"]:
            print_nlb(os.linesep + "Invalid input made. " + request_valid_char_message)
            invalid_input = True
        else:
            if user_input_line == "a" or user_input_line == "abort":
                print_elb()
                print_lb(your_decision_was + YES_NO_ABORT_MAP[user_input_line])
                print_elb()
                print_lb("Abort script selected. Terminating script. Have a nice day." + os.linesep)
                exit_script(1)
            elif user_input_line == "y" or user_input_line == "yes":
                print_elb()
                print_lb(your_decision_was + YES_NO_ABORT_MAP[user_input_line] + os.linesep)
                return YES_PRESSED
            elif user_input_line == "n" or user_input_line == "no":
                print_elb()
                print_lb(your_decision_was + YES_NO_ABORT_MAP[user_input_line] + os.linesep)
                return NO_PRESSED
            else:
                invalid_input = True

        # fine, set exit sentinel
        if not invalid_input:
            break


def request_user_input_number_exit_on_fail(
        objects_to_enumerate,
        max_input_number,
        max_digit_len):
    invalid_input = True

    request_valid_number_message = "Please enter a valid numeric value between {0} and {1}.".format(0, max_input_number)

    objects_to_enumerate = ["Abort script"] + objects_to_enumerate

    while invalid_input:
        # print object decisions available
        for i, obj in enumerate(objects_to_enumerate):
            print_lb("[{0}] = {1}".format(i, obj))

        invalid_input = False

        print_elb()
        print_nlb("Your selection: ")
        user_input_number = read_ln().rstrip()

        if not user_input_number.isdigit():
            print_lb("Not a number entered. " + request_valid_number_message + os.linesep)
            invalid_input = True
        else:
            if int(user_input_number) < 0 or \
                            int(user_input_number) > max_input_number or \
                            strlen_unicode(str(user_input_number)) > max_digit_len:
                print_lb("Out of range number selected. " + request_valid_number_message + os.linesep)
                invalid_input = True

                # exit if cancel
                # zero is always cancel
            if int(user_input_number) is 0:
                print_elb()
                print_lb("Abort script selected. Terminating script. Have a nice day." + os.linesep)
                exit_script(1)

        # fine, set exit sentinel
        if not invalid_input:
            break

    return int(user_input_number) - 1


def get_file_size(filename):
    try:
        return os.path.getsize(filename)
    except Exception as err:
        return "Error: " + err.message


def is_directory_empty(dir_path):
    return os.listdir(dir_path) == []


def is_file_locked(filename):
    try:
        fp = open(filename, 'w')

        # try to put a exclusive lock
        # on the file, on fail its very
        # likely locked in some way
        fcntl.lockf(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.lockf(fp, fcntl.F_UNLCK)

        return STATE_FALSE
    except:
        return STATE_TRUE


def delete_files_in_directory(dirpath, delete_subdirs):
    for file_obj in os.listdir(dirpath):
        file_obj_path = os.path.join(dirpath, file_obj)
        try:
            if os.path.isfile(file_obj_path):
                os.unlink(file_obj_path)
            if delete_subdirs:
                if os.path.isdir(file_obj_path):
                    shutil.rmtree(file_obj_path, True)
        except:
            pass


def find_position_of_nth_string_occurence(targetstr, char, nthpos):
    count = int(0)
    if IS_PYTHON3:
        if strlen_unicode(str(targetstr)) == 0:
            return 0
    else:
        if strlen_unicode(unicode(targetstr)) == 0:
            return 0
    for index, c in enumerate(targetstr):
        if c == char:
            count += 1
            if count == nthpos:
                return index
    return 0


def dispatch_command_line_arguments(args):
    if len(args) == 0:
        return True
    else:
        print_elb()
        print_lb("Command line args are currently not supported.")
        print_elb()
    return True  # Script info header


script_info_header = """\n#*********************************************#
#                                             #
#       -- Latest Stable Upstream --          #
#         -- Kernel Downloader --             #
#                                             #
# Purpose: Latest stable upstream kernel      #
#          DEB files downloader and           #
#          installer script                   #
#                                             #
# Author:   Kerem Gümrükcü                    #
# EMail:    kerem.g@arcor.de                  #
# License:  MIT-License                       #
#*********************************************#
"""


def main(argv):
    # global import of variables
    global sha1sum_bin_file_full_path
    global dpkg_bin_file_full_path
    global latest_stable_kernel_checksums_file

    # print application info
    print_lb(script_info_header)

    # dispatch arguments, if returning false
    # exit the script
    if not dispatch_command_line_arguments(argv):
        return

    # doing prerequisites check
    print_lb("[Checking environment requirements]:" + os.linesep +
             "-----------------------------------")

    print_nlb("Is system linux based ...")

    # only linux is allowed to run
    if not sys.platform.startswith("linux"):
        print_lb(NO_STRING + os.linesep)
        print_lb("The script is only made to run on linux systems. Sorry!" + os.linesep)
        exit_script(1)

    # yes, we run on linux
    print_lb(YES_STRING)

    # Check whether the download directory exists or not
    # and create on missing, use user defined if set
    global user_kernel_package_download_dir
    if FORCE_DOWNLOAD_LOCATION:
        user_kernel_package_download_dir = FORCE_DOWNLOAD_LOCATION

    print_nlb("Checking for " + ("user defined \"{0}\" ".format(
        FORCE_DOWNLOAD_LOCATION) if FORCE_DOWNLOAD_LOCATION is not None else "") + "download directory availability ...")

    if not os.path.isdir(user_kernel_package_download_dir):
        print_lb(MISSING_STRING)
        print_nlb("Download directory missing...creating new download directory in \"" + quote(
            user_kernel_package_download_dir) + "\" ...")
        os.makedirs(user_kernel_package_download_dir)
        print_lb(SUCCESS_STRING)
    else:
        print_lb(AVAILABLE_STRING)
        print_lb("Download directory already exists in: " + quote(user_kernel_package_download_dir))

    # check for sha1sum binary for downloaded
    # files verfification
    print_nlb("Checking for \"{0}\" availability ...".format(SHA1SUM_BIN_FILE))

    sha1sum_bin_file_full_path = distutils.spawn.find_executable(SHA1SUM_BIN_FILE)

    if not os.path.isfile(sha1sum_bin_file_full_path):
        raise IOError(
            "The \"{0}\" binary is missing for checksum validation. This is mandatory!".format(SHA1SUM_BIN_FILE))

    print_lb(AVAILABLE_STRING)
    print_lb("The \"{0}\" binary file is located in: {1}".format(SHA1SUM_BIN_FILE, sha1sum_bin_file_full_path))

    # check for dpkg binary for
    # installation
    print_nlb("Checking for \"{0}\" availability ...".format(DPKG_BIN_FILE))

    dpkg_bin_file_full_path = distutils.spawn.find_executable(DPKG_BIN_FILE)

    if not os.path.isfile(dpkg_bin_file_full_path):
        print_lb(MISSING_STRING)
        print_lb("The \"{0}\" binary is missing for kernel files installation.".format(DPKG_BIN_FILE))
    else:
        print_lb(AVAILABLE_STRING)
        print_lb("The \"{0}\" binary file is located in: {1}".format(DPKG_BIN_FILE, dpkg_bin_file_full_path))

    # check for dpkg binary for
    # grub update
    print_lb("Checking for download tools availability:")

    for download_tool in DOWNLOAD_TOOLS.items():

        # reference global variable
        global downloader_bin_full_path_and_param

        print_nlb("Probing for \"{0}\" availability ...".format(download_tool[0]))

        downloader_bin_full_path = distutils.spawn.find_executable(string_to_unicode(download_tool[0]))

        if not os.path.isfile(string_to_unicode(downloader_bin_full_path)):
            print_lb(MISSING_STRING)
        else:
            print_lb(AVAILABLE_STRING)
            print_lb("The \"{0}\" downloader binary file is located in: {1}".format(download_tool[0],
                                                                                    downloader_bin_full_path))
            # create list if None
            if downloader_bin_full_path_and_param is None:
                downloader_bin_full_path_and_param = list()

            # binary found, insert to array
            downloader_bin_full_path_and_param.append(downloader_bin_full_path)
            downloader_bin_full_path_and_param.append(download_tool[1])
            break

    # check whether we will use the simple
    # build-in downloader as fallback or not
    if downloader_bin_full_path_and_param is None:
        print_lb("Could not find any suitable downloader. The build-in downloader will be used.")

    restart_internet_connection_attempt = True

    while restart_internet_connection_attempt:
        # check for internet availability
        print_nlb("Checking for internet connection availability in {0} seconds timeout cycle, please wait ...".format(
            SERVER_TIMEOUT_CYCLES_IN_SEC))

        start_progress_spinner()

        internet_available = is_internet_available()

        restart_internet_connection_attempt = False

        if internet_available is not None:
            stop_progress_spinner()
            print_lb(SUCCESS_STRING)
            print_lb("Internet connection is available. Successfully connected to \"{0}\" on port \"{1}\".".format(
                internet_available[0], internet_available[1]))
        else:
            stop_progress_spinner()
            print_lb(FAILED_STRING)

            print_elb()

            print_lb("Internet connection not available. You need a running internet " +
                     "connection in order to use this script and download the kernel " +
                     "packages. Would you like to restart a connection attempt to the " +
                     "online servers? If you press \"Yes\", a connection test will be " +
                     "restarted. If you press \"No\", the script continues without being " +
                     "aware of a running internet connection.")

            print_elb()

            user_decision = request_user_yes_no_abort_script()

            if user_decision == YES_PRESSED:
                restart_internet_connection_attempt = True
            else:
                restart_internet_connection_attempt = False

    print_elb()

    # collect and print user and os environment data
    print_lb("[Environment information]:" + os.linesep +
             "-------------------------")
    print_lb("Kernel version info JSON url: " + LATEST_KERNEL_VERSION_JSON_URL)
    print_lb("Upstream kernels archive url: " + LATEST_UPSTREAM_KERNELS_ARCHIVE_URL)
    print_lb("User home directory is: " + user_home_directory)
    print_lb("Script base download directory is: " + user_home_download_directory)
    print_lb("Kernel packages download directory is: " + user_kernel_package_download_dir + "/<ver>/<arch>/<flavor>")
    print_lb("Running Linux platform: " + os_linux_platform)
    print_lb("Running Linux architecture is: " + os_linux_architecture)
    print_lb("Running Python version is: " + os_python_version)
    print_elb()

    try:

        # loop to repeat_download step if
        # if user wants to download more
        # variants
        repeat_download = True
        while repeat_download:

            print_lb("[Collecting online Upstream kernel information]:" + os.linesep +
                     "-----------------------------------------------")

            print_nlb("Trying to download kernel JSON info data from official Kernel archive ...")

            # check whether we should use a predefined version
            # or use the online resource
            if FORCE_KERNEL_VERSION:
                print_lb(SKIPPED_STRING)
                print_lb("Will use user defined kernel version string \"{0}\" for online repository access.".format(
                    FORCE_KERNEL_VERSION))
                kernel_info_json_data_stream = True  # fake a valid stream
                latest_stable_kernel_version_number = FORCE_KERNEL_VERSION
            else:
                # download the json info data
                start_progress_spinner()
                web_response = open_webfile_get_response(LATEST_KERNEL_VERSION_JSON_URL)
                kernel_info_json_data_stream = web_response[1]

                if kernel_info_json_data_stream is None or web_response[0] != 200:
                    print_lb(FAILED_STRING)
                    print_elb()
                    raise WebFileDownloadError(
                        "Could not open {0} for downloading. Please check your internet connection or online location for availability.".format(
                            LATEST_KERNEL_VERSION_JSON_URL) + " The response code for the file was \"{0}\".".format(
                            web_response[0]))

                kernel_json_info_data = json.loads(kernel_info_json_data_stream)

                # get the latest stable version info
                latest_stable_kernel_version_number = kernel_json_info_data["latest_stable"]["version"]
                stop_progress_spinner()
                print_lb(SUCCESS_STRING)

            latest_stable_kernel_version_directory_string = "v" + latest_stable_kernel_version_number

            # print version info data
            if FORCE_KERNEL_VERSION:
                print_lb("User defined kernel version is: " + latest_stable_kernel_version_number)
            else:
                print_lb("Latest stable kernel version is: " + latest_stable_kernel_version_number)

            print_nlb(
                "Trying to download kernel \"CHECKSUMS\" file from \"" + latest_stable_kernel_version_directory_string + "\" Upstream kernel archive directory ...")

            start_progress_spinner()
            # download the CHECKSUMS info data stream
            latest_stable_kernel_checksums_file = LATEST_UPSTREAM_KERNELS_ARCHIVE_URL + os.path.sep + latest_stable_kernel_version_directory_string + os.path.sep + CHECKSUMS_FILE
            web_response = open_webfile_get_response(latest_stable_kernel_checksums_file)
            kernel_checksums_file_stream = web_response[1]
            if kernel_info_json_data_stream is None or web_response[0] != 200:
                print_lb(FAILED_STRING)
                print_elb()
                raise WebFileDownloadError(
                    "Could not open \"{0}\" for downloading. Please check your internet connection or online location for availability.".format(
                        latest_stable_kernel_checksums_file) + " The response code for the file was \"{0}\".".format(
                        web_response[0]))

            stop_progress_spinner()
            print_lb(SUCCESS_STRING)

            # build the hash tables#
            print_nlb("Building checksum tables with DEB package names...")

            start_progress_spinner()

            # build the dictionaries with the hashed files
            checksums_stream = get_string_unicode_stream(kernel_checksums_file_stream)

            # iterate over elements
            # and filter
            # add pseudo cancel arch first, zero is always cancel
            del kernel_available_architectures[:]  # cleanup lists
            for read_line in checksums_stream:
                read_line = read_line.strip()
                if re.search(r".*\.deb$", read_line, re.IGNORECASE | re.UNICODE) is not None:
                    kernel_hash_and_file = read_line.split()  # [0]=hash, [1]=filename
                    # we only want the sha1 40 chars length sized hash
                    if strlen_unicode(kernel_hash_and_file[0]) == 40:
                        kernel_hashes_and_files[kernel_hash_and_file[0]] = kernel_hash_and_file[1]
                        # add available kernel archs to the list
                        # first get kernel arch
                        kernel_arch = kernel_hash_and_file[1].split("_")[2].split(".")[0]
                        if kernel_arch not in kernel_available_architectures and kernel_arch != "all":
                            kernel_available_architectures.append(kernel_arch)

            stop_progress_spinner()
            print_lb(SUCCESS_STRING)

            # print total available
            # packages count

            print_lb("Total available kernel DEB package files: " + string_to_unicode(len(kernel_hashes_and_files)))
            print_lb("Total available kernel package architectures: " + string_to_unicode(
                len(kernel_available_architectures)))
            print_elb()

            # there are currently no packages available for that
            # version yet, exit the script
            if len(kernel_hashes_and_files) == 0 or len(kernel_available_architectures) == 0:
                print_lb(
                    "Seems like that there are currently no DEB packages available on the Upstream kernel archive " +
                    "for the kernel version \"{0}\". Please try again later or visit the archive online to check manually.".format(
                        latest_stable_kernel_version_number))
                print_elb()
                print_lb("No files have been downloaded. Have a nice day.")
                print_nelb(2)
                exit_script(0)

            # ask the user for the prefered kernel
            # architecture he wants: amd64, i386, s390x, etc.
            print_lb("Please select your prefered kernel" + os.linesep + "architecture to download: ")
            print_elb()

            # probe user input for valid number
            # invalid data == exit script
            # select target kernel architecture
            user_selection_number = request_user_input_number_exit_on_fail(
                kernel_available_architectures,
                len(kernel_available_architectures),
                len(kernel_available_architectures))

            kernel_selected_target_arch = kernel_available_architectures[user_selection_number]
            print_lb("Selected target architecture is: " + kernel_selected_target_arch)
            print_elb()

            # ask the user for the prefered kernel flavor
            # like generic, generic-lpae, lowlatency, etc.
            print_lb("Please select your prefered kernel" + os.linesep + "flavor to download: ")
            print_elb()

            # cut-off the flavor part
            del kernel_available_flavors[:]  # cleanup lists
            for kernel_hash, kernel_file in kernel_hashes_and_files.items():
                # skip the generic header file with no flavor part
                # and all flavors we dont have for the selected arch
                if "_all.deb" not in kernel_file and kernel_selected_target_arch in kernel_file:
                    # the forth "-" is the delimiter for the flavor part
                    startpos_kernel_flavor = find_position_of_nth_string_occurence(kernel_file, "-", 4) + 1
                    flavor = kernel_file[startpos_kernel_flavor:]  # cut the string before the flavor
                    flavor = flavor[:get_string_index(flavor, "_")]  # get the length of the flavor string
                    if flavor not in kernel_available_flavors:
                        kernel_available_flavors.append(flavor)

            # probe user input for valid number
            # invalid data == exit script
            # select target kernel flavor
            user_selection_number = request_user_input_number_exit_on_fail(
                kernel_available_flavors,
                len(kernel_available_flavors),
                len(kernel_available_flavors))

            kernel_selected_target_flavor = kernel_available_flavors[user_selection_number]
            print_lb("Selected target flavor is: " + kernel_selected_target_flavor)
            print_elb()

            # GO FOR IT
            # dispatch all gathered data
            full_download_location = user_kernel_package_download_dir + os.path.sep + \
                                     latest_stable_kernel_version_directory_string + os.path.sep + \
                                     kernel_selected_target_arch + os.path.sep + \
                                     kernel_selected_target_flavor

            # Check whether the download directory exists or not
            # and create on missing
            print_nlb("Checking for download arch and flavor sub-directory availability ...")

            if not os.path.isdir(full_download_location):
                print_lb(MISSING_STRING)
                print_nlb(
                    "Creating new arch and flavor download sub-directory in \"" + quote(
                        full_download_location) + "\" ...")
                os.makedirs(full_download_location)
                print_lb(SUCCESS_STRING)
            else:
                print_lb(SUCCESS_STRING)
                print_lb("Download sub-directory for arch and flavor already exists in: \"" + quote(
                    full_download_location) + "\"")

            if not is_directory_empty(full_download_location):
                print_elb()
                print_lb("The download directory \"{0}\" already contains files. Would you like to fully ".format(
                    quote(
                        full_download_location)) + "purge its contents, before you start downloading the new files? If you select \"No\", existing files will be overwritten!")

                print_elb()
                user_selection_number = request_user_yes_no_abort_script()

                if user_selection_number == YES_PRESSED:
                    print_lb("(Purging - Existing files and folders will be purged)")
                elif user_selection_number == NO_PRESSED:
                    print_lb("(Overwriting - Existing files will be overwritten)")

                if user_selection_number == YES_PRESSED:
                    delete_files_in_directory(
                        full_download_location,
                        True)
                    print_elb()
                    print_lb(
                        "All folder contents in \"{0}\" have been purged successfull! Proceeding download ...".format(
                            full_download_location))

            print_elb()
            print_lb("Starting files download (press Ctrl+C to abort running download task) ...")
            print_elb()

            download_counter = 0  # our download counter
            del user_downloaded_kernel_deb_files[:]  # delete already downloaded files list

            # first download the CHECKSUMS file
            print_nlb("[{0}]: Downloading file \"".format(download_counter) + CHECKSUMS_FILE + "\" from \"" +
                      latest_stable_kernel_checksums_file +
                      "\" to \"" +
                      full_download_location + os.path.sep + CHECKSUMS_FILE + "\" ...")

            # only start/stop spinner if there is no download tool
            if downloader_bin_full_path_and_param is None:
                start_progress_spinner()

            if download_file(LATEST_UPSTREAM_KERNELS_ARCHIVE_URL + os.path.sep +
                                     latest_stable_kernel_version_directory_string +
                                     os.path.sep + CHECKSUMS_FILE,
                             full_download_location + os.path.sep + CHECKSUMS_FILE):
                user_downloaded_kernel_deb_files.append(full_download_location + os.path.sep + CHECKSUMS_FILE)
                if downloader_bin_full_path_and_param is None:
                    stop_progress_spinner()
                    print_lb(SUCCESS_STRING)
            else:
                if downloader_bin_full_path_and_param is None:
                    stop_progress_spinner()
                    print_lb(FAILED_STRING)

            print_lb(
                "File size: " + str(get_file_size(full_download_location + os.path.sep + CHECKSUMS_FILE)) + " bytes")
            print_elb()

            # download all DEB files in the dictionary
            # for the specific arch
            for kernel_hash_key, kernel_deb_file in kernel_hashes_and_files.items():
                if kernel_deb_file.endswith("_all.deb") or \
                        (kernel_deb_file.endswith("_" + kernel_selected_target_arch + ".deb") and
                                         "-" + kernel_selected_target_flavor + "_" in kernel_deb_file):  # compose the flavor part

                    destination_full_path = full_download_location + os.path.sep + kernel_deb_file
                    source_full_url = LATEST_UPSTREAM_KERNELS_ARCHIVE_URL + os.path.sep + latest_stable_kernel_version_directory_string + os.path.sep + kernel_deb_file

                    download_counter += 1

                    print_nlb("[{0}]: Downloading file \"".format(download_counter) + kernel_deb_file
                              + "\" from \"" +
                              source_full_url +
                              "\" to \"" +
                              destination_full_path + "\" ...")

                    # only start spinner if there is no download tool
                    if downloader_bin_full_path_and_param is None:
                        start_progress_spinner()

                    if download_file(
                            source_full_url,
                            destination_full_path):
                        user_downloaded_kernel_deb_files.append(destination_full_path)
                        if downloader_bin_full_path_and_param is None:
                            stop_progress_spinner()
                            print_lb(SUCCESS_STRING)
                    else:
                        if downloader_bin_full_path_and_param is None:
                            stop_progress_spinner()
                            print_lb(FAILED_STRING)

                    print_lb("File size: " + str(get_file_size(destination_full_path)) + " bytes")

                    print_nlb("Validating checksum from online kernel archive to downloaded local file ...")

                    start_progress_spinner()
                    local_sha1_checksum = execute_process_wait_get_output(
                        [SHA1SUM_BIN_FILE,
                         destination_full_path])
                    stop_progress_spinner()
                    print_lb(FINISHED_STRING)

                    if local_sha1_checksum.lower() == kernel_hash_key.lower():
                        print_lb(
                            "Local file hash: " + local_sha1_checksum + os.linesep + "Remote file hash: " + kernel_hash_key + os.linesep + "OK. File is valid.")
                    else:
                        print_lb(
                            "Local file hash: " + local_sha1_checksum + os.linesep + "Remote file hash: " + kernel_hash_key + os.linesep + "WARNING! File is possibly corrupted.")

                    print_elb()

            print_lb("[Successfully downloaded files]:" + os.linesep +
                     "-------------------------------")
            # make sure we downloaded more than zero and one more than just the CHECKSUMS file
            downloaded_kernel_deb_files_count = len(user_downloaded_kernel_deb_files)
            if downloaded_kernel_deb_files_count == 0 or (downloaded_kernel_deb_files_count == 1 and CHECKSUMS_FILE in user_downloaded_kernel_deb_files):
                print_lb("No kernel archive files have been successfully downloaded. Have a nice day." + os.linesep)
                exit_script(0)
            else:
                for deb_file_name in user_downloaded_kernel_deb_files:
                    print_lb("\t" + os.path.basename(deb_file_name))

            print_elb()

            # check for root
            # if yes, ask for install
            optionally_installing = ""
            if os.geteuid() == 0:
                print_lb(
                    "You are running as \"root\". Would you like to install the kernel files with " + DPKG_BIN_FILE + "? " +
                    "WARNING: You should exactly know what you are doing now, since a new or wrong kernel can render your system " +
                    "entirely useless or instable if something fails or the kernel has bugs. Remember that these kernels "
                    "are not supported from Ubuntu and are not appropriate for production use. YOU HAVE BEEN WARNED!")

                print_elb()
                print_lb("[Successfully downloaded kernel files (will be installed in that order)]:" + os.linesep +
                         "--------------------------------------")

                # headers-all file is the shortest string and must be
                # installed first before all others to avoid dpkg errors
                user_downloaded_kernel_deb_files.sort(key=len)
                for deb_file_name in user_downloaded_kernel_deb_files:
                    if ".deb" in deb_file_name:
                        print_lb("\t" + os.path.basename(deb_file_name))

                print_elb()

                user_selection_number = request_user_yes_no_abort_script()

                print_elb()

                if user_selection_number == YES_PRESSED:

                    error_occurred = 0
                    last_error_code = 0
                    exit_installation = False
                    optionally_installing = " and installing"

                    for deb_file_name in user_downloaded_kernel_deb_files:

                        dpkg_file_is_locked = True

                        while dpkg_file_is_locked:
                            if is_file_locked(DPKG_LOCK_FILE) == STATE_TRUE:

                                dpkg_file_is_locked = True

                                print_elb()

                                print_lb(
                                    "Another installer is holding an exclusive lock on the dpkg lock file \"{0}\". ".format(
                                        DPKG_LOCK_FILE) +
                                    "Please wait until other installations will finish or close the installer application. " +
                                    "If you are ready to continue the packages installation, select \"Yes\" to retry, \"No\" to continue without " +
                                    "installation or \"Cancel script\" to abort the entire script.")

                                print_elb()

                                user_selection_number = request_user_yes_no_abort_script()

                                if user_selection_number == NO_PRESSED:
                                    exit_installation = True
                                    break

                                elif user_selection_number == ABORT_PRESSED:
                                    exit_script(0)

                                print_elb()

                                exit_installation = False  # reset flag

                            else:
                                break

                        if exit_installation:
                            break

                        file_name = os.path.basename(deb_file_name)

                        if file_name != CHECKSUMS_FILE:
                            print_lb(
                                "Installing " + file_name + " with " + DPKG_BIN_FILE + ", please wait ..." + os.linesep)

                            error_code = execute_process_wait_get_returncode(
                                [dpkg_bin_file_full_path,
                                 DPKG_BIN_FILE_PARAMS, quote(deb_file_name)])

                            if error_code != 0:
                                last_error_code = error_code
                                error_occurred += 1

                    if error_occurred != 0:
                        print_elb()
                        print_lb(
                            "One or more installation steps finished with a error code. Last error code was \"{0}\". Please check the files installation status.".format(
                                last_error_code))
                    else:

                        if not exit_installation:

                            print_elb()

                            print_lb(
                                "The kernel packages installation seem to finish successfully." + os.linesep +
                                "Would you like to reboot your system into the new kernel?")

                            print_elb()

                            user_selection_number = request_user_yes_no_abort_script()

                            if user_selection_number == YES_PRESSED:
                                print_elb()
                                print_lb("Rebooting your system ...")
                                execute_process_wait_get_returncode(["reboot"])

                            print_elb()

            # ask the user for more downloads
            print_lb("Would you like to get more/another packages/flavors and run the download procedure again?")
            print_elb()

            user_selection_number = request_user_yes_no_abort_script()

            if user_selection_number != YES_PRESSED:
                repeat_download = False
            else:
                print_nelb(2)  # put some spacers before repeating

        print_elb()
        print_lb("Downloading" + optionally_installing + " files finished. Have a nice day." + os.linesep)

    except WebFileDownloadError as e:
        # stop spinner if running
        stop_progress_spinner()
        print_lb("Web file access error: {0}".format(e.errmsg) + os.linesep)
        print_lb("Exiting script.")
        print_nelb(2)
        exit_script(1)
    except KeyboardInterrupt:
        # stop spinner if running
        stop_progress_spinner()
        print_lb(os.linesep + os.linesep + "Script manually aborted. Good Bye!" + os.linesep)
        exit_script(1)
    except Exception as e:
        # stop spinner if running
        stop_progress_spinner()
        print_nlb("ERROR: Operation failed! Reason: {0}. Terminating script.".format(
            "Unknown Error" if len(e.message) == 0 or e.message is None else e.message) + os.linesep)
        print_elb()
        exit_script(1)
    finally:
        # stop spinner if running
        stop_progress_spinner()
        exit_script(0)


# entry point, strip-off script name in passed args
if __name__ == "__main__":
    main(sys.argv[1:])
