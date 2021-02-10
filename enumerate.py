import subprocess
import argparse
import json
import jenkins
import tarfile
import os


import sys



if __name__ == "__main__":

  args_parser = argparse.ArgumentParser(description="Enumerate streamblocks generated code and produce jenkins job descriptions")
  args_parser.add_argument('jobs', type=str, metavar='FILE', help='json build job base configuration file')
  args_parser.add_argument('--start', metavar="n", type=int, help="start post-fix", required=True)
  args_parser.add_argument('--end', metavar="N", type=int, help='end post-fix', required=True)
  args_parser.add_argument('--output', metavar="FILE", type=str, help="outptut file", default='enumerated.json')
  args = args_parser.parse_args()

  with open (args.jobs, 'r') as build_config_file:

    print("Reading build config:")
    build_config = json.load(build_config_file)
    
    
    jenkins_url = 'http://iccluster126.iccluster.epfl.ch:8080/'
    jenkins_server = jenkins.Jenkins(jenkins_url, 
      username=build_config['username'], password=build_config['token'])
    
    user = build_config['username']
    token = build_config['token']
    jobs_desc = []
    for job in build_config['jobs']:
      for i in range(args.start, args.end + 1, 1):
        new_job = job.copy()
        new_job['name'] = new_job['name'].replace("@INDEX@", str(i))
        new_job['dir'] = new_job['dir'].replace("@INDEX@", str(i))
        jobs_desc.append(new_job)

    build_config['jobs'] = jobs_desc
    with open(args.output, 'w') as output_file:
      output_file.write(json.dumps(build_config, indent=4))
     
    

  