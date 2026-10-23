const rawBackendPort = process.env.BACKEND_PORT ?? '8000';
const backendPort = Number(rawBackendPort);
if (!Number.isInteger(backendPort) || backendPort < 1 || backendPort > 65535) {
  throw new Error('BACKEND_PORT must be an integer between 1 and 65535.');
}
module.exports = {
  '/api': {
    target: 'http://127.0.0.1:' + backendPort,
    changeOrigin: true,
  },
};
