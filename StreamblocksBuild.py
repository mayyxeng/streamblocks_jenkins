import subprocess
import argparse
import json
import jenkins
import tarfile
import os
import requests


import sys


def printError(*args):
    print('\033[91mError\033[0m:' + " ".join(map(str, args)))


def queryYesNo(question, default="yes"):
    """Ask a yes/no question via raw_input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")


class JenkinsJob:

    """
    A job is a JSON record such as:
    {
      "name" : "u250_rvc_configuration_4_3.3",
      "dir" : "configuration_4_3.3",
      "network" : "decoderDemo",
      "operation": "build",
      "params" : {
        "HLS_CLOCK_PERIOD" : 3.3,
        "KERNEL_FREQ" : 300,
        "TARGET" : "hw",
        "PLATFORM": "xilinx_u250_xdma_201830_2",
        "FPGA_NAME": "xcu250-figd2104-2L-e",
        "IS_MPSOC": "OFF",
        "MPSOC_CLOCK_ID" : "0"
      }
    }

    """
    DEFAULT_SERVER = 'http://iccluster126.iccluster.epfl.ch:8080/'
    DEFAULT_TEMPLATE = 'templates/shell_build_template'

    def getServer(url, username, password):
        return jenkins.Jenkins(url,
                               username=username, password=password)

    def __init__(self, job_info, no_prompt=False):

        try:
            self.no_prompt = no_prompt
            self.name = job_info['name']
            self.dir = job_info['dir']
            self.network = job_info['network']
            self.operation = job_info['operation']
            self.params = job_info['params']
        except KeyError as err:
            printError("Invalid job key:")
            raise RuntimeError from err

    def jobName(self, user):
        return user + "/" + self.name

    """
  Submit the job to the server
  """

    def submit(self, server, user, token, template_name):
        job_name = self.jobName(user)
        job_exists = self.jobExists(server, user)
        job_template = jenkins.EMPTY_CONFIG_XML
        try:
            print("Pulling job template from jenkins %s" % (template_name))
            job_template = server.get_job_config(template_name)
        except Exception as e:
            raise RuntimeError(
                "Could not fetch job template " + template_name + ": " + str(e))
        if self.operation == "build":
            should_build = False
            if job_exists:
                should_build = True if self.no_prompt else queryYesNo(
                    "Job " + self.name + " already exists, do you want to reconfigure and rebuild?", 'yes')
                if should_build:
                    server.reconfig_job(job_name, job_template)
            else:
                # template_name = 'templates/shell_build_template'
                server.create_job(job_name, job_template)
                should_build = True
            if should_build:
                try:

                    self.__submit_build__(server, user, token)
                except subprocess.SubprocessError as err:
                    print("Failed to enqueue job %s\n:" %
                          (self.name, err))
                    pass

        elif self.operation == "clean":
            prompt = True if self.no_prompt else queryYesNo(
                "Do you want to clean job " + self.name + "?", 'no')
            if job_exists and prompt:
                self.__submit_clean__(server, user)
            else:
                print("Skipping job " + self.name)

        elif self.operation == "query":
            self.query(server, user)
        elif self.operation == "download":
            self.download(server, user, token)
        else:
            print("Invalid operation " + self.operation)

    def __submit_build__(self, server, user, token):
        job_name = self.jobName(user)

        root_dir = os.getcwd()

        job_url = server.get_job_info(job_name)['url']
        job_build_url = job_url + "/buildWithParameters"

        def tardir(paths, tar_name):
            with tarfile.open(tar_name, 'w:gz') as tar_handle:
                for path in paths:
                    if os.path.exists(path):
                        tar_handle.add(path, recursive=True)

        tarbal = self.name + '.tar.gz'
        tar_sources = [
            'vivado-hls',
            'multicore',
            'CMakeLists.txt',
            'bin'
        ]

        print("Creating compressesd file " + tarbal)
        os.chdir(self.dir)

        tardir(tar_sources, tarbal)

        forms = "--form submission_file=@" + "./" + tarbal + " "
        forms = forms + "--form NETWORK_NAME=" + self.network + " "

        for (param_key, param_value) in self.params.items():
            if type(param_value) != str:
                param_value = str(param_value)
            forms = forms + "--form " + param_key + "=" + param_value + " "

        # This is a very ugly way of doing things, all because I can not send
        # a file using the python api...

        print("Uploading submission")
        curl_cmd = "curl " + job_build_url + " --user " + user + ":" + token + " " + forms

        curl = subprocess.run(curl_cmd, shell=True, stdout=subprocess.PIPE)

        print("Cleaning up temp archives")

        os.remove(tarbal)
        os.chdir(root_dir)

        if curl.returncode != 0:
            print("Submission failed\n%s" % (curl_cmd))

    def __submit_clean__(self, server, user):
        job_name = self.jobName(user)
        if self.jobExists(server, user):

            job_info = server.get_job_info(job_name)
            if job_info != None:
                last_build_number = job_info['lastBuild']['number']
                print("Stopping build for job %s" % job_name)
                server.stop_build(job_name, last_build_number)
                print("Cleaning job %s" % job_name)
                server.delete_job(job_name)

    """
  Query the status of the job
  """

    def query(self, server, user):
        job_name = self.jobName(user)
        # if self.jobExists(server, job_name):
        build_info = self.__get_last_build_info__(server, user)
        if build_info != None:
            if build_info['building'] == True:
                show_console = True if self.no_prompt else queryYesNo(
                    "Job " + job_name + " is building, show console output?", 'yes')
                if show_console:
                    console_output = server.get_build_console_output(
                        job_name, build_info['number'])
                    print(
                        "-------------------------------------------------------------")
                    print("JOB: %s" % job_name)
                    print("\n\n%s\n\n" % console_output)
                print("=============================================================")
            else:
                print("Job %s is not building" % job_name)
        # else:
        #   print("Job %s does not exits, skipping query."%(job_name))

    def __get_last_build_info__(self, server, user):
        job_name = self.jobName(user)
        if self.jobExists(server, user):
            print("Pulling %s job info" % job_name)
            job_info = server.get_job_info(job_name)
            if job_info != None:
                last_build_number = job_info['lastBuild']['number']
                build_info = server.get_build_info(job_name, last_build_number)
                return build_info
        return None

    """
  Download the artifacts
  """

    def download(self, server, user, token):

        job_name = self.jobName(user)
        if self.jobExists(server, user):
            build_info = self.__get_last_build_info__(server, user)
            if build_info != None:
                if build_info['building'] == False and len(build_info['artifacts']) > 0:
                    job_url = build_info['url']
                    dl_url = job_url + 'artifact/*zip*/archive.zip'

                    print("Downloading artifacts from " + dl_url)
                    dl_dir = self.dir + '/artifacts.zip'
                    should_download = True

                    if os.path.isfile(dl_dir):
                        should_download = queryYesNo("Archive already exists at " +
                                                     dl_dir + ", download again?", 'no')
                    if should_download:
                        with open(dl_dir, 'wb') as f:
                            response = requests.get(
                                dl_url, stream=True, auth=(user, token))
                            total_length = response.headers.get(
                                'content-length')

                            if total_length is None:  # no content length header
                                f.write(response.content)
                            else:
                                dl = 0
                                total_length = int(total_length)
                                for data in response.iter_content(chunk_size=4096):
                                    dl += len(data)
                                    f.write(data)
                                    done = int(50 * dl / total_length)
                                    sys.stdout.write("\r[%s%s]" % (
                                        '=' * done, ' ' * (50-done)))
                                    sys.stdout.flush()
                else:
                    print("Job is not finished")
        else:
            print("Job does not exist")

    """
  Check if the job exits
  """

    def jobExists(self, server, user):
        job_name = self.jobName(user)
        return server.job_exists(job_name)
