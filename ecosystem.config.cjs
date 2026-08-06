module.exports = {
  apps: [{
    name: 'country-intel-api',
    cwd: '/home/deploy/country-intel',
    script: 'venv/bin/uvicorn',
    args: 'src.server:app --host 127.0.0.1 --port 8710',
    interpreter: 'none',
    env: { PORT: '8710' },
  }]
};
