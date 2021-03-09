#!/usr/bin/env python3
import json
from zipfile import ZipFile
import argparse
import sys
import os
import inspect


try:
    from .. import StreamblocksBuild
except ImportError as e:
    currentdir = os.path.dirname(os.path.abspath(
        inspect.getfile(inspect.currentframe())))
    parentdir = os.path.dirname(currentdir)
    sys.path.insert(0, parentdir)
    import StreamblocksBuild

from xml.dom import minidom


"""
Aggeragate the hls reports of different synthesized actors into a json file
"""


class SystemCJob(StreamblocksBuild.JenkinsJob):
    class ActorStat():

        def __init__(self, element):

            self.id = element.attributes["id"].value
            self.total_cycles = int(
                element.attributes["clockcycles-total"].value)

            self.firings = int(element.attributes["firings"].value)

            triggerElement = element.getElementsByTagName("trigger")[0]
            self.trigger = {
                "IDLE_STATE": int(triggerElement.attributes["IDLE_STATE"].value),
                "LAUNCH": int(triggerElement.attributes["LAUNCH"].value),
                "CHECK": int(triggerElement.attributes["CHECK"].value),
                "SLEEP": int(triggerElement.attributes["SLEEP"].value),
                "SYNC_LAUNCH": int(triggerElement.attributes["SYNC_LAUNCH"].value),
                "SYNC_CHECK": int(triggerElement.attributes["SYNC_CHECK"].value),
                "SYNC_WAIT": int(triggerElement.attributes["SYNC_WAIT"].value),
                "SYNC_EXEC": int(triggerElement.attributes["SYNC_EXEC"].value)
            }

        def getId(self):
            return self.id

        def getCycles(self):
            return self.total_cycles

        def getFirings(self):
            return self.firings

        def getSleeps(self):
            return self.trigger["SLEEP"]

        def getSyncCycles(self):
            return self.trigger["SYNC_EXEC"] + self.trigger["SYNC_WAIT"]

    def makeDirectory(path):
        StreamblocksBuild.Utilities.forceMakeDirectory(path)

    def getReport(self, server, runs, user, token):
        """
        Downloads the job artifacts and extract systemc profile information
       
        """
        self.download(server, user, token)

        artifact_path = self.dir + '/artifacts.zip'

        if not os.path.exists(artifact_path):
            StreamblocksBuild.printError(
                "Artifact file " + str(artifact_path) + " does not exist")
            return
        extract_dir = os.path.abspath(self.dir) + '/extracted/'
        SystemCJob.makeDirectory(extract_dir)

        print("Extracting artifacts to " + extract_dir)
        with ZipFile(artifact_path, 'r') as zfp:
            zfp.extractall(extract_dir)

        return [
            {'run_name': r, 'profile': SystemCJob.__get_run_profile__(r, extract_dir)} for r in runs
        ]

    def __get_run_profile__(run, extract_dir):

        bin_dir = extract_dir + '/archive/project/bin/' + run

        if not os.path.exists(bin_dir):
            StreamblocksBuild.printError(
                "Run %s does not exists at %s" % (run, bin_dir))
            return None

        exdf_path = bin_dir + "/" + run + ".exdf"

        if not os.path.exists(exdf_path):
            StreamblocksBuild.printError(
                "Can not open exdf file at %s" % exdf_path)
            return None

        exdf_profile = minidom.parse(exdf_path)

        all_actor_elements = exdf_profile.getElementsByTagName('actor')

        valid_actor_elements = list(filter(
            lambda e: e.attributes['id'].value.find('fanout') == -1,
            all_actor_elements
        ))

        def parseActorStats(actor_elem):
            id = actor_elem.attributes["id"].value
            total_cycles = int(
                actor_elem.attributes["clockcycles-total"].value)
            firings = int(actor_elem.attributes["firings"].value)
            action_elems = actor_elem.getElementsByTagName('action')

            actions = [{
                'id': e.attributes['id'].value,
                'mean_cycles': float(e.attributes['clockcycles'].value),
                'max_cycles': int(e.attributes['clockcycles-min'].value),
                'min_cycles': int(e.attributes['clockcycles-max'].value),
                'total_cycles': int(e.attributes['clockcycles-total'].value),
                'firings': int(e.attributes['firings'].value)
            } for e in action_elems]

            triggerElement = actor_elem.getElementsByTagName("trigger")[0]

            trigger = {
                "IDLE_STATE": int(triggerElement.attributes["IDLE_STATE"].value),
                "LAUNCH": int(triggerElement.attributes["LAUNCH"].value),
                "CHECK": int(triggerElement.attributes["CHECK"].value),
                "SLEEP": int(triggerElement.attributes["SLEEP"].value),
                "SYNC_LAUNCH": int(triggerElement.attributes["SYNC_LAUNCH"].value),
                "SYNC_CHECK": int(triggerElement.attributes["SYNC_CHECK"].value),
                "SYNC_WAIT": int(triggerElement.attributes["SYNC_WAIT"].value),
                "SYNC_EXEC": int(triggerElement.attributes["SYNC_EXEC"].value)
            }

            return {
                'id': id,
                'total_cycles': total_cycles,
                'firings': firings,
                'actions': actions,
                'trigger': trigger
            }

        actors = [parseActorStats(e) for e in valid_actor_elements]
        network_elem = exdf_profile.getElementsByTagName('network')[0]
        total_cycles = int(network_elem.attributes['clockcycles-total'].value)
        trip_count = int(network_elem.attributes['runs'].value)

        return {
            'name': network_elem.attributes['name'].value,
            'total_cycles': total_cycles,
            'trip_count': trip_count,
            'actors': actors
        }


if __name__ == "__main__":

    arg_parser = argparse.ArgumentParser(
        "Summarize systemc simulation profiles of jobs into json files"
    )
    arg_parser.add_argument('jobs', type=str, metavar='FILE',
                            help='json build jobss configuration file')
    
    arg_parser.add_argument('-s', '--server', type=str, metavar='URL',
                            help='jenkins server address url', default=StreamblocksBuild.JenkinsJob.DEFAULT_SERVER)
    arg_parser.add_argument('--runs', '-r', nargs='+', required=True,
                            help="REQUIRED List of run names, e.g, -r bust_cif_15 foreman_qqcif_30")
    arg_parser.add_argument('--single-file', '-S', action='store_true',
                            help='save all the summaries in a single file', default=False)
    arg_parser.add_argument('--output', '-o', type=str, metavar='FILE',
                            help='output file name if --single-file or -S is provided', default='summary.json')
    arg_parser.add_argument('-y', '--no-prompt', action='store_true', default=False, help="do not prompt")
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
            summary = SystemCJob(job_info, no_prompt=args.no_prompt).getReport(
                jenkins_server, args.runs, user, token)
            
            job_info['artifacts'] = summary
            if not args.single_file:
                summary_path = job_info['dir'] + '/profile_summary.json'
                with open(summary_path, 'w') as fp:
                    fp.write(json.dumps(job_info, indent=4))
            else:
                
                all_summaries.append(job_info)

        if args.single_file:
            with open(args.output, 'w') as fp:
                fp.write(json.dumps(all_summaries, indent=4))

        print("All done. Visit %sjob/%s to query the status of your jobs." %
              (jenkins_url, user))
