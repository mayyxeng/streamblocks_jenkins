import json
import re
from zipfile import ZipFile
import argparse
import sys
import os
import inspect
import requests
import shutil
import tarfile

try:
    from .. import StreamblocksBuild
except ImportError as e:
    currentdir = os.path.dirname(os.path.abspath(
        inspect.getfile(inspect.currentframe())))
    parentdir = os.path.dirname(currentdir)
    sys.path.insert(0, parentdir)
    import StreamblocksBuild


"""
Aggeragate the hls reports of different synthesized actors into a json file
"""


class CustomJenkinsJob(StreamblocksBuild.JenkinsJob):

    # def __download_instance_reports__(self, server, user, token):
    #     job_name = self.jobName(user)
    #     if self.jobExists(server, user):
    #         build_info = self.__get_last_build_info__(server, user)
    #         if build_info != None:
    #             if build_info['building'] == False and len(build_info['artifacts']) > 0:
    #                 job_url = build_info['url']
    #                 dl_url = job_url + 'ws/project/bin/instance_reports.tar.gz'

    #                 print("Downloading instance reports from " + dl_url)
    #                 dl_dir = job_info['dir'] + '/instance_reports.tar.gz'
    #                 should_download = True

    #                 if os.path.isfile(dl_dir):
    #                     should_download = StreamblocksBuild.queryYesNo("instance report already exists at " +
    #                                                  dl_dir + ", download again?", 'no')
    #                 if should_download:
    #                     with open(dl_dir, 'wb') as f:
    #                         response = requests.get(
    #                             dl_url, stream=True, auth=(user, token))
    #                         total_length = response.headers.get(
    #                             'content-length')

    #                         if total_length is None:  # no content length header
    #                             f.write(response.content)
    #                         else:
    #                             dl = 0
    #                             total_length = int(total_length)
    #                             for data in response.iter_content(chunk_size=4096):
    #                                 dl += len(data)
    #                                 f.write(data)
    #                                 done = int(50 * dl / total_length)
    #                                 sys.stdout.write("\r[%s%s]" % (
    #                                     '=' * done, ' ' * (50-done)))
    #                                 sys.stdout.flush()
    #             else:
    #                 print("Job is not finished")
    #         else:
    #             print("Job does not exist")

    def makeDirectory(path):
        if os.path.exists(path):
            shutil.rmtree(path)
        os.makedirs(path)

    def getReport(self, server, user, token):

        self.download(server, user, token)

        artifact_path = self.dir + '/artifacts.zip'
        if not os.path.exists(artifact_path):
            StreamblocksBuild.printError(
                "Artifact file " + str(artifact_path) + " does not exist")
            return
        extract_dir = os.path.abspath(self.dir) + '/extracted/'
        CustomJenkinsJob.makeDirectory(extract_dir)

        print("Extracting artifacts to " + extract_dir)
        with ZipFile(artifact_path, 'r') as zfp:
            zfp.extractall(extract_dir)

        instance_summary = CustomJenkinsJob.__get_instance_report__(extract_dir)
        network_summary = CustomJenkinsJob.__get_synthesis_report__(extract_dir)
        return {
            'network_synth': network_summary,
            'instance_synth': instance_summary
        }

    def __get_utilization_report__(utilization_report_path):
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
            StreamblocksBuild.printError(
                "Synthesis report " + utilization_report_path + " does not exist")
            return None

    def __get_timing_report__(timing_report_path):
      
      if not os.path.exists(timing_report_path):
        StreamblocksBuild.printError("Timing report " + timing_report_path + " does not exists")
        return None
      
      regex_slack_violation = re.compile(r'Slack\s*\(VIOLATED\)\s*:\s*(\-\d*\.\d*)\w*\s*\(required time - arrival time\)')

      with open(timing_report_path, 'r') as fp:
        lines = fp.readlines()

        slack_violations = []
        for ln_num, ln in enumerate(lines):

          matches = regex_slack_violation.match(ln)
          if matches:
            print("Found violation")
            violation = float(matches.group(1))
            source = lines[ln_num + 1].split()[1]
            dest = lines[ln_num + 3].split()[1]
            slack_violations.append({
              'violation' : violation,
              'source' : source,
              'destination': dest
            })
        return slack_violations
      
    def __get_synthesis_report__(extract_dir):

        timing_report_path = extract_dir + '/project/bin/reports/timing_summary.rpt'
        result = {'timing': None, 'utilization': None}
        # if os.path.exists(timing_report_path):

        utilization_report_path = extract_dir + \
            '/project/bin/reports/report_utilization.rpt'
        util_report = CustomJenkinsJob.__get_utilization_report__(utilization_report_path)
        timing_report = CustomJenkinsJob.__get_timing_report__(timing_report_path)
        return {
          'utilization' : util_report,
          'timing': timing_report
        }

    def __get_instance_report__(extract_dir):

        instance_report_gz_path = extract_dir + '/project/bin/instance_reports.tar.gz'

        if not os.path.exists(instance_report_gz_path):
            StreamblocksBuild.printError(
                "Instance report file does not exist at " + str(instance_report_gz_path))
            return None

        instance_tar = tarfile.open(instance_report_gz_path, 'r:gz')
        instance_report_dir = extract_dir + '/instnace_reports'
        CustomJenkinsJob.makeDirectory(instance_report_dir)
        instance_tar.extractall(instance_report_dir)

        def __check_report_exists__(hls_project_path, project_name):
            report_file_path = hls_project_path + '/' + project_name + \
                '/solution/impl/report/verilog/' + project_name + '_export.rpt'
            if not os.path.exists(report_file_path):
                StreamblocksBuild.printError(
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

        hls_projects_root = instance_report_dir + '/build/vivado-hls'
        summary = {}
        for dir in os.listdir(hls_projects_root):
            print("Extracting reports for " + dir)
            summary[dir] = __inner_summarize__(hls_projects_root, dir)
        print("Extracted %d reports" % (len(summary)))
        return summary


if __name__ == "__main__":

    arg_parser = argparse.ArgumentParser(
        "Summarize the hls reports of jobs into json files"
    )
    arg_parser.add_argument('jobs', type=str, metavar='FILE',
                            help='json build jobss configuration file')
    # arg_parser.add_argument('--no-download', '-n', action='store_true',
    #                         help='do not download build artifacts if they do not exist', default=False)
    arg_parser.add_argument('-s', '--server', type=str, metavar='URL',
                            help='jenkins server address url', default=StreamblocksBuild.JenkinsJob.DEFAULT_SERVER)

    arg_parser.add_argument('--single-file', '-S', action='store_true',
                            help='save all the summaries in a single file', default=False)
    arg_parser.add_argument('--output', '-o', type=str, metavar='FILE',
                            help='output file name if --single-file or -S is provided', default='summary.json')
    args = arg_parser.parse_args()

    with open(args.jobs, 'r') as jobs_fp:
        print('Reading job file')
        jobs_desc = json.load(jobs_fp)

        print('Username: ' + jobs_desc['username'])

        jenkins_url = args.server
        jenkins_server = \
            StreamblocksBuild.JenkinsJob.getServer(jenkins_url,
                                                   username=jobs_desc['username'], password=jobs_desc['token'])

        user = jobs_desc['username']
        token = jobs_desc['token']
        all_summaries = {}
        for job_info in jobs_desc['jobs']:
            summary = CustomJenkinsJob(job_info, no_prompt=False).getReport(
                jenkins_server, user, token)
            if not args.single_file:
                summary_path = job_info['dir'] + '/instance_report.json'
                with open(summary_path, 'w') as fp:
                    fp.write(json.dumps(summary, indent=4))
            else:
                all_summaries[job_info['name']] = summary

        if args.single_file:
            with open(args.output, 'w') as fp:
                fp.write(json.dumps(all_summaries, indent=4))

        print("All done. Visit %sjob/%s to query the status of your jobs." %
              (jenkins_url, user))
