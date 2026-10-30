const rawBackendPort = process.env.BACKEND_PORT ?? '8000';
const backendPort = Number(rawBackendPort);
if (!Number.isInteger(backendPort) || backendPort < 1 || backendPort > 65535) {
  throw new Error('BACKEND_PORT must be an integer between 1 and 65535.');
}
const localAgentToken = process.env.LOCAL_AGENT_TOKEN ?? '';
if (!/^[0-9a-f]{64}$/.test(localAgentToken)) {
  throw new Error('LOCAL_AGENT_TOKEN is missing or invalid. Run scripts\setup.ps1.');
}
module.exports = {
  '/api': {
    target: 'http://127.0.0.1:' + backendPort,
    changeOrigin: true,
    headers: { 'X-Local-Agent-Token': localAgentToken },
  },
};
