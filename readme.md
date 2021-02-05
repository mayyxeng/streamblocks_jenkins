# Streamblocks build and clean submission script for Jenkins

This is a simple script to submit a `build` or `clean` job to Jenkins. The
script takes a json _job description_. And example is provided in 
`job_example.json`. 

```bash
python3 submit.py job_example.py
```

To configure the operation (i.e., build or clean) modify your job description
json. You can have a mix of build and clean jobs.

Jenkins job template is pulled from the Jenkins server, and example job 
template is provided in `template.xml`. 

A script for retrieving artifacts after builds will be added.