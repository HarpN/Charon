# Charon Agent

Charon is the orchestration agent for the Trophy Backlog Command Center. It transforms user intent into deterministic proposal payloads, signs them, and sends them to Judy Council over gRPC for judgment or commit.

## Architecture Role

- **Zone**: Agent Zone (untrusted orchestration layer)
- **Primary responsibility**: Convert user intent into structured proposal payloads
- **Governance dependency**: Judy Council gRPC (`judy.JudyCouncil`)
- **Security model**: Signed payload envelope, TLS-ready Judy channel, and restricted egress to governance service

```mermaid
flowchart LR
		A[User Intent] --> B[Charon]
		B -->|Signed Proposal| C[Judy Council]
		C -->|Verdict| B
```

## Features

- Deterministic proposal builder for low-cost MVP operation
- Signature envelope (`X-Charon-Signature`) using HMAC-SHA256
- Judge/commit modes through one gRPC method (`ProposeTask`)
- Health and lightweight metrics methods
- Docker and Helm packaging aligned to multi-zone rollout
- Shared governance schema at `proto/judy.proto`

## gRPC API

- Service: `charon.CharonService`
- Method: `Health(google.protobuf.Empty) -> google.protobuf.Struct`
- Method: `GetMetrics(google.protobuf.Empty) -> google.protobuf.Struct`
- Method: `ProposeTask(google.protobuf.Struct) -> google.protobuf.Struct`

### `ProposeTask` Request Body (Struct JSON Shape)

```json
{
	"user_intent": "User confirmed this game is completed",
	"entity_id": "game_204",
	"target_table": "local_backlog",
	"action_type": "UPDATE_STATUS",
	"commit": false
}
```

## Local Run

```bash
docker compose up --build -d
```

Charon listens on `localhost:50051` (gRPC).

## Tests

```bash
docker compose run --rm charon pytest
```

## Configuration

| Variable | Description | Default |
| --- | --- | --- |
| `ENVIRONMENT` | Runtime environment hint used for startup validation (`dev`, `staging`, `prod`) | `dev` |
| `SERVICE_NAME` | Service identifier | `charon-agent` |
| `SERVICE_VERSION` | Version string | `0.1.0` |
| `CHARON_AGENT_ID` | Agent identifier in metadata | `charon-v1` |
| `GRPC_PORT` | gRPC listen port | `50051` |
| `GRPC_MAX_WORKERS` | gRPC thread pool worker count | `32` |
| `GRPC_TLS_ENABLED` | Enable inbound TLS listener | `false` |
| `GRPC_TLS_SERVER_CERT_PATH` | Server cert path for inbound TLS | empty |
| `GRPC_TLS_SERVER_KEY_PATH` | Server key path for inbound TLS | empty |
| `GRPC_TLS_REQUIRE_CLIENT_AUTH` | Require client cert on inbound listener (mTLS) | `false` |
| `GRPC_TLS_CLIENT_CA_CERT_PATH` | Trusted client CA path for inbound mTLS | empty |
| `JUDY_GRPC_TARGET` | Judy Council gRPC target | `judy-council:50052` |
| `JUDY_TIMEOUT_SECONDS` | gRPC timeout to Judy | `10` |
| `JUDY_TLS_ENABLED` | Enable TLS for Judy gRPC channel | `false` |
| `JUDY_TLS_CA_CERT_PATH` | CA certificate path for Judy TLS validation | empty |
| `JUDY_MTLS_ENABLED` | Enable mTLS for Judy gRPC channel | `false` |
| `JUDY_TLS_CLIENT_CERT_PATH` | Client cert path for Judy mTLS | empty |
| `JUDY_TLS_CLIENT_KEY_PATH` | Client key path for Judy mTLS | empty |
| `INBOUND_SIGNATURE_HEADER` | Signature header name for inbound proposal auth | `X-Judy-Signature` |
| `INBOUND_SIGNATURE_SECRET` | Shared secret for inbound proposal verification | required |
| `OUTBOUND_SIGNATURE_HEADER` | Signature header name for outbound Judy requests | `X-Charon-Signature` |
| `OUTBOUND_SIGNATURE_SECRET` | Shared secret for outbound proposal signing | required |
| `OUTBOUND_KEY_ID` | Signing key identifier for outbound envelope metadata | `charon-k1` |
| `REPLAY_TTL_SECONDS` | Replay protection window for inbound signed requests | `300` |

### Compose mTLS Profile

Generate local dev certificates first:

```powershell
./scripts/generate-dev-certs.ps1 -Force
```

Run Charon with inbound TLS + client auth and outbound mTLS to Judy:

```bash
docker compose -f docker-compose.yml -f docker-compose.mtls.yml up --build
```

Verify certificate chains and mTLS handshakes:

```powershell
./scripts/verify-mtls.ps1
```

If Charon or Judy is not running, verify cert trust only:

```powershell
./scripts/verify-mtls.ps1 -SkipHandshake
```

## Kubernetes / Helm

A starter chart is provided at `charts/charon` with:

- Deployment
- ServiceAccount
- Service (gRPC)
- Secret
- Egress NetworkPolicy (allow to Judy only)
- Optional CA secret mount for Judy TLS

Install example:

```bash
helm upgrade --install charon charts/charon -n agent-zone --create-namespace
```

### k3d Quick Deploy

For local k3d deployment with image build/import and Helm install:

```powershell
./scripts/deploy-k3d.ps1
```

Optional overrides:

```powershell
./scripts/deploy-k3d.ps1 -ClusterName trophy-local -Namespace agent-zone -ReleaseName charon -ImageRepository charon-agent -ImageTag latest -JudyNamespace governance-zone
```

## Repository Layout

```text
Charon/
├── app/
│   ├── grpc_server.py
│   ├── judy_client.py
│   ├── orchestrator.py
│   ├── models.py
│   ├── signer.py
│   └── config.py
├── proto/
│   └── judy.proto
├── charts/charon/
├── scripts/
│   └── deploy-k3d.ps1
├── tests/
│   └── test_api.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```
