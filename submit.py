import subprocess
import argparse
import json
import jenkins
import tarfile
import os


import sys

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



def buildJob(server, job_name, user, token, job_info):

  root_dir = os.getcwd()

  job_url = server.get_job_info(job_name)['url']
  job_build_url = job_url + "/buildWithParameters"
  
  def tardir(paths, tar_name):    
    with tarfile.open(tar_name, 'w:gz') as tar_handle:
      for path in paths:
          tar_handle.add(path, recursive=True)

  tarbal = job_info['name'] + '.tar.gz'
  tar_sources = [
    'vivado-hls',
    'multicore',
    'CMakeLists.txt'
  ]
  
  print("Creating compressesd file " + tarbal)
  os.chdir(job_info['dir'])

  tardir(tar_sources, tarbal)


  forms = "--form submission_file=@" + "./" + tarbal + " "
  forms = forms + "--form NETWORK_NAME=" + job_info['network'] + " "
  for p in job_info['params']:
    this_param = job_info['params'][p]
    if type(this_param) != str:
      this_param = str(this_param)
    forms = forms + "--form " + p + "=" + this_param + " "
  
  # This is a very ugly way of doing things, all because I can not send
  # a file using the python api...
  
  curl_cmd = "curl " + job_build_url + " --user " + user  + ":" + token + " " + forms
  
  
  curl = subprocess.run(curl_cmd, shell=True, stdout=subprocess.PIPE)

  print("Cleaning up temp archives")
  
  os.remove(tarbal)
  os.chdir(root_dir)

  if curl.returncode != 0:
    print("Enqueue failed\n%s"%(curl_cmd))
  


def cleanJob(server, job_name):
  server.delete_job(job_name)

if __name__ == "__main__":

  args_parser = argparse.ArgumentParser(description="Submit streamblocks generated code to build server")
  args_parser.add_argument('jobs', type=str, metavar='FILE', help='json build jobs configuration file')
  
  # args_parser.add_argument('token_file', type=str, metavar='TOKEN' help='path to token file')
  args = args_parser.parse_args()

  with open (args.jobs, 'r') as build_config_file:

    print("Reading build config:")
    build_config = json.load(build_config_file)
    
    print("Username: " +  build_config['username'])
    print("There are %d jobs to submit" %(len(build_config['jobs'])))

    jenkins_url = 'http://iccluster126.iccluster.epfl.ch:8080/'
    jenkins_server = jenkins.Jenkins(jenkins_url, 
      username=build_config['username'], password=build_config['token'])
    
    user = build_config['username']
    token = build_config['token']

    template_name = 'templates/shell_build_template'
    print("Pulling job template from jenkins %s"%(template_name))
    job_template = jenkins_server.get_job_config(template_name)

    for job_info in build_config['jobs']:
      
      operation = job_info['operation']
      print("Requesting %s job %s"%(operation, job_info['name']))
      
      job_name = build_config['username'] + '/' + job_info['name']
      
      job_exists = jenkins_server.job_exists(job_name)
      
      
      if operation == "build":
        should_build = False
        if job_exists:
          should_build = queryYesNo("Job " + job_info['name'] + " already exists, do you want to rebuild?", 'yes')
        else:
          jenkins_server.create_job(job_name, job_template)
          should_build = True
        if should_build:
          try:

            buildJob(jenkins_server, job_name, user, token, job_info)
          except subprocess.SubprocessError as err:
            print("Failed to enqueue job %s\n:"%(job_info['name'], err))
            pass
      
      elif operation == "clean":

        if job_exists and queryYesNo("Do you want to clean job " + job_info['name'] + "?", 'no'):
          cleanJob(jenkins_server, job_name)
        else:
          print("Skipping job " + job_info['name'])
      
    print("All done. Visit %sjob/%s to query the status of your jobs."%(jenkins_url, user))
      # q = jenkins_server.get_queue_info()
      # import pprint
      # pp = pprint.PrettyPrinter(indent=4)
      # pp.pprint(q)

      # job_url = jenkins_server.get_job_info(job_name)['url']
      # job_build_url = job_url + "/buildWithParameters"
      
      # forms = "--form submission_file=@" + "job_extract_0/example.tar.gz "
      # for p in job_info['params']:
      #   this_param = job_info['params'][p]
      #   if type(this_param) != str:
      #     this_param = str(this_param)
      #   forms = forms + "--form " + p + "=" + this_param + " "
      
      # # This is a very ugly way of doing things, all because I can not send
      # # a file using the python api...
      # print(forms)
      # curl_cmd = "curl " + job_build_url + " --user " + user  + ":" + token + " " + forms
      # print(curl_cmd) 
      # curl = subprocess.run(curl_cmd, shell=True, stdout=subprocess.PIPE)
      # if curl.returncode != 0:
      #   print("Enqueue failed\n%s"%s(curl_cmd))


      # print(job_info['params'])
      # q_item = jenkins_server.build_job(job_name, job_info['params'])

      
    

  