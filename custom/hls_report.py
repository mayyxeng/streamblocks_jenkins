#!/usr/bin/env python3
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

    def makeDirectory(path):
      StreamblocksBuild.Utilities.forceMakeDirectory(path)

    def getReport(self, server, user, token):
        """
        Downloads the job artifacts and extracst hls instance reports and
        network synthesis and timing reports
        """
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

        instance_summary = CustomJenkinsJob.__get_instance_report__(
            extract_dir)
        network_summary = CustomJenkinsJob.__get_synthesis_report__(
            extract_dir)
        return {
            'network_synth': network_summary,
            'instance_synth': instance_summary
        }

  
    def __get_synthesis_report__(extract_dir):
        """
        Get the resource and timing report in a dictionary
        """
        timing_report_path = extract_dir + 'archive/project/bin/reports/timing_summary.rpt'
        result = {'timing': None, 'utilization': None}
        # if os.path.exists(timing_report_path):

        utilization_report_path = extract_dir + \
            'archive/project/bin/reports/report_utilization.rpt'
        util_report = StreamblocksBuild.Utilities.__get_utilization_report__(
            utilization_report_path)
        timing_report = StreamblocksBuild.Utilities.__get_timing_report__(
            timing_report_path)
        return {
            'utilization': util_report,
            'timing': timing_report
        }

    def __get_instance_report__(extract_dir):

        instance_report_gz_path = extract_dir + 'archive/project/bin/instance_reports.tar.gz'
        if not os.path.exists(instance_report_gz_path):
            StreamblocksBuild.printError(
                "Instance report file does not exist at " + str(instance_report_gz_path))
            return None
        instance_tar = tarfile.open(instance_report_gz_path, 'r:gz')
        instance_report_dir = extract_dir + '/instnace_reports'
        CustomJenkinsJob.makeDirectory(instance_report_dir)
        instance_tar.extractall(instance_report_dir)
        hls_projects_root = instance_report_dir + '/build/vivado-hls'
        return StreamblocksBuild.Utilities.__get_instance_report__(hls_projects_root)
        

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
        all_summaries = []
        for job_info in jobs_desc['jobs']:
            summary = CustomJenkinsJob(job_info, no_prompt=False).getReport(
                jenkins_server, user, token)
            if not args.single_file:
                summary_path = job_info['dir'] + '/instance_report.json'
                job_info['artifacts'] = summary
                with open(summary_path, 'w') as fp:
                    fp.write(json.dumps(job_info, indent=4))
            else:
                all_summaries.append(job_info)

        if args.single_file:
            with open(args.output, 'w') as fp:
                fp.write(json.dumps(all_summaries, indent=4))

        print("All done. Visit %sjob/%s to query the status of your jobs." %
              (jenkins_url, user))
