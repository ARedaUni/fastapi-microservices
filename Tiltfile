services = ['users', 'users-worker', 'canvas', 'redis', 'postgres', 'ingress']
yaml_files = ["k8s/%s.yaml" % service for service in services]

k8s_yaml(yaml_files)
docker_build('users', 'users', dockerfile='users/Dockerfile', target='prod')
docker_build('users-worker', 'users', dockerfile='users/Dockerfile', target='worker')
docker_build('canvas', 'canvas', dockerfile='canvas/Dockerfile', target='prod')
k8s_resource(workload="users-deployment", port_forwards="8000:80")
k8s_resource(workload="canvas-deployment", port_forwards="8001:80")
