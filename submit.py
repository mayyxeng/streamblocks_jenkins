#!/usr/bin/env python3
import argparse
from StreamblocksBuild import JenkinsJob
import json

if __name__ == "__main__":

    default_server = JenkinsJob.DEFAULT_SERVER
    default_template = JenkinsJob.DEFAULT_TEMPLATE
    args_parser = argparse.ArgumentParser(
        description="Submit streamblocks generated code to build server")
    args_parser.add_argument(
        'jobs', type=str, metavar='FILE', help='json build jobs configuration file')
    args_parser.add_argument('-t', '--template', type=str, metavar="TEMPLATE",
                             help='jenkins job template, if not provided the default job template is pulled from the server', default=default_template)
    args_parser.add_argument('-s', '--server', type=str, metavar="URL",
                             help="jenkins server address url", default=default_server)
    args_parser.add_argument(
        '-y', '--no-prompt', help='Do not prompt for clean or query jobs', action='store_true', default=False)
    args = args_parser.parse_args()

    with open(args.jobs, 'r') as build_config_file:

        print("Reading build config:")
        build_config = json.load(build_config_file)

        print("Username: " + build_config['username'])
        print("There are %d jobs to submit" % (len(build_config['jobs'])))

        jenkins_url = args.server
        jenkins_server = JenkinsJob.getServer(jenkins_url,
                                              username=build_config['username'], password=build_config['token'])

        user = build_config['username']
        token = build_config['token']
        for job_info in build_config['jobs']:
            JenkinsJob(job_info, args.no_prompt).submit(
                jenkins_server, user, token, args.template)
        print("All done. Visit %sjob/%s to query the status of your jobs." %
              (jenkins_url, user))
