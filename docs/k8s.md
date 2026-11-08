# Kubernetes Quick Reference

## What You Have

- **Deployments (stateless, can scale):** users, canvas, redis. Change `replicas: 1` to `3` to scale.
- **StatefulSet (stateful, ordered):** postgres. Use for anything with persistent state.
- **Ingress:** Routes traffic. Users on `users.minikube`, canvas on `canvas.minikube`.
- **Services:** Internal DNS. Canvas reaches users via `http://users-service`.

## Scaling Without YAML Sprawl

**Now (6 files):** Each YAML file is explicit. Works fine.

**When you hit 4+ services:** Use Kustomize overlays.

```
k8s/
├── base/                    # Canonical config
│   ├── users/deployment.yaml
│   ├── canvas/deployment.yaml
│   └── kustomization.yaml
└── overlays/
    ├── dev/kustomization.yaml      # replicas: 1
    ├── staging/kustomization.yaml  # replicas: 2
    └── prod/kustomization.yaml     # replicas: 3
```

Deploy with: `kubectl apply -k k8s/overlays/prod`

**When you hit 5+ services:** Helm charts. One `values.yaml` + template, deploy each service with different values.

**When templates get complex (nested `{{- if }}`):** Pulumi/CDK. Write infrastructure as actual code.

## Horizontal Scaling

```yaml
spec:
  replicas: 3  # Kubernetes spreads pods, load-balances, replaces failed ones
```

Add this to stateless services (users, canvas). Stateless = no local data, replicas are interchangeable.

For resilience, also add:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: users-pdb
spec:
  minAvailable: 1  # Keep 1 running during updates/failures
  selector:
    matchLabels:
      app: users
```

## Local Development

```bash
kubectl apply -f k8s/
kubectl logs -f deployment/users-deployment
kubectl port-forward svc/users-service 8080:80
curl http://localhost:8080/api/health/
```

## Production (GitOps)

Don't run `kubectl apply` manually. Instead:

1. Commit manifests to git
2. Create PR (manifests are reviewed like code)
3. Merge
4. ArgoCD watches git, auto-applies to cluster

This gives audit trail, auto-rollback via `git revert`, disaster recovery (git is source of truth).

## Common Debugging

```bash
# Pod won't start
kubectl describe pod <name>  # Check Events section

# Pod is running but unhealthy
kubectl logs <pod>  # Check app logs
curl http://service-name/api/health/  # Test endpoint

# Services can't reach each other
kubectl exec -it <pod> -- curl http://other-service  # Test DNS + connectivity

# Migrations fail
kubectl logs <pod> -c perform-migrations  # InitContainers run first
kubectl rollout restart deployment/<name>  # Retry migrations
```

## Secrets (Development Only)

Current setup: base64-encoded (not encrypted). For production, use Vault or external secret manager + encryption at rest.

## Cost: Resource Requests/Limits

```yaml
resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi
```

Kubernetes uses requests to schedule pods efficiently. Find values by: deploy, run under load, check `kubectl top pod`, set requests to 1.2x observed.
