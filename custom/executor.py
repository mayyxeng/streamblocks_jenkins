import subprocess
import re 
import json

import numpy as np
import time
import pathlib

class PartitionExecutor:


  def __init__(self, partitions_path, bin_path):

    self.bin_path = bin_path
    self.partitions_path = partitions_path

    with  open (partitions_path + '/heterogeneous/hardware.json', 'r') as m_file:
      
      print('Reading mappings file ')
      self.mapping = json.load(m_file)
      print('There are %d solutions'%len(self.mapping['solutions']))

  def programDevice(self, xclbin):

    shell_command = 'xbutil program -p ' + xclbin
    run = subprocess.run(shell_command, shell=True)

    if run.returncode != 0:
      raise RuntimeError("""
    could not program the device using {file}
      """.format(file=xclbin))
  
  def runSolution(self, solution, args=''):

    cores = 0
    try:
      cores = solution['cores']
    except KeyError:
      raise KeyError('Invalid solution format: ' + 
        json.dumps(solution, indent=4) + "\n missing \'cores\' entry")

    sol_number = 0
    try:
      sol_number = solution['index']
    except KeyError:
      try:
        sol_number = solutoin['sol_number']
      except KeyError:
        raise KeyError('Invalid solution format: ' + 
          json.dumps(solution, indent=4) + "\n missing \'sol_number\' entry")

    unique_index = 0
    try:
      unique_index = solution['hash_index']
    except KeyError:
      try:
        unique_index = solution['index']
      except KeyError:
        raise KeyError('Invalid solution format: ' + 
          json.dumps(solution, indent=4) + "\n missing \'index\' entry")

  
    binary_path = pathlib.Path(self.bin_path.replace("@INDEX@", str(unique_index)))

    if binary_path.is_file() == False:
      raise RuntimeError("Binary file " + str(binary_path) + " does not exits")
    
    program_name = binary_path.name
    
    print(program_name)

    exec_dir = pathlib.Path(binary_path).parent

    shell_command = './' + str(program_name) + ' ' + args

    run = subprocess.run(shell_command, shell=True, stdout=subprocess.PIPE, cwd=str(exec_dir))

    if run.returncode != 0:
      print(""" 
      Failed to execute:
      {cmd}
      in direcotory {dir}, program returned {code}

      {err}
      """.format(cmd=shell_command, dir=exec_dir, code=run.returncode, err=run.stdout))
      return None
    else:
      regex = re.compile(r'(\d*) images in (\d*\.\d*) seconds: (\d*\.\d*) FPS')
      perf = {'frames' : 0, 'trips' : 0, 'time' : 0}
      for ln in run.stdout.decode("utf-8").split('\n'):
        # print(ln)
        matches = regex.match(ln)
        if (matches != None):
          frames = int(matches.group(1))
          exec_time = float(matches.group(2))
          fps = float(matches.group(3))
          return (frames, exec_time, fps)
      
      raise RuntimeError("Could not measure performance!")
      



if __name__ == "__main__":

  
  executor = PartitionExecutor('pwr_fixed', 'unique_@INDEX@_3.3/bin/Top_RVC_Decoder')
  executor.runSolution({'index' : 0, 'sol_number' : 0, 'cores' : 1}, '--i=foreman_qcif_30.bit --l=1')


