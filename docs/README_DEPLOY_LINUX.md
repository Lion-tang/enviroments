# Linux Offline Deployment

This package is built by GitHub Actions on Linux. It contains the backend executable and bundled frontend static files.

## Run

```bash
tar -xzf Enviroments-linux-*.tar.gz
cd Enviroments-linux-*
chmod +x Enviroments
./Enviroments
```

The service listens on `0.0.0.0:8000` by default. Open:

```text
http://<server-ip>:8000
```

## Notes

- Use the ARM64 package on Linux ARM64, and the x86_64 package on Linux x86_64.
- PyInstaller runs inside a `manylinux_2_34` container for the target architecture, so Linux packages target glibc 2.34. Systems older than glibc 2.34 may still require a custom build on an older base.
- Official standalone packages embed CPython 3.9. The Python version installed on the offline machine is not used; no Node.js, pnpm, Python, or pip installation is required.
- The runtime directory must be writable because SQLite data and logs are generated at runtime.
- SSH, SFTP, and Web SSH require network access from this machine to managed servers.

## 稳定性注意事项

- 当前后端进程内置 APScheduler。生产环境请保持单个 Uvicorn worker；多 worker 会各自启动一套定时任务。需要扩容时，应先把调度器拆到单独进程或加入跨进程租约。
- SQLite 已启用 WAL。在线备份前执行 `PRAGMA wal_checkpoint(TRUNCATE);`，或者停止后端后再复制 `enviroments.db`，避免遗漏仍在 `enviroments.db-wal` 中的事务。
- 服务端运行日志按 5MB 轮转并保留 5 份；可结合系统日志策略定期归档或删除更早的备份。
- 应用会在解析前限制文件上传请求体；如果前面还有 Nginx/Caddy，请同步设置约 257MB 的 multipart 限制和约 342MB 的旧版 Base64 接口限制。
