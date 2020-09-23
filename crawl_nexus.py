#!/usr/bin/env python3

from optparse import OptionParser
import os
import requests
import json
import tempfile
import urllib.request


def http_get(url):
    response = urllib.request.urlopen(url)
    return response.read().strip()


def file_get_contents(filename):
    with open(filename) as f:
        return f.read().strip()


def verify_md5sum(localdir, remotedir, filename):
    local_sum = file_get_contents(os.path.join(localdir, filename))
    remote_sum = http_get(os.path.join(remotedir, filename))
    return (local_sum == remote_sum, local_sum, remote_sum)


parser = OptionParser("Crawl a Nexus repo to verify all files under $1 are present.")

parser.add_option("--maven-repository", action="store", help="Folder containing the exploded maven-repository")
parser.add_option("--repository-name", action="store",
                  help="Repository name or release group to test. Defaults to /ga/", default="ga")
parser.add_option("--jars-only", action="store_true", help="Check for .jar files only")
parser.add_option("--verbose", action="store_true", help="Print results for each file/folder", default=None)
parser.add_option("--json", action="store_true", help="Dump missing artifacts to a .json file", default=None)
parser.add_option("--test", action="store_true", help="Don't actually HTTP GET artifacts", default=None)
parser.add_option("--md5", action="store_true", help="Verify md5 checksums", default=None)
parser.add_option("--sha1", action="store_true", help="Verify sha1 checksums", default=None)

opts, args = parser.parse_args()

if not opts.maven_repository:
    print("Must specify a maven-repository folder")
    exit(-1)

if not opts.verbose and not opts.json:
    print("Must specify at least one of --verbose or --json")
    exit(-2)

MAVEN_REPO = opts.maven_repository

NEXUS_ROOT = "https://maven.repository.redhat.com"
REPO_ROOT = NEXUS_ROOT + "/" + opts.repository_name + "/"

dir_errors = []
file_errors = []
for dirpath, dirnames, filenames in os.walk(MAVEN_REPO):
    r_dirpath = dirpath.replace(MAVEN_REPO, '')
    if not opts.test:
        res = requests.head(REPO_ROOT + r_dirpath)
        if opts.verbose:
            print("%s is %s: %s" % (r_dirpath, res.status_code, res.text))
        if not res.status_code in (301, 302, 200):
            dir_errors.append({"artifact_url": r_dirpath, "error_code": res.status_code, "text": res.text})
            # If folder is missing/misconfigured, assume all files under it are missing and skip them
            continue
    else:
        print("%s: Would have been probed" % (r_dirpath))

    if opts.jars_only:
        filelist = [filename for filename in filenames if filename.endswith(".jar")]
    else:
        filelist = [filename for filename in filenames if
                    not filename.endswith('md5') and not filename.endswith('sha1')]
    for filename in filelist:
        artifact = os.path.join(r_dirpath, filename)
        if not opts.test:
            res = requests.head(REPO_ROOT + artifact)
            if opts.verbose:
                print("%s is %s: %s" % (artifact, res.status_code, res.text))
            if not res.status_code in (200,):
                file_errors.append({"artifact_url": filename, "error_code": res.status_code, "text": res.text})
                continue
            if opts.md5:
                md5sum, local_sum, remote_sum = verify_md5sum(dirpath, REPO_ROOT + r_dirpath, filename + ".md5")
                if md5sum:
                    md5sum_s = 'OK'
                else:
                    md5sum_s = 'FAIL'
                    file_errors.append({"artifact_url": filename, "error_code": 'md5sum FAIL', "local": local_sum,
                                        "remote": remote_sum})
                if opts.verbose:
                    print('md5sum %s (%s, %s)' % (md5sum_s, local_sum, remote_sum))

        else:
            if opts.verbose:
                print("%s: Would have been probed" % (artifact))

if opts.json:
    results = {"missing_dirs": dir_errors, "missing_files": file_errors}
    tf = tempfile.NamedTemporaryFile(prefix='nexus_crawl_', mode='w+t', delete=False)
    json.dump(results, tf, indent=2)
    print("JSON results saved in %s" % tf.name)
