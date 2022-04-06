
import subprocess
import traceback
import argparse
import json
import os


def get_args():
    parser = argparse.ArgumentParser(
        description='Script to get security info from deployed containers')
    parser.add_argument(
        '-c', '--cluster', type=str, help='Kubernetes cluster name', required=True)
    parser.add_argument(
        '-n', '--namespace', type=str, help='Kubernetes namespace', required=True)
    parser.add_argument(
        '-f', '--file', type=str, help='Output file for pod info', required=True)
    args = parser.parse_args()
    return args.cluster, args.namespace, args.file


def execute_cmd(command):
    output = subprocess.check_output([command], shell=True)
    return output


def get_kube_artifacts(command, prefixes):
    items = []
    output = execute_cmd(command)
    items_json = json.loads(output)
    for item in items_json['items']:
        name = item['metadata']['name']
        for prefix in prefixes:
            if name[0:len(prefix)] == prefix:
                items.append(item)
                break
    return items


def de_dup_pods(pods):
    unique_pods = []
    last_pod_name = ''
    for pod in pods:
        pod_name = pod['metadata']['name']
        base_pod_name = pod_name[0: pod_name.rfind("-")]
        if base_pod_name != last_pod_name:
            last_pod_name = base_pod_name
            unique_pods.append(pod)
    return unique_pods


def write_pod_info(pods, filename):
    file = open(filename, 'w')
    file.write(json.dumps(pods, indent=4))
    file.close()

def main():
    try:
        print("Be sure to first:")
        print("ibmcloud login --sso -a https://cloud.ibm.com")
        print("Pick the environment, PPRD, PSTG, etc")
        print("Then (same thing pick the right environment):")
        print("~/kubectl-helper-master/setup.sh")
        print("Finally (same thing pick the right environment:")
        print("~/kubectl-helper-master/switch.sh")
        print("When issuing kubectl commands, be sure to specif namespace, e.g. -n namespace")
        cluster, namespace, filename = get_args()
        artifact_prefixes = ['ga-', 'sireg']
        command = "kubectl get pods -n %s -o json" % namespace
        all_pods = get_kube_artifacts(command, artifact_prefixes)
        pods = de_dup_pods(all_pods)
        command = "kubectl get services -n %s -o json" % namespace
        services = get_kube_artifacts(command, artifact_prefixes)
        command = "kubectl get deployments -n %s -o json" % namespace
        deployments = get_kube_artifacts(command, artifact_prefixes)

        write_pod_info(pods, filename)

        print('\nPorts:')
        for service in services:
            print("\t%s" % service['metadata']['name'])
            for port in service['spec']['ports']:
                print("\t\t%s" % port)

        print('\n\nIDs and authority:')
        for pod in pods:
            pod_name = pod['metadata']['name']
            print(pod_name)
            try:
                id_bytes = execute_cmd("kubectl exec -it -n %s %s -- bash -c 'ps -eaf'" %
                                    (namespace, pod_name))
                ids = id_bytes.decode('utf-8')
                print("\n%s\n" % ids)
            except Exception as e:
                print("Error retrieving id info\n")

    except Exception as e:
        print('Error: ' + str(e))
        traceback.print_exc()


if __name__ == '__main__':
    main()
