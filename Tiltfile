# The only way the stack runs, locally and in CI. k8s/ is the one description
# of what processes exist; `make up` runs this and waits for it.
services = ['users', 'canvas', 'redis', 'postgres', 'ingress']
k8s_yaml(["k8s/%s.yaml" % s for s in services])

# `dev` targets: pytest and ruff are in the image, so `make tests` execs into the
# running pod, and the syncs below keep the pods on your working tree. uvicorn
# --reload picks the change up; no rebuild, no restart.
docker_build('users', 'users', target='dev', live_update=[
    sync('users/app', '/app/app'),
    sync('users/tests', '/app/tests'),
])
docker_build('canvas', 'canvas', target='dev', live_update=[
    sync('canvas/app', '/app/app'),
    sync('canvas/tests', '/app/tests'),
])
# arq does not reload, so the worker just rebuilds; the layer cache makes that
# a copy, not a reinstall.
docker_build('canvas-worker', 'canvas', target='worker')

# Ordering is the initContainers' job (wait-database, perform-migrations), so
# none is declared here.
k8s_resource('users-deployment', port_forwards='8000:80')
k8s_resource('canvas-deployment', port_forwards='8001:80')

# Built from load/ on every Tiltfile run, so the ConfigMap cannot drift from it.
watch_file('load/locustfile.py')
k8s_yaml(local('kubectl create configmap locustfile --from-file=load/locustfile.py --dry-run=client -o yaml'))
k8s_yaml('k8s/locust.yaml')
k8s_resource('locust', port_forwards='8089:8089', auto_init=False,
             trigger_mode=TRIGGER_MODE_MANUAL)
