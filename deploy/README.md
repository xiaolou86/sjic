# 安装与升级

客户环境不放源码。

- 第一次安装：[docs/初次打包与部署.md](../docs/初次打包与部署.md)
- 之后发版本：[docs/后续打包与升级.md](../docs/后续打包与升级.md)

`deploy/platform/install-host.sh` 和 `edge-agent/deploy/install-host.sh` 只给开发机联调，会从当前仓库拷贝代码。客户机器用交付包里的 `install.sh`。

在 Linux 打包机的仓库根目录打包。正式版本必须是干净工作区上的 `vX.Y.Z` tag。

```bash
make package
```

应用包里的 Python 文件只有 `.pyc`。上传时按清单核对每个文件的校验和。
