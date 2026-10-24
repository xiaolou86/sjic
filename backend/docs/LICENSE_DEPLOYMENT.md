# 授权部署说明

## 行为

1. **未导入授权**：可用默认账号登录，但业务功能全部不可用，需先导入授权文件。
2. **试用版 (`trial`)**：自签发日起 **30 天**，并限制 `max_cameras`（视频接入路数）。
3. **正式版 (`official`)**：按签发时填写的 `expires_at` 与 `max_cameras` 生效。
4. 授权文件带 **HMAC 签名**，并绑定本机 `machine_code`，防止篡改与虚机镜像复制后直接复用。

授权文件默认路径：`backend/instance/license.json`（Docker 已挂载 `instance/`）。

## 机器码（防克隆，且容器 rebuild 不失效）

`machine_code` = `SHA256`（下列因子按 key 排序后拼接），**不含容器 hostname**。

| 因子 | 来源 | 说明 |
|------|------|------|
| `machine_id` | `HOST_MACHINE_ID` / `/host/etc/machine-id` / `/etc/machine-id` | 宿主机 machine-id；Linux Docker 建议挂载 |
| `product_uuid` | `/sys/class/dmi/id/product_uuid` | 主板/虚机 UUID（有则加入） |
| `board_serial` / `product_serial` | DMI serial | 有真实值才加入（过滤 OEM 占位） |
| `windows_uuid` | Win32 `ComputerSystemProduct.UUID` | 仅 Windows 本机进程 |
| `mac_node` | `uuid.getnode()` | **仅非容器环境**；Docker 网卡 MAC 会随 recreate 变化，故容器内不参与计算 |
| `system` / `release` / `machine` | `platform.*` | OS 族、版本、架构 |

因此：

- `docker compose up --build` / 重建容器 **不应** 导致授权失效。
- 克隆虚机后若 `machine-id` / 虚拟机 UUID 变化，机器码仍会变，旧授权失效。

校验时同时接受「稳定指纹」与「含 MAC 的旧指纹」，避免升级后端后正在运行的环境突然判无效。

### Docker 部署

Compose 已设置 `SJIC_IN_CONTAINER=1`，容器内不会把 Docker NIC MAC 算进机器码。

Linux 生产环境请挂载宿主机 machine-id（根目录 `docker-compose.yml` 中取消注释）：

```yaml
- /etc/machine-id:/host/etc/machine-id:ro
```

也可通过环境变量传入：

```bash
HOST_MACHINE_ID=$(cat /etc/machine-id) docker compose up -d
```

Windows Docker Desktop 一般无需挂载；依赖容器可见的 DMI `product_uuid` 等稳定因子。

## 签发授权

签发不在 backend 里做，由仓库根目录的 [`license-server/`](../../license-server/README.md) 单独部署在发行方机器上，提供签发页面并记录每次签发。它的 `LICENSE_SIGNING_KEY` 必须与客户平台一致。

`issued_at` / `expires_at` 使用 **YYYY-MM-DD**（到期日当天仍有效）。

客户从「授权管理」页复制机器码并发给发行方；拿到文件后在同一页面导入。

也可调用 API：

- `GET /api/license/status`
- `POST /api/license/import`（multipart 字段 `license`，或 JSON body）

> 若此前已因容器 rebuild 导致授权失效：部署本修复后，请用页面上的**新机器码**重新签发并导入一次；之后 rebuild 不再需要重签。

## 配置

`backend/config.yaml`：

```yaml
license:
  trial_max_cameras: 4          # 仅作签发参考/状态展示
  signing_key: "change-me"      # 须与 license-server 一致；也可用环境变量 LICENSE_SIGNING_KEY
```

## 运行时约束

- 全局：无有效授权时，除登录 / 品牌 / 授权接口外，业务 API 返回 403。
- 创建摄像头时校验视频路数配额。
- 任务创建/更新/启动校验算法授权（`allowed_algorithms` 为空表示不限制算法）。
