# 授权签发服务

给客户平台签发 `license.json`，并把每次签发记在 SQLite（`data/licenses.db`）里。只部署在发行方自己的机器上，不随客户平台交付。

客户平台只负责验签和导入，规则见 [backend/docs/LICENSE_DEPLOYMENT.md](../backend/docs/LICENSE_DEPLOYMENT.md)。

## 部署（Ubuntu + Docker）

只需要拷贝 `license-server/` 这一个目录。

```bash
cd license-server
cp .env.example .env
vi .env        # 填 LICENSE_SIGNING_KEY 和 LICENSE_ADMIN_PASSWORD
docker compose up -d --build
```

浏览器打开 `http://<服务器IP>:38890`，用 `.env` 里的账号密码登录。

- `LICENSE_SIGNING_KEY` 必须和客户平台 backend 的完全一致，否则导入时报「签名无效」。平台没单独设置时，值是 `change-me-sjic-license-signing-key`。
- 页面只用 HTTP Basic Auth，密码明文传输。只在内网使用，或放到带 HTTPS 的反向代理后面。

升级代码后重新执行 `docker compose up -d --build`，记录不受影响。

## 使用

1. 客户在平台「授权管理」页复制机器码发过来。
2. 在签发页填机器码、版本、路数（正式版再填到期日），点「签发」。
3. 下载授权文件发给客户，客户在「授权管理」页导入。

所有记录都在页面下方列表，可随时重新下载。

## 数据与备份

记录只有一个文件：`license-server/data/licenses.db`。备份时复制它即可（建议先 `docker compose stop`）。

## 命令行签发

和页面一样会写入记录：

```bash
docker compose exec -T license-server python generate_license.py \
  --machine-code <客户机器码> --edition official --max-cameras 32 \
  --expires-at 2027-12-31 --customer-id acme > license.json
```

试用版用 `--edition trial`，不用填到期日。

## 本地开发

```bash
pip install -r requirements.txt pytest
pytest
LICENSE_SIGNING_KEY=dev-key python app.py    # http://127.0.0.1:38890，未设密码时不校验登录
```

`signer.py` 的签名算法必须与 `backend/app/services/license_service.py` 保持一致；两边的测试固定了同一组签名样例。
