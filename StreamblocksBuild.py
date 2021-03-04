import subprocess
import argparse
import json
import jenkins
import tarfile
import os
import requests
import shutil
import re
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


class Utilities:

    def forceMakeDirectory(path):
        """
        Recursively creates fresh directories given by the path. If a directory
        tree already exits at the path, it will be removed.
        """
        if os.path.exists(path):
            shutil.rmtree(path)
        os.makedirs(path)

    def __get_utilization_report__(utilization_report_path):
        """
        extract synthesis utilizatino report and return it in a dictionary
        """
        if os.path.exists(utilization_report_path):

            def getUtil(report_dir):
                def getUtilRE(resource):

                    return re.compile(r'\|\s*' + resource + r'\s*\|\s*(\d*)(\.\d*)?\s*\|\s*\d*\s*\|\s*(\d*)\s*\|\s*(\d*\.\d*)\s*\|')

                def matchRE(expr, line):
                    matches = expr.match(line)
                    if (matches != None):

                        used = int(matches.group(1))
                        avail = int(matches.group(3))
                        util = float(matches.group(4))
                        return {"used": used, "availble": avail, "util": util}
                    else:
                        return None

                report_fields = {
                    'LUTS': {
                        'keyword': 'CLB LUTs\*'
                    },
                    'FF': {
                        'keyword': 'CLB Registers'
                    },
                    'BRAM': {
                        'keyword': 'Block RAM Tile'
                    },
                    'DSP': {
                        'keyword': 'DSPs'
                    }
                }
                util_sum = dict(zip(report_fields.keys(), [
                    None for v in report_fields.values()]))

                with open(utilization_report_path) as util_fp:
                    report = util_fp.readlines()
                    expression_map = dict(zip(report_fields.keys(), [getUtilRE(
                        v['keyword']) for v in report_fields.values()]))

                    for line in report:
                        # print(line)
                        for rs, expr in expression_map.items():
                            # print(rs)
                            util = matchRE(expr, line)
                            if util:
                                util_sum[rs] = util

                return util_sum

            return getUtil(utilization_report_path)
        else:
            printError(
                "Synthesis report " + utilization_report_path + " does not exist")
            return None

    def __get_timing_report__(timing_report_path):
        """
        Extract the timing violation and return a list of violations
        """
        if not os.path.exists(timing_report_path):
            printError(
                "Timing report " + timing_report_path + " does not exists")
            return None

        regex_slack_violation = re.compile(
            r'Slack\s*\(VIOLATED\)\s*:\s*(\-\d*\.\d*)\w*\s*\(required time - arrival time\)')

        with open(timing_report_path, 'r') as fp:
            lines = fp.readlines()

            slack_violations = []
            for ln_num, ln in enumerate(lines):

                matches = regex_slack_violation.match(ln)
                if matches:

                    violation = float(matches.group(1))
                    source = lines[ln_num + 1].split()[1]
                    dest = lines[ln_num + 3].split()[1]
                    required = float(lines[ln_num + 7].split()[1][0:-2])
                    slack_violations.append({
                        'violation': violation,
                        'source': source,
                        'destination': dest,
                        'requirement': required,
                        'allowed': required - violation
                    })
            return slack_violations

    def __get_synthesis_report__(extract_dir):
        """
        Get the resource and timing report in a dictionary
        """
        timing_report_path = extract_dir + '/project/bin/reports/timing_summary.rpt'
        result = {'timing': None, 'utilization': None}
        # if os.path.exists(timing_report_path):

        utilization_report_path = extract_dir + \
            '/project/bin/reports/report_utilization.rpt'
        util_report = Utilities.__get_utilization_report__(
            utilization_report_path)
        timing_report = Utilities.__get_timing_report__(
            timing_report_path)
        return {
            'utilization': util_report,
            'timing': timing_report
        }
    def __get_instance_report__(hls_build_dir):
        
        def __check_report_exists__(hls_project_path, project_name):
            report_file_path = hls_project_path + '/' + project_name + \
                '/solution/impl/report/verilog/' + project_name + '_export.rpt'
            if not os.path.exists(report_file_path):
                printError(
                    "Report file " + report_file_path + " does not exist")
                return None
            else:
                return report_file_path

        def __inner_summarize__(hls_project_path, project_name):
            report_file_path = __check_report_exists__(
                hls_project_path, project_name)
            if report_file_path:

                def __extract_resource__(resource):
                    regex = re.compile(r'' + resource + r':\s*(\d*)')
                    with open(report_file_path, 'r') as fp:
                        lines = fp.readlines()
                        for line in lines:
                            matches = regex.match(line)
                            if matches:
                                used = int(matches.group(1))
                                return used

                def __extract_cp__():
                    regex_req = re.compile(r'CP required:\s*(\d*\.\d*)')
                    regex_achv = re.compile(
                        r'CP achieved post-synthesis:\s*(\d*\.\d*)')
                    res = {'cp_required': None, 'cp_achieved': None}
                    with open(report_file_path, 'r') as fp:
                        lines = fp.readlines()
                        for line in lines:
                            matches = regex_req.match(line)
                            if matches:
                                res['cp_required'] = float(
                                    matches.group(1))
                            matches = regex_achv.match(line)
                            if matches:
                                res['cp_achieved'] = float(
                                    matches.group(1))
                    return res

                reources = ['SLICE', 'LUT', 'FF', 'DSP', 'BRAM', 'SRL', 'URAM']
                utils = [__extract_resource__(r) for r in reources]
                return {
                    'resources': dict(zip(reources, utils)),
                    'timing': __extract_cp__()
                }
            else:
                return None

        hls_projects_root = hls_build_dir
        summary = {}
        for dir in os.listdir(hls_projects_root):
            print("Extracting reports for " + dir)
            summary[dir] = __inner_summarize__(hls_projects_root, dir)
        print("Extracted %d reports" % (len(summary)))
        return summary