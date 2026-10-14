# Local Minikube overlay

Use the named `wonderland` Minikube profile inside the separate `wonderland` Colima VM. Credentials live only in ignored `secrets/kubernetes.env` and are applied in memory on stdin, without last-applied annotations. The dedicated ignored `secrets/minikube.kubeconfig` avoids the default kubectl context. See [local Kubernetes guide](../../../docs/local-kubernetes.md).

Deploy ordering is PostgreSQL ready → SQL migration complete → APIs/frontend ready. `kubectl apply -k` alone does not guarantee migration ordering; use the script. The local queue and operational data share one persistent PostgreSQL volume. Stopping the cluster preserves it. Namespace/cluster/volume deletion would delete the isolated demo data and is deliberately absent from the deployment helper.
