# Containers e Kubernetes

## Padrão comum

- `Dockerfile` na raiz; build e runtime separados quando há compilação/dependências.
- Processo sem root; credenciais fora da imagem e da configuração versionada.
- `k8s/kustomization.yaml`, namespace `nexus`, imagem `nexus-bi-ai:local` substituível por qualquer registry.
- Sem conta cloud, registry ou integração de autenticação de um provedor específico.
- A infraestrutura é uma alternativa portátil. Não substitui as hospedagens atuais em Discloud, Render e Vercel.
- A CI compila a imagem e renderiza os manifests; não publica imagens nem executa deploys.

## Imagem local

Execute os comandos a partir da raiz deste repositório, com Docker Engine em execução:

```sh
docker build -t nexus-bi-ai:local .
docker run --rm --env-file .env -p 8000:8000 nexus-bi-ai:local
```

## Configuração e credenciais

Prepare um arquivo `.env` local a partir das variáveis documentadas no README e em `.env.example` (quando existir). Ele nunca deve entrar na imagem nem no Git. Bancos e serviços externos precisam ser alcançáveis a partir do cluster; `localhost` dentro do Pod é o próprio container.

```sh
kubectl apply -f k8s/namespace.yaml
kubectl create secret generic nexus-bi-ai-secret --namespace nexus --from-env-file=.env --dry-run=client -o yaml | kubectl apply -f -
```

O Secret é fornecido externamente, sem valores fictícios versionados. Atualizações exigem reiniciar o workload para recarregar variáveis de ambiente.

## Kubernetes em qualquer cluster

É necessário um cluster configurado no seu kubeconfig. Para usar registry remoto:

1. Compile e publique a imagem em um registry sob seu controle.
2. Dentro de `k8s/`, execute `kubectl kustomize` após ajustar `images` no `kustomization.yaml` (ou use `kustomize edit set image nexus-bi-ai=REGISTRY/PROJETO/nexus-bi-ai:TAG`). `REGISTRY`, `PROJETO` e `TAG` são substituições obrigatórias para esse exemplo.
3. Em registry privado, configure `imagePullSecrets` no cluster. Não é necessário um registry específico.

Para Kind/Minikube, carregue `nexus-bi-ai:local` nos nós usando `kind load docker-image` ou `minikube image load`. A política `IfNotPresent` permite a imagem local.

```sh
kubectl kustomize k8s
kubectl apply -k k8s
kubectl rollout status deployment/nexus-bi-ai -n nexus --timeout=5m
kubectl port-forward service/nexus-bi-ai 8080:80 -n nexus
```

O Service é `ClusterIP`: o acesso local é por port-forward. Para produção, configure Ingress/Gateway e TLS conforme o cluster. A configuração não presume LoadBalancer de cloud.

Os probes verificam a inicialização e disponibilidade HTTP do processo, não o funcionamento integral das integrações externas. Ajuste limites de CPU/memória a partir de medições reais.

O serviço inicia um agendador de relatórios no próprio processo. Por isso o exemplo usa uma réplica e estratégia `Recreate`; não escale sem coordenar o agendador. `/app/output` é temporário (emptyDir); use armazenamento persistente se precisar reter arquivos locais, além da persistência externa já configurada.

## Referências

- https://docs.docker.com/build/building/multi-stage/
- https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/
