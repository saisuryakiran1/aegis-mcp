# Aegis-MCP

Aegis-MCP sits between an MCP client and an upstream MCP server, evaluating every tool call against declarative policies before it reaches the server. MCP agents routinely invoke tools that execute SQL, send payments, or modify external systems — and those calls are forwarded with implicit trust. Aegis-MCP adds a deterministic structural layer (AST-based SQL parsing, length limits, threshold checks), an optional semantic risk judge, and a human-in-the-loop escalation path so high-risk calls are blocked or held for review instead of executed blindly.

## Architecture

```
  MCP Client                Aegis-MCP                    Upstream MCP Server
 (Cursor, etc.)         (FastAPI proxy)                  (stdio / HTTP)
       |                       |                                |
       |  JSON-RPC tools/call  |                                |
       |---------------------->|  1. policy lookup              |
       |                       |  2. structural validation      |
       |                       |  3. semantic judge             |
       |                       |  4. risk score + decision      |
       |                       |                                |
       |    ALLOW  ------------|-- JSON-RPC forward ----------->|
       |    BLOCK  <-----------|  (error -32001, no forward)    |
       |    ESCALATE <---------|  (HITL queue + webhook)        |
       |                       |                                |
       |              Review Console (Next.js)                  |
       |                       |  approve -> forward upstream   |
```

## Quickstart

### 1. Install Python dependencies

```bash
cd aegis-mcp
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

Copy `.env.example` to `.env` and set values as needed. Policy rules live in `aegis-config.yaml` (non-secret config only).

### 3. Run the API

```bash
python main.py
# listens on http://localhost:8000
```

### 4. Run the review console

```bash
cd console
npm install
npm run dev
# opens http://localhost:3000, polls API at NEXT_PUBLIC_API_URL (default http://localhost:8000)
```

Trigger an escalation (e.g. payment over $100):

```bash
curl -X POST http://localhost:8000/v1/tools/call \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"send_payment","arguments":{"amount":150}}}'
```

The call appears in the console for approve/reject.

## Security Model

**Stdio upstream (v1 scope):** Aegis-MCP is designed to wrap upstream MCP servers launched as child processes over stdio, where the proxy is the only entry point. In that deployment, the upstream server has no independently exposed transport — process isolation prevents clients from bypassing the guardrail layer.

**SSE/HTTP upstream (not implemented):** Network-policy enforcement, credential gating, and transport-level access controls for SSE or HTTP upstream MCP servers are **not** implemented in this version. Deploying Aegis-MCP in front of a publicly reachable upstream URL does not, by itself, prevent a determined client from calling that URL directly. Treat this as a known gap, not a solved problem.

## Known Limitations

- **Semantic judge adversarial robustness:** The Anthropic-backed semantic judge can be misled by adversarial prompts. It is a supplementary signal, not a guarantee.
- **AST allowlist scope:** Structural SQL parsing via sqlglot covers `execute_sql_query` only. Other tool types without a matching policy fall back to default-deny.
- **In-memory HITL queue:** Pending calls are stored in process memory and are lost on restart. There is no persistence or multi-instance coordination.
- **No authentication:** The API and review console ship without auth — suitable for local demos only.

## Worked Examples

These are the exact scoring scenarios exercised in `tests/test_risk_scorer.py` (weights: w_b=0.7, w_s=0.3).

| # | Scenario | S_b | S_s | R | Action |
|---|----------|-----|-----|---|--------|
| 1 | Clean SELECT, semantic safe | 0.0 | 0.0 | 0.0 | ALLOW |
| 2 | Clean SELECT, semantic medium | 0.0 | 0.66 | 0.20 | ALLOW |
| 3 | DROP TABLE attempt, semantic safe | 1.0 | 0.0 | 0.70 | BLOCK |
| 4 | Oversized query (>500 chars), semantic low | 1.0 | 0.33 | 0.80 | BLOCK |
| 5 | Payment $50, semantic safe | 0.0 | 0.0 | 0.0 | ALLOW |
| 6 | Payment $150 (threshold violation), semantic safe | 1.0 | 0.0 | 0.70 | ESCALATE_TO_HUMAN |
| 7 | Payment $150, semantic high | 1.0 | 1.0 | 1.0 | BLOCK |
| 8 | Unknown tool (no policy) | — | — | 1.0 | BLOCK (default-deny) |
| 9 | Stacked query injection, semantic high | 1.0 | 1.0 | 1.0 | BLOCK |
| 10 | Clean SELECT, semantic high (suspicious framing) | 0.0 | 1.0 | 0.30 | ESCALATE_TO_HUMAN |

Scoring formula: `R = (w_b × S_b) + (w_s × S_s)`. Thresholds: R < 0.3 → ALLOW; 0.3 ≤ R ≤ 0.7 → ESCALATE_TO_HUMAN; R > 0.7 → BLOCK. BLOCK-type structural rule failures at R = 0.7 also map to BLOCK.

## License

MIT (add your preferred license before publishing).
