#!/usr/bin/env python3
import json
import argparse
from zipfile import ZipFile
import os
import shutil
"""
Custom script to extract and copy artifacts to custom directories using
special path strings containing @SOL_NUMBER@, @CORES@, @INDEX@. This is
used with the output of the ilp solver... you do not need to use it:D
"""
if __name__ == "__main__":

    binary_path_example = \
      "generated/rvc_@CORES@/configuration_@SOL_NUMBER@/multicore/bin"
    artifact_path_example = \
      "generated/rvc_unique_@INDEX@_3.3/artifacts.zip"

    arg_parser = argparse.ArgumentParser(
        "place the artifacts downloaded from jenkins into multicore binary directories")
    arg_parser.add_argument(
        "-b", "--bin-pattern",  help=
    """
    Binary path pattern. @CORES@ and @SOL_NUMBER@ substrings will be substituted
    with core count and solution number for each partition. Example:
    -b {example}

    """.format(example=binary_path_example), 
    metavar="STRING", required=True, type=str)

    arg_parser.add_argument(
      "-a", "--artifact-pattern", help="""
    Artifact path pattern to the artifact.zip file fetched from jenkins.
    It should include an @INDEX@ substring represeting the unique partition
    index. Example: 
    -a {example}

    """.format(example=artifact_path_example),
    metavar="STRING", required=True, type=str
    )
    
    arg_parser.add_argument('-m', "--mapping", required=True, type=str, 
    metavar='PATH',  help="""
    Path to json file which maps each heterogeneous solution to the unique
    hardware partition index. Example:
    -m heterogeneous/hardware.json
    """)

    args = arg_parser.parse_args()


    with open(args.mapping, 'r') as mapping_file:

      mappings = json.load(mapping_file)

      if mappings['solutions'] == None or mappings['count'] == None:
        raise RuntimeError("Invalid mapping file")
      solutions = mappings['solutions']
      print("There are %d solutions"%mappings['count'])
      pwd = os.getcwd()
      tmp_dir = pwd + "/extract"

      print("Creating temp directory in " + tmp_dir)
      try: 
        os.makedirs(tmp_dir)
      except FileExistsError:
        shutil.rmtree(tmp_dir + "/")
        
      
      extracted_artifacts = set()
      try:
        for sol in solutions:
          try:
            cores = sol['cores']
            sol_number = sol['index']
            unique_index = sol['hash_index']
            bin_dir = args.bin_pattern.replace("@CORES@", str(cores))
            bin_dir = bin_dir.replace("@SOL_NUMBER@", str(sol_number))
          
            
            artifact_dir = args.artifact_pattern.replace("@INDEX@", 
              str(unique_index))
            
            
            print("""
            -----------------------cores: {c:2d} number: {n:2d}---------------------------
            bin directory: 
            {bin_dir}
            artifact directory:
            {artifact_dir}""".format(c=cores, n=sol_number, 
              bin_dir=bin_dir, artifact_dir=artifact_dir))
            if not os.path.isfile(artifact_dir):
              print("""
            artifact file does not exits! Skipping copy.
            """)
            else:
            
              if not (unique_index in extracted_artifacts):
                extract_dir = tmp_dir + "/" + str(unique_index)
                if not os.path.exists(extract_dir):
                  os.makedirs(extract_dir)
                print("""
            extracting artifacts into {}
              """.format(extract_dir))
              
                with ZipFile(artifact_dir, 'r') as f:
                  f.extractall(extract_dir)
                
                extracted_artifacts.add(unique_index)
              print("""
            copying artifacts
            """)
              src_dir = extract_dir + "/archive/project/bin/xclbin"
              dst_dir = bin_dir + '/xclbin'
              if os.path.exists(dst_dir):
                print("""
            overwriting existing files
                """)
                shutil.rmtree(dst_dir)
              shutil.copytree(src_dir, dst_dir)
            print("""
            ======================================================================
            """)
          
          
          except KeyError as e:
            raise KeyError("Invalid Solution entry!: \n" + e)
          
      except Exception as e:
        print("Errors occured! \n" + str(e))
        # shutil.rmtree(tmp_dir)
      
      shutil.rmtree(tmp_dir)
        


