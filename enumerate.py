#!/usr/bin/env python3

import argparse
import json


if __name__ == "__main__":

    args_parser = argparse.ArgumentParser(description="""
  Enumerate streamblocks generated code job description and produce jenkins job descriptions
  An example job template job descritption can have name, dir, and network
  fields containing @INDEX@ substring that will be replaced
  by indices that is defined by the --start and --end switches.
  """)
    args_parser.add_argument(
        'jobs', type=str, metavar='FILE', help='json build job base configuration file')
    args_parser.add_argument('--start', metavar="n",
                             type=int, help="start post-fix", required=True)
    args_parser.add_argument('--end', metavar="N",
                             type=int, help='end post-fix', required=True)
    args_parser.add_argument('--output', metavar="FILE",
                             type=str, help="outptut file", default='enumerated.json')
    args_parser.add_argument('--operation', metavar="OP", type=str, choices=['build', 'clean', 'query', 'download'],
                             help='type of operation, overrides existing', default='build')
    args_parser.add_argument('--clocks', nargs='+', default=['3.3'])
    args = args_parser.parse_args()

    with open(args.jobs, 'r') as build_config_file:

        print("Reading build config:")
        build_config = json.load(build_config_file)

        user = build_config['username']
        token = build_config['token']
        jobs_desc = []
        for job in build_config['jobs']:
            for i in range(args.start, args.end + 1, 1):
                for clk in args.clocks:
                    new_job = job.copy()
                    new_job['name'] = new_job['name'].replace("@INDEX@", str(i))
                    new_job['name'] = new_job['name'].replace("@CLOCK@", str(clk))
                    new_job['dir'] = new_job['dir'].replace("@INDEX@", str(i))
                    new_job['dir'] = new_job['dir'].replace("@CLOCK@", str(clk))
                    new_job['network'] = new_job['network'].replace(
                        "@INDEX@", str(i))
                    new_job['network'] = new_job['network'].replace(
                        "@CLOCK@", str(clk))
                    new_job['params'] = job['params'].copy()
                    new_job['params']['HLS_CLOCK_PERIOD'] = float(clk)
                    new_job['params']['KERNEL_FREQ'] = int(1000. / float(clk))
                    new_job['operation'] = args.operation
                    
                    jobs_desc.append(new_job)

        build_config['jobs'] = jobs_desc
        with open(args.output, 'w') as output_file:
            output_file.write(json.dumps(build_config, indent=4))
